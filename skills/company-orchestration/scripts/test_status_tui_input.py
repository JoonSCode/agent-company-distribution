#!/usr/bin/env python3
"""Ordinary Company records through the real product; no live staffed-run claim."""
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
import time
import unittest
from unittest.mock import patch
import open_run_view as opener
import status_tui as tui
import status_tui_data as data
import status_tui_input as feed
from test_status_tui import OwnedPTY, child_env
from test_status_tui_data import ASSETS, dump, fixture

SCRIPT = Path(__file__).with_name('status_tui.py')


class OrcaRunInputTests(unittest.TestCase):
    run_id = 'run_selected'

    def response(self):
        return {'ok': True, 'result': {'runId': self.run_id, 'count': 3, 'tasks': [
            {'id': 'root', 'run_id': self.run_id, 'task_title': 'Root',
             'status': 'completed', 'deps': '[]', 'spec': 'Unrelated private task specification'},
            {'id': 'parallel', 'run_id': self.run_id, 'task_title': 'Parallel',
             'status': 'dispatched', 'parent_id': 'root', 'deps': []},
            {'id': 'consumer', 'run_id': self.run_id, 'task_title': 'Consumer',
             'status': 'pending', 'deps': '["root"]'},
        ]}}

    def completed(self, response, code=0):
        return subprocess.CompletedProcess([], code, json.dumps(response).encode(), b'')

    def test_exact_run_and_explicit_dependencies_are_observed_without_acceptance(self):
        with patch.object(feed, 'resolve_orca', return_value='local-orca'), patch.object(
            feed.subprocess, 'run', return_value=self.completed(self.response())
        ) as command:
            snapshot = feed.load_run_snapshot(self.run_id)
        self.assertEqual(command.call_args.args[0], [
            'local-orca', 'orchestration', 'task-list', '--environment', 'local',
            '--run', self.run_id, '--full', '--brief', '--json',
        ])
        self.assertEqual(snapshot['binding'], {'run_id': self.run_id})
        self.assertEqual(snapshot['tasks'][0]['host_status'], 'completed')
        self.assertEqual(snapshot['tasks'][0]['state'], '?')
        self.assertEqual(snapshot['tasks'][1]['needs'], [])
        self.assertEqual(snapshot['tasks'][2]['needs'], ['root'])
        self.assertFalse(snapshot['overall_goal_acceptance']['earned_success'])
        self.assertNotIn('Unrelated private task specification', json.dumps(snapshot))
        frame = tui.render_frame(snapshot, 120, 28)
        self.assertIn('Run ' + self.run_id, frame)
        self.assertIn('Orca: completed', frame)
        self.assertNotIn('작업 검토 통과', frame)

    def test_foreign_or_contradictory_responses_are_rejected(self):
        for field, replacement in (('run_id', 'run_other'), ('id', 'root'),
                                   ('deps', ['consumer']), ('deps', ['unknown'])):
            response = self.response()
            response['result']['tasks'][2][field] = replacement
            with self.subTest(field=field, replacement=replacement), patch.object(
                feed.subprocess, 'run', return_value=self.completed(response)
            ):
                with self.assertRaises(data.InputError):
                    feed.load_run_snapshot(self.run_id)

    def test_run_renders_only_bound_dispatch_launch_settings(self):
        runtime = 'runtime-local'
        active_dispatch = 'ctx_current'

        def reply(result, origin=runtime):
            return self.completed({'ok': True, 'result': result, '_meta': {'runtimeId': origin}})

        def record(tid, did, status):
            return {'taskId': tid, 'dispatchId': did, 'runId': self.run_id,
                    'dispatchStatus': status, 'workerState': 'running' if status == 'dispatched' else 'succeeded'}

        def host(argv, **_):
            operation = argv[2]
            if operation == 'task-list':
                return reply(self.response()['result'])
            if operation == 'worker-list':
                return reply({'workers': [record('root', 'ctx_previous_root', 'completed'),
                                          record('parallel', 'ctx_previous', 'completed'),
                                          record('parallel', active_dispatch, 'dispatched')],
                              'scope': {'run': self.run_id}, 'page': {'hasMore': False}})
            if operation == 'dispatch-show':
                tid = argv[6]
                did, status = ('ctx_root', 'completed') if tid == 'root' else (active_dispatch, 'dispatched')
                return reply({'dispatch': {'run_id': self.run_id, 'task_id': tid, 'id': did, 'status': status}})
            self.assertEqual(operation, 'worker-show')
            did = argv[6]
            self.assertNotIn(did, ('ctx_previous_root', 'ctx_previous'))
            tid, status = ('root', 'completed') if did == 'ctx_root' else ('parallel', 'dispatched')
            applied = {'model': 'model-old', 'effort': 'high'} if did == 'ctx_current' else None
            if did == 'ctx_root':
                applied = {'model': 'model-root', 'effort': 'low'}
            launch = {'requested': applied if tid == 'root' else {'model': 'model-requested', 'effort': 'medium'},
                      'effective': applied}
            return reply({'dispatch': {'id': did, 'taskId': tid, 'runId': self.run_id, 'status': status},
                          'worker': {'dispatchId': did, 'startOptions': {'launch': launch}},
                          'terminal': {'preview': 'private preview excluded'}})

        cache = {}
        with patch.object(feed.subprocess, 'run', side_effect=host) as calls:
            snapshot = feed.load_run_snapshot(self.run_id, cache)
            active_dispatch = 'ctx_restarted'
            restarted = feed.load_run_snapshot(self.run_id, cache)
        self.assertEqual(snapshot['tasks'][1]['current_dispatch'], 'ctx_current')
        self.assertEqual(restarted['tasks'][1]['current_dispatch'], 'ctx_restarted')
        self.assertNotIn('effective', restarted['tasks'][1]['launch_settings'])
        self.assertEqual([call.args[0][6] for call in calls.call_args_list
                          if call.args[0][2] == 'worker-show'].count('ctx_root'), 1)
        self.assertNotIn('private preview excluded', json.dumps(snapshot))
        for layout in ('wide', 'focus', 'legacy'):
            states = [tui.navigation.State(layout=layout, selected=tid) for tid in ('root', 'parallel')]
            frame = '\n'.join(tui.render_frame(snapshot, 138, 30, page=page, layout=layout, state=state)
                              for state in states for page in range(tui.page_count(
                                  snapshot, 138, 30, layout=layout, state=state)))
            self.assertIn('Orca 적용: model-old / high', frame)
            self.assertIn('요청: model-requested / medium', frame)
            self.assertIn('Orca: completed', frame)
            for placeholder in ('분류 미확인', '모델 미확인', '전문가 미확인', '소속 미확인'):
                self.assertNotIn(placeholder, frame)
        self.assertNotIn('model-old', tui.render_frame(restarted, 138, 30))

    def test_foreign_or_unavailable_worker_keeps_task_and_clears_old_settings(self):
        runtime = 'local'
        task_reply = self.response()
        task_reply['_meta'] = {'runtimeId': runtime}
        worker_list = self.completed({'ok': True, '_meta': {'runtimeId': runtime}, 'result': {
            'scope': {'run': self.run_id}, 'page': {'hasMore': False}, 'workers': [
                {'runId': self.run_id, 'taskId': 'root', 'dispatchId': 'ctx_root',
                 'dispatchStatus': 'completed', 'workerState': 'succeeded'}]}})
        selected = self.completed({'ok': True, '_meta': {'runtimeId': runtime}, 'result': {
            'dispatch': {'task_id': 'root', 'run_id': self.run_id, 'id': 'ctx_root', 'status': 'completed'}}})
        foreign = self.completed({'ok': True, '_meta': {'runtimeId': 'foreign'}, 'result': {
            'dispatch': {'taskId': 'root', 'runId': self.run_id, 'id': 'ctx_root', 'status': 'completed'},
            'worker': {'dispatchId': 'ctx_root', 'startOptions': {'launch': {'effective': {'model': 'wrong-model'}}}}}})
        task_reply['result']['tasks'][1]['status'] = 'pending'
        with patch.object(feed.subprocess, 'run', side_effect=[
            self.completed(task_reply), worker_list, selected, foreign, self.completed(task_reply),
            subprocess.TimeoutExpired('orca', 1),
        ]):
            cache = {}
            for _ in range(2):
                snapshot = feed.load_run_snapshot(self.run_id, cache)
                self.assertEqual(len(snapshot['tasks']), 3)
                self.assertEqual(snapshot['tasks'][0]['host_status'], 'completed')
                self.assertNotIn('launch_settings', snapshot['tasks'][0])
                self.assertFalse(snapshot['overall_goal_acceptance']['earned_success'])
        self.assertFalse(cache)

    def test_mismatched_refresh_keeps_only_the_same_runs_last_good_frame(self):
        good = self.response()
        foreign = self.response()
        foreign['result']['runId'] = 'run_other'
        healthy = self.response()
        healthy['result']['tasks'][1]['status'] = 'completed'
        with patch.object(feed.subprocess, 'run', side_effect=[
            self.completed(good), self.completed(foreign), self.completed(healthy),
        ]):
            refresh = tui.RefreshState(None, .25, run_id=self.run_id)
            self.assertTrue(refresh.refresh(0))
            last_good = refresh.snapshot
            self.assertTrue(refresh.refresh(1))
            self.assertIs(refresh.snapshot, last_good)
            self.assertEqual(refresh.error, 'InputError')
            self.assertTrue(refresh.refresh(6))
            self.assertEqual(refresh.snapshot['tasks'][1]['host_status'], 'completed')
            self.assertIsNone(refresh.error)


def ordinary(root):
    # Existing actual Company schema corpus, deliberately labelled synthetic.
    record = copy.deepcopy(json.loads((ASSETS / 'record-cases.json').read_text())['cases'][0]['record'])
    record['goal'].update(status='active', known_failure=False, assessment=None)
    dump(root / 'record.json', record)
    return record


class RecordPTY(OwnedPTY):
    """Reuse original cleanup/termios assertions, but launch --record, not a manifest."""
    def __init__(self, root, width=80, height=12):
        # OwnedPTY constructor invokes Popen only once. Replace just its argv at
        # the harness boundary, never a product loader/checker.
        original = subprocess.Popen
        def launch(argv, **kwargs):
            argv = list(argv)
            position = argv.index('--manifest')
            argv[position:position+2] = ['--record', str(Path(root) / 'record.json')]
            return original(argv, **kwargs)
        with patch.object(subprocess, 'Popen', side_effect=launch):
            super().__init__(root, width, height)


class InputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.record = ordinary(self.root)
        self.path = self.root / 'record.json'
        environment = child_env(self.root)
        if os.environ.get('COMPANY_TUI_TEST_EVIDENCE'):
            environment['COMPANY_TUI_TEST_EVIDENCE'] = os.environ['COMPANY_TUI_TEST_EVIDENCE']
        self.environment = patch.dict(os.environ, environment, clear=True)
        self.environment.start(); self.addCleanup(self.environment.stop)

    def load(self, metadata=None):
        return feed.load_record_snapshot(self.path, metadata_path=metadata)

    def save(self): dump(self.path, self.record)

    def test_automatic_run_view_requires_owned_binding_and_claims_once(self):
        handle = 'term_owner'
        run = {'id': 'run_selected', 'coordinator_handle': handle, 'legacy': 0}
        terminal = {'handle': handle, 'tabId': 'tab', 'leafId': 'owner-leaf', 'connected': True,
                    'orphaned': False, 'writable': True, 'executionHostId': 'local'}
        splits = []
        binding = None

        def reply(_orca, *args, **_kwargs):
            if args[0] == 'orchestration':
                return {'run': binding}
            if args[1] == 'show':
                return {'terminal': terminal}
            splits.append(args)
            return {'split': {'handle': 'term_view', 'tabId': 'tab', 'leafId': 'view-leaf'}}

        with patch.dict(os.environ, {'ORCA_TERMINAL_HANDLE': handle}), patch.object(opener, 'orca_result', side_effect=reply):
            self.assertEqual(opener.open_current()['status'], 'skipped')
            binding = {**run, 'coordinator_handle': 'term_other'}
            self.assertEqual(opener.open_current()['status'], 'skipped')
            self.assertEqual(splits, [])
            binding = run
            self.assertEqual(opener.open_current()['run_id'], 'run_selected')
            with patch.dict(os.environ, {'CODEX_HOME': str(self.root / 'other-codex')}):
                self.assertEqual(opener.open_current()['status'], 'already_requested')
            self.assertEqual(len(splits), 1)
            self.assertEqual(splits[0][2:4], ('--terminal', handle))
            self.assertIn('--run run_selected', splits[0][-1])
            binding = {**run, 'id': 'run_new'}
            self.assertEqual(opener.open_current()['status'], 'pane_accepted')
            self.assertEqual(len(splits), 2)

    def test_automatic_run_view_rechecks_binding_and_does_not_retry_unknown_split(self):
        handle = 'term_owner'
        run = {'id': 'run_selected', 'coordinator_handle': handle, 'legacy': 0}
        terminal = {'handle': handle, 'tabId': 'tab', 'leafId': 'owner-leaf', 'connected': True,
                    'orphaned': False, 'writable': True, 'executionHostId': 'local'}
        with patch.dict(os.environ, {'ORCA_TERMINAL_HANDLE': handle}), patch.object(opener, 'orca_result', side_effect=[
            {'run': run}, {'terminal': terminal}, {'run': {**run, 'id': 'run_foreign'}},
            {'run': run}, {'terminal': terminal}, {'run': run}, subprocess.TimeoutExpired('orca', 12),
            {'run': run}, {'terminal': terminal}, {'run': run},
        ]) as command:
            self.assertEqual(opener.open_current()['reason'], 'run_binding_changed')
            self.assertEqual(opener.open_current()['status'], 'split_unconfirmed')
            self.assertEqual(opener.open_current()['status'], 'already_requested')
        self.assertEqual(sum(call.args[1:3] == ('terminal', 'split') for call in command.call_args_list), 1)

    def test_ordinary_no_manifest_unknowns_and_byte_identity(self):
        snap = self.load(); task = snap['tasks'][0]
        self.assertTrue(snap['check']['ok'], snap['check'])
        self.assertEqual(task['state'], 'ACC')
        self.assertEqual(task['title'], '?')
        for field in ('classification', 'team_id', 'assigned_actor', 'assigned_model'):
            self.assertIsNone(task[field])
        self.assertEqual(task['specialist']['status'], 'unknown')
        self.assertIsNone(snap['organization'])
        self.assertEqual(snap['dependency_coverage'], 'unknown')
        self.assertEqual(snap['live_host_state'], 'unknown')
        observed = snap['record_observation']
        self.assertEqual(observed['path'], str(self.path))
        self.assertEqual(observed['sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(observed['identity']['inode'], self.path.stat().st_ino)
        self.assertEqual(snap['binding']['record_sha256'], observed['sha256'])
        self.assertEqual(snap['input_mode'], 'record')
        self.assertEqual(set(p.name for p in self.root.iterdir()), {'record.json'})

    def test_read_only_no_files_or_mtimes_changed(self):
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir()}
        self.load(); self.load()
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir()})

    def test_updates_and_whole_revision_no_repin_required(self):
        first = self.load()
        self.record['tasks'][0]['parent_integration'] = None; self.save()
        second = self.load()
        self.assertEqual(second['tasks'][0]['state'], 'SUB')
        self.assertNotEqual(first['binding']['record_sha256'], second['binding']['record_sha256'])
        self.record['goal']['revision'] = 'r2'
        self.record['goal'].update(status='pending', owner_acceptance='pending')
        self.record['tasks'][0]['goal_revision'] = 'r2'; self.save()
        self.assertEqual(self.load()['binding']['revision'], 'r2')

    def test_requested_model_only_not_model_role_staffing_inference(self):
        task = self.record['tasks'][0]
        task['model'].update(requested='explicit-model', observed='observed-not-assigned')
        task.update(title='unchecked annotation', classification='code', team_id='imaginary')
        self.save(); projected = self.load()['tasks'][0]
        self.assertEqual(projected['assigned_model'], 'explicit-model')
        self.assertEqual(projected['model_basis'], 'assigned')
        self.assertEqual(projected['title'], '?')
        self.assertIsNone(projected['classification']); self.assertIsNone(projected['team_id'])
        self.assertIsNone(projected['assigned_actor'])
        self.assertEqual(projected['specialist']['status'], 'unknown')

    def test_current_routing_model_and_contradiction(self):
        task = self.record['tasks'][0]
        task['routing_decision'] = {'binding': {'task': task['id'], 'attempt': task['current_dispatch'],
            'scope': task['goal_scope'], 'revision': task['goal_revision']}, 'selected': {'model': 'routed'}}
        self.save(); self.assertEqual(self.load()['tasks'][0]['assigned_model'], 'routed')
        task['model']['requested'] = 'contradiction'; self.save()
        with self.assertRaises(data.InputError): self.load()
        task['model']['requested'] = None
        task['routing_decision']['binding']['attempt'] = 'old'; self.save()
        with self.assertRaises(data.InputError): self.load()

    def test_checker_errors_preserved_not_invented_success(self):
        self.record['tasks'][0]['technical']['candidate'] = 'old'; self.save()
        snap = self.load()
        self.assertFalse(snap['check']['ok'])
        self.assertTrue(snap['check']['errors'])
        self.assertNotEqual(snap['tasks'][0]['state'], 'ACC')
        self.assertFalse(snap['overall_goal_acceptance']['earned_success'])

    def test_missing_model_and_live_do_not_become_run(self):
        task = self.record['tasks'][0]
        task.update(technical=None, parent_integration=None)
        task['execution'].update(state='live', result=None); self.save()
        snap = self.load()
        self.assertEqual(snap['tasks'][0]['state'], '?')
        self.assertEqual(snap['observed_overlap'], 'unknown')

    def test_malformed_duplicate_nan_schema_and_current_revision_reject(self):
        for raw in ('{', '{"version":1,"version":1}', '{"x":NaN}', '[]'):
            self.path.write_text(raw)
            with self.subTest(raw=raw), self.assertRaises(data.InputError): self.load()
        self.record['version'] = 2; self.save()
        with self.assertRaises(data.InputError): self.load()
        self.record['version'] = True; self.save()
        with self.assertRaises(data.InputError): self.load()
        self.record['version'] = 1
        self.record['tasks'][0]['goal_revision'] = 'old'; self.save()
        with self.assertRaises(data.InputError): self.load()

    def test_symlink_directory_and_oversized_reject(self):
        link = self.root / 'link.json'; link.symlink_to(self.path)
        for path in (link, self.root):
            with self.assertRaises(data.InputError): feed.load_record_snapshot(path)
        with patch.object(data, 'MAX_BYTES', 5):
            with self.assertRaises(data.InputError): self.load()

    def test_explicit_evidence_pin_is_immutable_and_transitive_visible(self):
        external = self.root / 'result.txt'
        external.write_bytes(b'owned fixture evidence')
        self.record['evidence']['result'].update(file='result.txt', sha256=hashlib.sha256(external.read_bytes()).hexdigest())
        self.save(); snap = self.load()
        self.assertTrue(any(pin['path'] == str(external) for pin in snap['input_observations']))
        external.write_bytes(b'changed without declared pin update')
        with self.assertRaises(data.InputError): self.load()

    def test_explicit_catalog_receipts_are_tracked_not_arbitrary_json_paths(self):
        digest = dump(self.root/'status.json', {'ok': True})
        manifest = {'format': 'company-host-catalog-metadata/v1',
                    'receipts': [{'file': 'status.json', 'sha256': digest}]}
        pin = dump(self.root/'manifest.json', manifest)
        self.record['evidence']['plan'].update(file='manifest.json', sha256=pin)
        self.save(); snap = self.load()
        self.assertIn(str(self.root/'status.json'), [p['path'] for p in snap['input_observations']])
        (self.root/'status.json').write_text('{}')
        with self.assertRaises(data.InputError): self.load()

    def test_record_and_external_identity_race_rejected(self):
        external = self.root/'result.txt'; external.write_text('same bytes')
        self.record['evidence']['result'].update(file='result.txt', sha256=hashlib.sha256(external.read_bytes()).hexdigest())
        self.save()
        original = data.status_view.build_view
        for target in (self.path, external):
            def race(*args, **kwargs):
                result = original(*args, **kwargs)
                replacement = self.root/'replace.json'
                replacement.write_bytes(target.read_bytes()); replacement.replace(target)
                return result
            with self.subTest(target=target), patch.object(data.status_view, 'build_view', side_effect=race):
                with self.assertRaises(data.InputError): self.load()

    def test_optional_metadata_usable_and_never_auto_repinned(self):
        manifest, self.record, _, _ = fixture(self.root, count=1)
        self.assertEqual(self.load(self.root/'view.json')['tasks'][0]['title'], '작업 1')
        self.record['tasks'][0]['parent_integration'] = None; self.save()
        original = (self.root/'view.json').read_bytes()
        with self.assertRaises(data.InputError): self.load(self.root/'view.json')
        self.assertEqual((self.root/'view.json').read_bytes(), original)
        self.assertEqual(self.load()['tasks'][0]['state'], 'SUB')

    def test_optional_metadata_wrong_record_path_and_revision_reject(self):
        manifest, self.record, _, _ = fixture(self.root, count=1)
        other = self.root/'other.json'; other.write_bytes(self.path.read_bytes())
        with self.assertRaises(data.InputError): feed.load_record_snapshot(other, self.root/'view.json')
        manifest['binding']['revision'] = 'old'; dump(self.root/'view.json', manifest)
        with self.assertRaises(data.InputError): self.load(self.root/'view.json')

    def test_refresh_last_good_whole_replacement_and_recovery(self):
        refresh = tui.RefreshState(self.path, .25, record=True)
        self.assertTrue(refresh.refresh(0)); good = refresh.snapshot
        self.record['tasks'][0]['goal_revision'] = 'old'; self.save()
        self.assertTrue(refresh.refresh(.25)); self.assertIs(refresh.snapshot, good)
        self.assertIsNotNone(refresh.error)
        self.record['tasks'][0]['goal_revision'] = 'r1'
        self.record['tasks'][0]['parent_integration'] = None; self.save()
        self.assertFalse(refresh.refresh(1))
        self.assertTrue(refresh.refresh(5.25)); self.assertIsNone(refresh.error)
        self.assertEqual(refresh.snapshot['tasks'][0]['state'], 'SUB')
        self.assertIsNone(refresh.snapshot['organization'])

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *map(str,args)],
            capture_output=True, text=True, env=child_env(self.root), timeout=10)

    def test_actual_cli_record_json_frame_and_mutual_exclusion(self):
        result = self.cli('--record', self.path, '--once', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['input_mode'], 'record')
        frame = self.cli('--record', self.path, '--once', '--width', 80, '--height', 12)
        self.assertEqual(frame.returncode, 0, frame.stderr)
        self.assertIn('조직 미기록', frame.stdout)
        for args in ((), ('--record', self.path, '--manifest', self.path),
                     ('--manifest', self.path, '--metadata', self.path)):
            self.assertEqual(self.cli(*args).returncode, 2)

    def test_original_manifest_cli_and_optional_metadata(self):
        manifest, self.record, _, _ = fixture(self.root, count=1)
        for args in (('--manifest', self.root/'view.json'),
                     ('--record', self.path, '--metadata', self.root/'view.json')):
            result = self.cli(*args, '--once', '--json')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['tasks'][0]['title'], '작업 1')
        self.record['tasks'][0]['parent_integration'] = None; self.save()
        self.assertEqual(self.cli('--manifest',self.root/'view.json','--once').returncode,2)

    def test_actual_owned_record_pty_updates_errors_recovery(self):
        terminal = RecordPTY(self.root); self.addCleanup(terminal.close)
        timeline = []
        def await_token(token, limit=7):
            start=time.monotonic(); output=terminal.until(token, timeout=limit)
            timeline.append({'token':token,'elapsed_seconds':time.monotonic()-start})
            return output
        await_token('작업 검토 통과')
        before=len(terminal.raw); terminal.collect(.6)
        self.assertEqual(len(terminal.raw),before)
        self.record['tasks'][0]['parent_integration']=None; self.save()
        await_token('제출·검토 대기')
        self.path.write_text('{')
        failed=await_token('ERROR | last-good')
        self.assertIn('제출·검토 대기'.encode(),failed)
        self.save(); restored=await_token('\x1b[H\x1b[2JCompany [combined]')
        # One PTY read may include the preceding age repaint AND the recovered
        # frame. Check the actual final repaint, not the accumulated byte batch.
        self.assertNotIn(b'ERROR | last-good', restored.rsplit(b'\x1b[H\x1b[2J', 1)[-1])
        self.record['tasks'][0]['goal_revision']='old'; self.save()
        failed=await_token('ERROR | last-good'); self.assertIn('제출·검토 대기'.encode(),failed)
        self.record['tasks'][0]['goal_revision']='r1'; self.save()
        await_token('\x1b[H\x1b[2JCompany [combined]')
        external=self.root/'result.txt'; external.write_text('pinned owned evidence')
        self.record['evidence']['result'].update(file='result.txt',sha256=hashlib.sha256(external.read_bytes()).hexdigest())
        self.record['tasks'][0]['parent_integration']=copy.deepcopy(json.loads((ASSETS/'record-cases.json').read_text())['cases'][0]['record']['tasks'][0]['parent_integration'])
        self.save(); await_token('작업 검토 통과')
        external.write_text('source drift')
        failed=await_token('ERROR | last-good'); self.assertIn('작업 검토 통과'.encode(),failed)
        external.write_text('pinned owned evidence')
        await_token('\x1b[H\x1b[2JCompany [combined]')
        receipt=terminal.close(signal.SIGTERM)
        for flag in ('semantic_restored','cursor_shown','alternate_left','reaped','fds_closed'):
            self.assertTrue(receipt[flag],receipt)
        self.assertEqual(receipt['exit'],0,receipt)
        self.assertEqual(set(p.name for p in self.root.iterdir()),{'record.json','result.txt'})
        evidence=os.environ.get('COMPANY_TUI_TEST_EVIDENCE')
        if evidence: dump(Path(evidence)/'record-feed-timeline.json',timeline)


if __name__ == '__main__': unittest.main()
