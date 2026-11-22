#!/usr/bin/env python3
"""Immutable planning context against fresh records, actual CLI and owned PTY."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import status_tui as tui
import status_tui_context as context
import status_tui_data as data
import status_tui_input as feed
from test_status_tui import OwnedPTY, child_env
from test_status_tui_data import dump, fixture

SCRIPT = Path(__file__).with_name('status_tui.py')
NATIVE = 'agent-company-development'


def enriched(root):
    manifest, record, claims, plan = fixture(root, count=2)
    for task, attached in zip(record['tasks'], manifest['tasks']):
        task['execution']['actor'] = attached['actor']
        task['technical']['actor'] = 'independent-qa'
        task['model']['requested'] = attached['assigned_model'] = 'm1'
    manifest['sources'][0]['sha256'] = manifest['binding']['record_sha256'] = dump(root/'record.json', record)
    registry = {'id': 'development', 'native_agent': {'name': NATIVE}}
    pin = dump(root/'registry.json', registry)
    manifest['sources'].append({'id': 'registry', 'path': 'registry.json', 'sha256': pin, 'kind': 'registry'})
    assignments = {'scope': record['goal']['scope'], 'revision': record['goal']['revision'], 'assignments': [
        {'task': task['id'], 'dispatch': task['current_dispatch'], 'actor': attached['actor'], 'specialist': NATIVE}
        for task, attached in zip(record['tasks'], manifest['tasks'])]}
    pin = dump(root/'assignments.json', assignments)
    manifest['sources'].append({'id': 'assignment', 'path': 'assignments.json', 'sha256': pin, 'kind': 'assignment'})
    for i, attached in enumerate(manifest['tasks']):
        attached['specialist'] = {'status': 'assigned', 'id': NATIVE,
                                  'evidence': [{'source': 'assignment', 'pointer': f'/assignments/{i}'}]}
    dump(root/'view.json', manifest)
    return manifest, record


class ContextPTY(OwnedPTY):
    def __init__(self, root):
        original = subprocess.Popen
        def launch(argv, **kwargs):
            argv = list(argv); position = argv.index('--manifest')
            argv[position:position+2] = ['--record', str(Path(root)/'record.json'),
                                       '--context', str(Path(root)/'context.json')]
            return original(argv, **kwargs)
        with patch.object(subprocess, 'Popen', side_effect=launch):
            super().__init__(root, 80, 12)


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.manifest, self.record = enriched(self.root)
        self.record_path, self.metadata, self.path = (self.root/name for name in ('record.json', 'view.json', 'context.json'))
        env = child_env(self.root)
        if os.environ.get('COMPANY_TUI_TEST_EVIDENCE'):
            env['COMPANY_TUI_TEST_EVIDENCE'] = os.environ['COMPANY_TUI_TEST_EVIDENCE']
        self.environment = patch.dict(os.environ, env, clear=True)
        self.environment.start(); self.addCleanup(self.environment.stop)

    def capture(self): return context.capture_context(self.record_path, self.metadata, self.path)
    def load(self): return feed.load_record_snapshot(self.record_path, context_path=self.path)
    def save(self): dump(self.record_path, self.record)
    def files(self): return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir() if p.is_file()}

    def stable(self, snap):
        for i, task in enumerate(snap['tasks']):
            self.assertEqual(task['title'], f'작업 {i+1}')
            self.assertEqual(task['classification'], 'code')
            self.assertEqual(task['team_id'], 'build' if i == 0 else 'review')
            self.assertEqual(task['assigned_model'], 'm1')
            self.assertEqual(task['specialist']['id'], NATIVE)
        self.assertEqual(snap['tasks'][1]['needs'], ['t1'])
        self.assertEqual(snap['live_host_state'], 'unknown')
        self.assertFalse(snap['overall_goal_acceptance']['earned_success'])

    def test_capture_new_private_file_only_and_read_only_refresh(self):
        before = self.files(); receipt = self.capture()
        self.assertEqual(receipt['status'], 'captured'); self.assertFalse(receipt['launch_authorized'])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(before, {k: v for k, v in self.files().items() if k != self.path.name})
        captured = json.loads(self.path.read_text())
        self.assertNotIn('execution', self.path.read_text())
        self.assertEqual(captured['record_facts'], {'/tasks/0': {'id': 't1'}, '/tasks/1': {'id': 't2'}})
        after = self.files(); self.stable(self.load()); self.load()
        self.assertEqual(self.files(), after)

    def test_states_acc_sub_acc_keep_all_fields_without_hash_edits(self):
        self.capture(); frozen = self.path.read_bytes(); metadata = self.metadata.read_bytes()
        original = copy.deepcopy(self.record['tasks'][1]['technical'])
        for technical, state in [(original, 'ACC'), (None, 'SUB'), (original, 'ACC')]:
            self.record['tasks'][1]['technical'] = technical; self.save()
            snap = self.load(); self.stable(snap); self.assertEqual(snap['tasks'][1]['state'], state)
            self.assertEqual(self.path.read_bytes(), frozen); self.assertEqual(self.metadata.read_bytes(), metadata)

    def test_original_metadata_still_stale_rejects_context_works(self):
        self.capture(); self.record['tasks'][0]['technical'] = None; self.save()
        with self.assertRaises(data.InputError): feed.load_record_snapshot(self.record_path, self.metadata)
        with self.assertRaises(data.InputError): data.load_snapshot(self.metadata)
        self.assertEqual(self.load()['tasks'][0]['state'], 'SUB')

    def test_revision_scope_goal_dispatch_task_and_actor_changes_reject(self):
        self.capture(); original = copy.deepcopy(self.record)
        changes = [lambda r: r['goal'].update(revision='r2'), lambda r: r['goal'].update(scope='elsewhere'),
                   lambda r: r['goal'].update(id='new-goal'), lambda r: r['tasks'][0].update(current_dispatch='new'),
                   lambda r: r['tasks'][0].update(id='new'), lambda r: r['tasks'].pop(),
                   lambda r: r['tasks'].append(copy.deepcopy(r['tasks'][0])),
                   lambda r: r['tasks'][0]['execution'].update(actor='different'),
                   lambda r: r['tasks'][0].update(goal_revision='r2')]
        for change in changes:
            self.record = copy.deepcopy(original); change(self.record); self.save()
            with self.subTest(change=change), self.assertRaises(data.InputError): self.load()

    def test_model_routing_known_and_unknown_assignment_changes_reject(self):
        self.capture()
        self.record['tasks'][0]['model']['requested'] = 'new-model'; self.save()
        with self.assertRaises(data.InputError): self.load()
        self.record['tasks'][0]['model']['requested'] = None; self.save()
        with self.assertRaises(data.InputError): self.load()
        self.record['tasks'][0]['model']['requested'] = 'm1'
        self.record['tasks'][0]['routing_decision'] = {'binding': {'task': 't1', 'attempt': 'd1',
            'scope': 'approved-scope', 'revision': 'r1'}, 'selected': {'model': 'm1'}}
        self.save()
        with self.assertRaises(data.InputError): self.load()

    def test_each_original_metadata_source_drift_rejects_no_repins(self):
        self.capture(); frozen = self.path.read_bytes()
        for name in ('view.json', 'claims.json', 'plan.json', 'assignments.json', 'registry.json'):
            p = self.root/name; original = p.read_bytes(); p.write_bytes(original+b' ')
            with self.subTest(name=name), self.assertRaises(data.InputError): self.load()
            p.write_bytes(original)
        self.assertEqual(self.path.read_bytes(), frozen)
        self.stable(self.load())

    def test_capture_conflicting_declared_actor_refuses_no_output(self):
        self.manifest['tasks'][0]['actor'] = 'reviewer'; dump(self.metadata, self.manifest)
        with self.assertRaises(data.InputError): self.capture()
        self.assertFalse(self.path.exists())

    def test_capture_stale_metadata_or_wrong_record_path_refuses(self):
        self.record['tasks'][0]['technical'] = None; self.save()
        with self.assertRaises(data.InputError): self.capture()
        self.assertFalse(self.path.exists())
        other = self.root/'other.json'; other.write_bytes(self.record_path.read_bytes())
        with self.assertRaises(data.InputError): context.capture_context(other, self.metadata, self.path)

    def test_missing_metadata_fields_stay_unknown_and_explicit_none(self):
        self.manifest['tasks'].pop(); dump(self.metadata, self.manifest)
        self.capture(); task = self.load()['tasks'][1]
        self.assertEqual(task['title'], '?'); self.assertIsNone(task['classification']); self.assertIsNone(task['team_id'])
        self.assertEqual(task['specialist']['status'], 'unknown'); self.assertEqual(task['assigned_model'], 'm1')

    def test_absent_org_does_not_infer_registry_roster(self):
        self.manifest['organization'] = None
        for task in self.manifest['tasks']: task['team_id'] = None
        dump(self.metadata, self.manifest); self.capture()
        snap = self.load(); self.assertIsNone(snap['organization'])
        self.assertTrue(all(task['team_id'] is None for task in snap['tasks']))

    def test_unproven_relation_renders_unknown_not_declared_membership(self):
        claims = json.loads((self.root/'claims.json').read_text())
        claims['unproven'] = {'actor': 'worker'}
        self.manifest['sources'][1]['sha256'] = dump(self.root/'claims.json', claims)
        self.manifest['organization']['teams'][0]['members'][0]['evidence'] = [
            {'source': 'claims', 'pointer': '/unproven'}]
        dump(self.metadata, self.manifest); self.capture()
        snap = self.load()
        self.assertEqual(snap['organization']['teams'][0]['members'][0]['basis'], 'unknown')
        frame = tui.render_frame(snap, 80, 12, mode='org')
        self.assertIn('member:? | unknown', frame)
        self.assertNotIn('member:worker', frame)

    def test_captured_org_acceptance_never_promoted(self):
        claims = json.loads((self.root/'claims.json').read_text())
        claims['head'] = {'actor': 'B', 'status': 'accepted'}
        self.manifest['sources'][1]['sha256'] = dump(self.root/'claims.json', claims)
        dump(self.metadata, self.manifest)
        self.assertEqual(data.load_snapshot(self.metadata)['organization']['head']['acceptance'], 'claimed')
        self.capture(); self.assertEqual(self.load()['organization']['head']['acceptance'], 'unknown')

    def test_record_not_persistent_org_or_specialist_authority(self):
        self.record['org'] = {'scope': 'approved-scope', 'revision': 'r1', 'head': 'B', 'teams': []}
        self.manifest['organization']['head']['evidence'] = [{'source': 'record', 'pointer': '/org/head'}]
        self.manifest['sources'][0]['sha256'] = self.manifest['binding']['record_sha256'] = dump(self.record_path, self.record)
        dump(self.metadata, self.manifest)
        with self.assertRaises(data.InputError): self.capture()
        self.assertFalse(self.path.exists())

    def test_record_current_execution_evidence_stays_pinned(self):
        self.capture(); external = self.root/'evidence.txt'; external.write_text('fresh evidence')
        self.record['evidence']['result'].update(file=external.name, sha256=hashlib.sha256(external.read_bytes()).hexdigest())
        self.save(); self.stable(self.load())
        external.write_text('changed')
        with self.assertRaises(data.InputError): self.load()

    def test_checker_error_and_live_not_promoted_by_context(self):
        self.capture(); task = self.record['tasks'][0]
        task['technical']['candidate'] = 'old'; self.save()
        snap = self.load(); self.assertFalse(snap['check']['ok']); self.assertNotEqual(snap['tasks'][0]['state'], 'ACC')
        task.update(technical=None, parent_integration=None); task['execution'].update(state='live', result=None); self.save()
        snap = self.load(); self.assertEqual(snap['tasks'][0]['state'], '?'); self.stable(snap)

    def test_output_overwrite_symlink_directory_permissions_refuse(self):
        self.capture(); frozen = self.path.read_bytes()
        with self.assertRaises(data.InputError): self.capture()
        self.assertEqual(self.path.read_bytes(), frozen)
        link = self.root/'link.json'; link.symlink_to(self.path)
        with self.assertRaises(data.InputError): context.capture_context(self.record_path, self.metadata, link)
        directory = self.root/'output'; directory.mkdir()
        directory.chmod(0o755)  # Set the fixture mode independently of the runner's umask.
        with self.assertRaises(data.InputError): context.capture_context(self.record_path, self.metadata, directory/'context.json')
        safe = self.root/'safe'; safe.mkdir(mode=0o700); alias = self.root/'alias'; alias.symlink_to(safe, target_is_directory=True)
        with self.assertRaises(data.InputError): context.capture_context(self.record_path, self.metadata, alias/'context.json')
        self.assertFalse((safe/'context.json').exists())

    def test_reader_symlinks_tamper_and_record_path_refuse(self):
        self.capture(); original = self.path.read_bytes()
        alias = self.root/'alias.json'; alias.symlink_to(self.path)
        with self.assertRaises(data.InputError): context.load_context_snapshot(self.record_path, alias)
        for raw in (b'{', b'{"x":NaN}', b'{"x":1,"x":2}'):
            self.path.write_bytes(raw)
            with self.assertRaises(data.InputError): self.load()
        self.path.write_bytes(original)
        other = self.root/'other.json'; other.write_bytes(self.record_path.read_bytes())
        with self.assertRaises(data.InputError): context.load_context_snapshot(other, self.path)
        with self.assertRaises(data.InputError): feed.load_record_snapshot(self.record_path, self.metadata, context_path=self.path)

    def test_identity_race_while_checking_rejects(self):
        self.capture(); original = data.status_view.build_view
        def race(*args, **kwargs):
            result = original(*args, **kwargs)
            replacement = self.root/'replacement.json'; replacement.write_bytes(self.path.read_bytes()); replacement.replace(self.path)
            return result
        with patch.object(data.status_view, 'build_view', side_effect=race), self.assertRaises(data.InputError): self.load()

    def test_capture_source_identity_race_no_output(self):
        original = context._record_facts
        def race(*args):
            result = original(*args)
            replacement = self.root/'replacement.json'; replacement.write_bytes(self.metadata.read_bytes()); replacement.replace(self.metadata)
            return result
        with patch.object(context, '_record_facts', side_effect=race), self.assertRaises(data.InputError): self.capture()
        self.assertFalse(self.path.exists())

    def test_capture_output_race_refuses_success(self):
        original = os.open
        def race(path, flags, *args, **kwargs):
            if path == self.path.name and flags & os.O_CREAT:
                self.path.write_text('other writer')
            return original(path, flags, *args, **kwargs)
        with patch.object(os, 'open', side_effect=race), self.assertRaises(data.InputError): self.capture()
        self.assertEqual(self.path.read_text(), 'other writer')

    def test_capture_source_drift_during_output_write_refuses_success(self):
        original = context._new_private_file
        def race(path, raw):
            original(path, raw)
            (self.root/'claims.json').write_text('{}')
        with patch.object(context, '_new_private_file', side_effect=race), self.assertRaises(data.InputError): self.capture()
        with self.assertRaises(data.InputError): self.load()

    def test_refresh_mismatch_is_error_whole_last_good_then_recovery(self):
        self.capture(); refresh = tui.RefreshState(self.record_path, .25, record=True, context=self.path)
        self.assertTrue(refresh.refresh(0)); good = refresh.snapshot
        self.record['tasks'][0]['execution']['actor'] = 'other'; self.save()
        self.assertTrue(refresh.refresh(.25)); self.assertIs(refresh.snapshot, good); self.assertIsNotNone(refresh.error)
        self.record['tasks'][0]['execution']['actor'] = 'worker'; self.record['tasks'][0]['technical'] = None; self.save()
        self.assertTrue(refresh.refresh(5.25)); self.assertIsNone(refresh.error); self.stable(refresh.snapshot)
        assert refresh.snapshot is not None
        self.assertEqual(refresh.snapshot['tasks'][0]['state'], 'SUB')

    def cli(self, *args):
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), *map(str, args)],
            capture_output=True, text=True, env=child_env(self.root), timeout=15)
        evidence = os.environ.get('COMPANY_TUI_TEST_EVIDENCE')
        if evidence:
            directory = Path(evidence); directory.mkdir(parents=True, exist_ok=True)
            with (directory/'context-cli.jsonl').open('a') as stream:
                stream.write(json.dumps({'argv': list(map(str,args)), 'exit': result.returncode,
                                         'stdout': result.stdout, 'stderr': result.stderr}, ensure_ascii=False)+'\n')
        return result

    def test_actual_cli_capture_refresh_and_invalid_arguments(self):
        result = self.cli('--record', self.record_path, '--metadata', self.metadata, '--capture-context', self.path)
        self.assertEqual(result.returncode, 0, result.stderr); self.assertEqual(json.loads(result.stdout)['status'], 'captured')
        accepted = copy.deepcopy(self.record['tasks'][1]['technical'])
        for technical, state in [(accepted, 'ACC'), (None, 'SUB'), (accepted, 'ACC')]:
            self.record['tasks'][1]['technical'] = technical; self.save()
            result = self.cli('--record', self.record_path, '--context', self.path, '--once', '--json')
            self.assertEqual(result.returncode, 0, result.stderr)
            snap = json.loads(result.stdout); self.stable(snap); self.assertEqual(snap['tasks'][1]['state'], state)
        for args in [('--manifest', self.metadata, '--context', self.path),
                     ('--record', self.record_path, '--metadata', self.metadata, '--context', self.path),
                     ('--record', self.record_path, '--capture-context', self.path),
                     ('--record', self.record_path, '--metadata', self.metadata, '--capture-context', self.path)]:
            self.assertEqual(self.cli(*args).returncode, 2)
        self.record['tasks'][0]['current_dispatch'] = 'new'; self.save()
        self.assertEqual(self.cli('--record', self.record_path, '--context', self.path, '--once').returncode, 2)

    def test_actual_owned_80x12_acc_sub_acc_fields_needs_and_error(self):
        result = self.cli('--record', self.record_path, '--metadata', self.metadata, '--capture-context', self.path)
        self.assertEqual(result.returncode, 0, result.stderr)
        frozen = self.path.read_bytes(); metadata = self.metadata.read_bytes()
        terminal = ContextPTY(self.root); self.addCleanup(terminal.close)
        output = terminal.until('page:1/')  # both dependent nodes now co-visible
        def fields(output):
            for token in ('작업 2', '코드', '모델명 미확인 · 할당 ID:m1', '개발 전문가', '[review]', '│───▶│'):
                self.assertIn(token.encode(), output)
        fields(output); self.assertIn('작업 검토 통과'.encode(), output)
        accepted = copy.deepcopy(self.record['tasks'][1]['technical'])
        self.record['tasks'][1]['technical'] = None; self.save()
        output = terminal.until('제출·검토 대기', timeout=7); fields(output)
        self.record['tasks'][1]['technical'] = accepted; self.save()
        output = terminal.until('작업 검토 통과', timeout=7); fields(output)
        self.record['tasks'][1]['execution']['actor'] = 'wrong'; self.save()
        output = terminal.until('ERROR | last-good', timeout=7); fields(output)
        receipt = terminal.close(signal.SIGTERM)
        for flag in ('semantic_restored', 'cursor_shown', 'alternate_left', 'reaped', 'fds_closed'):
            self.assertTrue(receipt[flag], receipt)
        self.assertEqual(receipt['exit'], 0, receipt)
        self.assertEqual(self.path.read_bytes(), frozen); self.assertEqual(self.metadata.read_bytes(), metadata)


if __name__ == '__main__': unittest.main()
