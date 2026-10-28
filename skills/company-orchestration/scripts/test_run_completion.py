#!/usr/bin/env python3
"""Destructive-boundary tests using only small owned /private/tmp fixtures."""
import contextlib
import argparse
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import run_completion as rc
import completion_hook as hook
import outcome_eval as ev


def ordinary_routing():
    selected = {'route': 'agy', 'family': 'flash', 'model': 'synthetic-flash', 'effort': 'high',
                'supported': True, 'evidence': 'route-ev', 'reason_evidence': 'route-ev'}
    return {
        'version': 1,
        'binding': {'task': 'task-1', 'scope': 'approved-scope', 'revision': 'r1',
                    'attempt': 'dispatch-current', 'planned': False},
        'trigger': 'initial', 'failure_class': None, 'prior': None, 'selected': selected,
        'alternatives': [{'route': 'agy', 'family': 'flash', 'model': 'synthetic-flash', 'effort': 'high',
                          'disposition': 'selected', 'reason': 'ordinary_assignment', 'evidence': 'route-ev'}],
        'selected_reason': 'ordinary_assignment',
        'constraints': {'task': 'bounded_simple', 'quality': 'unknown', 'tool': 'supported',
                        'billing': 'subscription', 'context': 'fresh'},
        'boundary': {'review': 'pending', 'reconsider': 'none', 'scope': 'approved-scope',
                     'next': 'none', 'inherits': False},
        'receipt_evidence': 'receipt-ev'}


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='/private/tmp', prefix='company-retention-test-')
        self.addCleanup(self.temp.cleanup)
        config = Path(self.temp.name) / 'user.md'
        config.write_text('---\nschema_version: 1\npreset: single\nservices: ["antigravity"]\n---\n\n# Synthetic route intent\n')
        env = patch.dict(os.environ, {'AGENT_COMPANY_CONFIG': str(config)})
        env.start()
        self.addCleanup(env.stop)
        self.home = Path(self.temp.name) / 'sejong'
        self.root = self.home / 'runs/flat-run'
        self.root.mkdir(parents=True)
        (self.root / 'scratch').mkdir()
        (self.root / 'scratch/raw').write_text('temporary input')
        (self.root / 'report.md').write_text('compact required evidence')
        (self.root / 'acceptance.json').write_text('{"accepted":true}')
        self.run_cli('init', '--run-id', 'goal-1', '--owner', 'B')
        self.run_cli('register', '--disposable', 'scratch/raw', '--preserve', 'report.md',
                     '--preserve', 'acceptance.json')
        suite = json.loads((Path(__file__).parent.parent / 'assets/record-cases.json').read_text())
        self.record = copy.deepcopy(next(x['record'] for x in suite['cases']
                                        if x['name'] == 'required-resource-record-valid')) if any(
                                            x['name'] == 'required-resource-record-valid' for x in suite['cases']) else copy.deepcopy(suite['cases'][0]['record'])
        self.record['label'] = 'real'
        self.record['resource_accounting'] = 'required'
        self.record['goal'].update(status='succeeded', known_failure=False)
        self.record['goal']['assessment'].update(verdict='succeeded')
        for evidence in self.record['evidence'].values():
            evidence['kind'] = 'host'
        self.record['evidence']['route-ev'] = {'ref': 'fixture://route', 'sha256': None, 'kind': 'host'}
        self.record['evidence']['receipt-ev'] = {'ref': 'fixture://routing-receipt', 'sha256': None, 'kind': 'host'}
        self.record['routing_accounting'] = 'required'
        for task in self.record['tasks']:
            task['routing_decision'] = ordinary_routing()
        self.record['evidence']['assessment'].update(kind='independent', file='acceptance.json',
                                                     sha256=rc.sha((self.root / 'acceptance.json').read_bytes()))
        for task in self.record['tasks']:
            task['resource_preflight'] = {'host':'fixture', 'cpu':'12', 'ram':'32GB',
                                         'disk':'small fixture', 'evidence':'result'}
            task['resources'] = []
        self.record['artifact_retention'] = {'run_id':'goal-1', 'manifest_sha256':self.manifest_hash(),
                                              'consumers':[], 'quiescent':True}
        self.save_record()

    def save_record(self):
        (self.root / 'record.json').write_text(json.dumps(self.record))

    def manifest_hash(self):
        return rc.sha((self.root / rc.MANIFEST).read_bytes())

    def run_cli(self, command, *extras):
        args = [command, '--run', str(self.root), '--sejong-home', str(self.home), *extras]
        if command != 'init':
            args += ['--expect-manifest-sha256', self.manifest_hash()]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = rc.main(args)
        value = json.loads(out.getvalue())
        self.assertEqual(code, 0, value)
        return value

    def finish(self, probe=lambda root: {'status':'synthetic no activity'}):
        root, fd = rc.open_run(self.home, self.root)
        try:
            data = (root / rc.MANIFEST).read_bytes()
            return rc.complete(root, fd, rc.decode(data), rc.sha(data), 'record.json', probe)
        finally:
            os.close(fd)

    def assert_preserved(self, value):
        self.assertEqual(value['status'], 'blocked', value)
        self.assertTrue((self.root / 'scratch/raw').exists(), value)
        self.assertEqual((self.root / 'report.md').read_text(), 'compact required evidence')

    def test_success_and_idempotent_retry(self):
        first = self.finish()
        self.assertEqual(first['status'], 'completed', first)
        self.assertFalse((self.root / 'scratch/raw').exists())
        self.assertEqual(self.finish()['removed'], first['removed'])
        self.assertTrue((self.root / 'report.md').exists())
        self.assertTrue((self.root / 'acceptance.json').exists())

    def study(self, environment_failure=False, task_name='evidence-reconcile'):
        """Real-shaped, entirely fabricated receipts; no provider or real Run."""
        for name in ('baseline', 'candidate', 'context'):
            (self.root / name).write_text(name)
        bundle = self.root / 'study'
        frozen = ev.freeze(argparse.Namespace(
            spec=Path(__file__).parent.parent / 'assets/outcome-eval/tasks.json',
            baseline=self.root / 'baseline', candidate=self.root / 'candidate', context=self.root / 'context',
            out=bundle, source_commit='synthetic', agent='codex', model='synthetic-flash', effort='high',
            tasks=task_name, repeats=1, evidence_class='real'))
        plan_path = bundle / 'plan.json'
        plan = ev.decode(plan_path.read_bytes())
        mapping = {}
        for i, trial in enumerate(plan['expected_trials']):
            tid = trial['id']
            args = argparse.Namespace(plan=plan_path, plan_sha256=frozen['plan_sha256'], trial=tid,
                                      workspace=self.root / ('workspace-' + str(i)))
            prepared = ev.prepare(args)
            actor, task_id, dispatch = 'trial-worker-' + str(i), 'trial-' + str(i), 'attempt-' + str(i)
            selection = {k: plan['common'][k] for k in ('agent', 'model', 'effort')}
            launch = self.root / 'launch.json'
            failed_start = environment_failure and i == 0
            launch.write_text(json.dumps({'ok': True, 'result': {
                'runId': 'goal-1', 'taskId': task_id, 'dispatchId': dispatch,
                'state': 'failed' if failed_start else 'ready',
                'failedStage': 'agent_readiness' if failed_start else None,
                'launch': {'requested': selection, 'effective': selection},
                'effects': [{'kind': 'terminal', 'role': 'agent', 'id': actor}]}}))
            outcome = 'failed' if i == 0 else 'succeeded'
            changed = []
            if i == 1:
                oracle = plan['tasks'][trial['task']]['oracle']
                solution = (json.dumps(oracle['expected']) if oracle['kind'] == 'json_equal' else
                            'def visible(start, end, threshold=600):\n'
                            '    return end is not None and end >= start and end-start >= threshold\n')
                (args.workspace / oracle['path']).write_text(solution)
                changed.append(oracle['path'])
            done = self.root / 'done.json'
            done.write_text(json.dumps({'ok': True, 'result': {'message': {
                'run_id': 'goal-1', 'from_handle': actor, 'type': 'worker_done',
                'payload': {'taskId': task_id, 'dispatchId': dispatch, 'outcome': outcome, 'filesModified': changed}}}}))
            trace = self.root / 'trace.txt'
            trace.write_text('synthetic trace only')
            collected = ev.collect(argparse.Namespace(**vars(args), brief=Path(prepared['brief_path']),
                launch=launch, done=None if failed_start else done, trace=None if failed_start else trace,
                status='environment_failure' if failed_start else 'failure' if i == 0 else 'success', usage=None))
            if not failed_start:
                review = collected['review_template']
                review.update(assessor='fixture-reviewer', critical_failure=False, note='synthetic independent review')
                (bundle / 'trials' / tid / 'review.json').write_text(json.dumps(review))
            raw = ev.decode((bundle / 'trials' / tid / 'record.json').read_bytes())
            task = copy.deepcopy(self.record['tasks'][0])
            candidate = ev.trial_binding(plan, frozen['plan_sha256'], trial)['candidate_sha256']
            task.update(id=task_id, current_dispatch=dispatch, candidate=candidate, technical=None, parent_integration=None)
            receipt = raw['launch' if failed_start else 'worker_done']
            task['execution'] = {'state': 'settled', 'actor': actor, 'result': {
                'task': task_id, 'dispatch': dispatch, 'candidate': candidate,
                'evidence': 'file:' + 'study/' + receipt['path'], 'outcome': outcome}}
            task['routing_decision']['binding'].update(task=task_id, attempt=dispatch)
            self.record['tasks'].append(task)
            mapping[tid] = task_id
        report = ev.score(argparse.Namespace(plan=plan_path, plan_sha256=frozen['plan_sha256'], allow_task_code=True))
        (bundle / 'report.json').write_text(json.dumps(report))
        for path in bundle.rglob('*'):
            if path.is_file():
                ref = path.relative_to(self.root).as_posix()
                self.record['evidence']['file:' + ref] = {
                    'ref': 'fixture://' + ref, 'file': ref, 'sha256': rc.sha(path.read_bytes()), 'kind': 'host'}
        self.record['study_completion'] = {'mode': 'accepted_study', 'plan': 'file:study/plan.json',
                                         'report': 'file:study/report.json', 'trials': mapping}
        preserved = [str(path.relative_to(self.root)) for path in bundle.rglob('*') if path.is_file()]
        self.run_cli('register', *[arg for ref in preserved for arg in ('--preserve', ref)])
        self.record['artifact_retention']['manifest_sha256'] = self.manifest_hash()
        self.save_record()

    def test_accepted_study_retains_failed_trial_and_raw_evidence(self):
        self.study()
        report = json.loads((self.root / 'study/report.json').read_text())
        self.assertEqual(sorted(t['status'] for t in report['trials'].values()), ['failure', 'success'])
        self.assertEqual(self.finish()['status'], 'completed')
        self.assertEqual(self.record['tasks'][1]['execution']['result']['outcome'], 'failed')
        self.assertTrue((self.root / 'study/trials/evidence-reconcile-baseline-1/worker_done.txt').exists())

    def test_observed_failed_readiness_needs_no_invented_done_or_trace(self):
        self.study(environment_failure=True)
        raw = ev.decode((self.root / 'study/trials/evidence-reconcile-baseline-1/record.json').read_bytes())
        self.assertIsNone(raw['worker_done'])
        self.assertIsNone(raw['trace'])
        self.assertEqual(self.finish()['status'], 'completed')

    def test_study_opt_in_does_not_waive_production_failure(self):
        self.study()
        original = copy.deepcopy(self.record['tasks'][0])
        for field in ('execution', 'technical', 'parent_integration'):
            self.record['tasks'][0] = copy.deepcopy(original)
            target = self.record['tasks'][0][field]
            if field == 'execution':
                target['result']['outcome'] = 'failed'
            else:
                target['verdict'] = 'failed'
            self.save_record()
            self.assert_preserved(self.finish())

    def test_old_default_still_blocks_trial_failure(self):
        self.study()
        del self.record['study_completion']
        self.save_record()
        self.assert_preserved(self.finish())

    def test_missing_duplicate_stale_trial_mapping(self):
        self.study()
        contract = self.record['study_completion']
        original = copy.deepcopy(contract['trials'])
        cases = [{}, dict.fromkeys(original, 'trial-0'), {**original, next(iter(original)): 'task-1'}]
        for mapping in cases:
            with self.subTest(mapping=mapping):
                contract['trials'] = mapping
                self.save_record()
                self.assert_preserved(self.finish())

    def test_live_unknown_stale_candidate_and_dispatch_stay_blocking(self):
        self.study()
        task = self.record['tasks'][1]
        original = copy.deepcopy(task)
        for key, value in [('state', 'live'), ('state', 'unknown'), ('candidate', 'stale'), ('current_dispatch', 'old')]:
            task.clear()
            task.update(copy.deepcopy(original))
            if key == 'state':
                task['execution']['state'] = value
            else:
                task[key] = value
            self.save_record()
            self.assert_preserved(self.finish())

    def test_study_report_missing_unaccepted_or_self_approved(self):
        self.study()
        original = copy.deepcopy(self.record)
        for change in ('missing', 'pending', 'owner', 'executor'):
            self.record = copy.deepcopy(original)
            if change == 'missing':
                self.record['evidence']['file:study/report.json'].pop('file')
            elif change == 'pending':
                self.record['goal']['assessment']['verdict'] = 'pending'
            else:
                self.record['goal']['assessment'].update(basis='human', actor='B' if change == 'owner' else 'trial-worker-0')
            self.save_record()
            self.assert_preserved(self.finish())

    def test_study_missing_evidence_unknown_report_or_relabelled_result(self):
        self.study()
        original = copy.deepcopy(self.record)
        path = self.root / 'study/report.json'
        report_bytes = path.read_bytes()
        for change in ('evidence', 'unknown', 'relabel', 'missing-trial'):
            self.record = copy.deepcopy(original)
            path.write_bytes(report_bytes)
            if change == 'evidence':
                del self.record['evidence']['file:study/inputs/context.txt']
            elif change == 'relabel':
                self.record['tasks'][1]['execution']['result']['outcome'] = 'succeeded'
            else:
                report = json.loads(path.read_text())
                tid = next(iter(report['trials']))
                if change == 'unknown':
                    report['trials'][tid]['status'] = 'unknown'
                else:
                    del report['trials'][tid]
                path.write_text(json.dumps(report))
                self.record['evidence']['file:study/report.json']['sha256'] = rc.sha(path.read_bytes())
            self.save_record()
            self.assert_preserved(self.finish())

    def test_study_still_requires_consumers_quiescence_and_retained_evidence(self):
        self.study()
        original = copy.deepcopy(self.record)
        for change in ('consumer', 'writer', 'preserve'):
            self.record = copy.deepcopy(original)
            if change == 'consumer':
                self.record['artifact_retention']['consumers'] = [{'id': 'late-reader', 'state': 'live'}]
            elif change == 'writer':
                self.record['artifact_retention']['quiescent'] = False
            else:
                (self.root / 'study/inputs/context.txt').write_text('changed')
            self.save_record()
            self.assert_preserved(self.finish())

    def refreeze_study_fixture(self):
        """Test-only: bind a changed, newly accepted synthetic report, not stale bytes.

        Production register cannot replace an existing declaration this way.
        This isolates semantic validation from the unchanged-file guard.
        """
        for item in self.record['evidence'].values():
            if item.get('file', '').startswith('study/'):
                item['sha256'] = rc.sha((self.root / item['file']).read_bytes())
        path = self.root / rc.MANIFEST
        manifest = json.loads(path.read_text())
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            manifest['preserve'] = [rc.snapshot_file(fd, item['path']) for item in manifest['preserve']]
        finally:
            os.close(fd)
        path.write_text(json.dumps(manifest))
        self.record['artifact_retention']['manifest_sha256'] = self.manifest_hash()
        self.save_record()

    def test_semantically_incomplete_frozen_report_is_rejected(self):
        self.study()
        path = self.root / 'study/report.json'
        original = json.loads(path.read_text())
        for change in ('empty-arms', 'null-aggregates', 'missing-oracle', 'unknown-trial', 'missing-trial'):
            report = copy.deepcopy(original)
            if change == 'empty-arms':
                report['arms'] = {}
            elif change == 'null-aggregates':
                report.update(arms=None, gate=None, critical_failure_trials=None)
            elif change == 'missing-oracle':
                next(t for t in report['trials'].values() if t['status'] == 'failure')['oracle'] = None
            elif change == 'unknown-trial':
                next(iter(report['trials'].values()))['status'] = 'unknown'
            else:
                del report['trials'][next(iter(report['trials']))]
            path.write_text(json.dumps(report))
            self.refreeze_study_fixture()
            self.assert_preserved(self.finish())

    def test_raw_critical_review_cannot_be_hidden_by_saved_success(self):
        self.study()
        path = self.root / 'study/report.json'
        report = json.loads(path.read_text())
        tid = next(tid for tid, trial in report['trials'].items() if trial['status'] == 'success')
        review_path = self.root / 'study/trials' / tid / 'review.json'
        review = json.loads(review_path.read_text())
        review['critical_failure'] = True
        review_path.write_text(json.dumps(review))
        report['trials'][tid]['review_sha256'] = rc.sha(review_path.read_bytes())
        path.write_text(json.dumps(report))
        self.refreeze_study_fixture()
        self.assert_preserved(self.finish())

    def test_fully_reported_critical_trial_can_complete_only_accepted_evidence_deliverable(self):
        self.study()
        bundle = self.root / 'study'
        path = bundle / 'report.json'
        old_report = json.loads(path.read_text())
        tid = next(tid for tid, trial in old_report['trials'].items() if trial['status'] == 'success')
        review_path = bundle / 'trials' / tid / 'review.json'
        review = json.loads(review_path.read_text())
        review['critical_failure'] = True
        review_path.write_text(json.dumps(review))
        report = ev.score(argparse.Namespace(plan=bundle / 'plan.json', plan_sha256=old_report['plan_sha256'],
                                            allow_task_code=False))
        self.assertEqual(report['gate'], 'critical_failure')
        self.assertIn(tid, report['critical_failure_trials'])
        path.write_text(json.dumps(report))
        self.refreeze_study_fixture()
        self.assertEqual(self.finish()['status'], 'completed')

    def test_saved_python_oracle_is_checked_without_execution_at_completion(self):
        self.study(task_name='boundary-repair')
        with patch.object(ev.subprocess, 'run', side_effect=AssertionError('completion must not execute task code')):
            self.assertEqual(self.finish()['status'], 'completed')

    def test_saved_python_oracle_exit_output_types_and_verdict_must_agree(self):
        self.study(task_name='boundary-repair')
        path = self.root / 'study/report.json'
        original = json.loads(path.read_text())
        for change in ('missing', 'boolean-exit', 'false-case', 'nonzero-exit'):
            report = copy.deepcopy(original)
            trial = next(t for t in report['trials'].values() if t['status'] == 'success')
            if change == 'missing':
                trial['oracle'] = None
            elif change == 'boolean-exit':
                trial['oracle']['exit_code'] = False
            elif change == 'false-case':
                trial['oracle']['stdout'] = '[false]'
            else:
                trial['oracle']['exit_code'] = 1
            path.write_text(json.dumps(report))
            self.refreeze_study_fixture()
            with patch.object(ev.subprocess, 'run', side_effect=AssertionError('must not execute task code')):
                self.assert_preserved(self.finish())

    def test_changed_quarantine_after_activity_probe_is_preserved(self):
        calls = 0
        def probe(root):
            nonlocal calls
            calls += 1
            if calls == 3:
                next((root / 'scratch').glob('.completion-quarantine-*')).write_text('new writer data')
            return {'status': 'synthetic closed writer'}
        self.assert_preserved(self.finish(probe))
        self.assertEqual((self.root / 'scratch/raw').read_text(), 'new writer data')

    def test_corrupt_receipt_is_rejected_without_overwrite(self):
        self.assertEqual(self.finish()['status'], 'completed')
        path = self.root / rc.RECEIPT
        original = json.loads(path.read_text())
        cases = [dict(format='garbage'), dict(status='banana'), dict(run_id='wrong'),
                 dict(removed=[]), dict(removed=original['removed'] * 2), dict(pending=None),
                 dict(removed=[{**original['removed'][0], 'sha256': '0' * 64}])]
        for changed in cases:
            with self.subTest(changed=changed):
                data = json.dumps({**original, **changed})
                path.write_text(data)
                self.assertEqual(self.finish()['status'], 'blocked')
                self.assertEqual(path.read_text(), data)

    def test_present_empty_receipt_preserves_target_and_receipt(self):
        path = self.root / rc.RECEIPT
        path.write_text('{}')
        self.assert_preserved(self.finish())
        self.assertEqual(path.read_text(), '{}')

    def test_corrupt_receipt_prevents_session_rebinding(self):
        hook.register_session(self.home, 'session', self.root, 'goal-1', 'B', self.root, 'record.json')
        target = hook.binding_path(self.home, 'session')
        before = target.read_bytes()
        self.assertEqual(self.finish()['status'], 'completed')
        receipt = self.root / rc.RECEIPT
        value = json.loads(receipt.read_text())
        value['removed'][0]['sha256'] = '0' * 64
        receipt.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            hook.register_session(self.home, 'session', self.home / 'runs/new', 'goal-2', 'B',
                                  self.root, 'record.json', rc.sha(before))
        self.assertEqual(target.read_bytes(), before)

    def test_incomplete_rejected_team_checks_and_missing_acceptance(self):
        for status, verdict, basis in [('active','pending','independent'), ('failed','failed','independent'),
                                       ('succeeded','succeeded','team_checks')]:
            self.record['goal'].update(status=status)
            self.record['goal']['assessment'].update(verdict=verdict, basis=basis)
            self.save_record()
            self.assert_preserved(self.finish())

    def test_consumer_unsettled(self):
        self.record['artifact_retention']['consumers'] = [{'id':'qa', 'state':'live'}]
        self.save_record()
        self.assert_preserved(self.finish())

    def test_quiescence_unknown(self):
        self.record['artifact_retention']['quiescent'] = None
        self.save_record()
        self.assert_preserved(self.finish())

    def test_stale_manifest_acceptance(self):
        self.record['artifact_retention']['manifest_sha256'] = '0' * 64
        self.save_record()
        self.assert_preserved(self.finish())

    def test_file_changed_and_inode_replaced(self):
        target = self.root / 'scratch/raw'
        target.write_text('changed')
        self.assert_preserved(self.finish())

    def test_preserve_changed(self):
        (self.root / 'acceptance.json').write_text('tamper')
        self.assert_preserved(self.finish())

    def test_pins_and_activity_markers(self):
        for ref in ['.pin', 'scratch/.keep', 'scratch/writer.lock']:
            marker = self.root / ref
            marker.touch()
            self.assert_preserved(self.finish())
            marker.unlink()

    def test_evidence_alias_cannot_be_deleted(self):
        self.record['evidence']['result'].update(file='scratch/../scratch/raw',
                                                 sha256=rc.sha((self.root / 'scratch/raw').read_bytes()))
        self.save_record()
        self.assert_preserved(self.finish())

    def test_symlink_file_and_parent_and_hardlink(self):
        target = self.root / 'scratch/raw'
        target.unlink()
        target.symlink_to(self.root / 'report.md')
        self.assert_preserved(self.finish())
        target.unlink()
        os.link(self.root / 'report.md', target)
        self.assert_preserved(self.finish())
        target.unlink()
        (self.root / 'scratch').rmdir()
        (self.root / 'scratch').symlink_to(self.root)
        self.assertEqual(self.finish()['status'], 'blocked')

    def test_escape_and_layouts(self):
        for path in ['../report.md', '/private/tmp/x', './scratch/raw', 'scratch//raw']:
            with self.assertRaises(ValueError):
                rc.parts(path)
        nested = self.home / 'runs/repo/nested'
        nested.parent.mkdir()
        self.root.rename(nested)
        self.root = nested
        self.assertEqual(self.run_cli_blocked('complete')['status'], 'blocked')
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        with self.assertRaises(ValueError):
            rc.open_run(self.home, outside)

    def run_cli_blocked(self, command, *extras):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = rc.main([command, '--run', str(self.root), '--sejong-home', str(self.home),
                            '--record','record.json', '--expect-manifest-sha256', self.manifest_hash(), *extras])
        self.assertEqual(code, 1)
        return json.loads(out.getvalue())

    def test_read_and_probe_error(self):
        def fail(root):
            raise OSError('open activity unavailable')
        self.assert_preserved(self.finish(fail))
        with patch.object(rc, 'read_file', side_effect=OSError('read denied')):
            self.assert_preserved(self.finish())

    def test_actual_open_file_probe(self):
        with (self.root / 'scratch/raw').open() as opened:
            self.assert_preserved(self.finish(rc.probe_activity))
            self.assertFalse(opened.closed)

    def test_actual_probe_success(self):
        result = self.finish(rc.probe_activity)
        self.assertEqual(result['status'], 'completed', result)

    def test_swap_during_rename_restores_without_unlink(self):
        original = os.rename
        def swapped(src, dst, **kwargs):
            if str(dst).startswith('.completion-quarantine-'):
                target = self.root / 'scratch/raw'
                target.unlink()
                target.write_text('new foreign file')
            return original(src, dst, **kwargs)
        with patch.object(os, 'rename', side_effect=swapped):
            value = self.finish()
        self.assertEqual(value['status'], 'blocked')
        self.assertEqual((self.root / 'scratch/raw').read_text(), 'new foreign file')

    def test_unlink_error_restores_and_retry_needs_new_identity(self):
        original = os.unlink
        def failed(path, **kwargs):
            if str(path).startswith('.completion-quarantine-'):
                raise OSError('unlink failed')
            return original(path, **kwargs)
        with patch.object(os, 'unlink', side_effect=failed):
            self.assert_preserved(self.finish())
        self.assertEqual(self.finish()['status'], 'blocked')

    def test_reappeared_deleted_path_preserved(self):
        self.assertEqual(self.finish()['status'], 'completed')
        (self.root / 'scratch/raw').write_text('new owner')
        self.assert_preserved(self.finish())

    def test_hook_unregistered_unfinished_exact_session_and_success(self):
        payload = {'hook_event_name':'Stop', 'session_id':'session-fixture', 'cwd':str(self.root)}
        self.assertEqual(hook.dispatch(payload, self.home)['reason'], 'unregistered session')
        hook.register_session(self.home, 'session-fixture', self.root, 'goal-1', 'B', self.root, 'record.json')
        self.record['goal']['status'] = 'active'
        self.save_record()
        self.assertEqual(hook.dispatch(payload, self.home)['status'], 'skipped')
        self.assertTrue((self.root / 'scratch/raw').exists())
        with self.assertRaises(ValueError):
            hook.dispatch({**payload, 'cwd':str(self.root.parent)}, self.home)
        self.record['goal']['status'] = 'succeeded'
        self.save_record()
        self.assertEqual(hook.dispatch(payload, self.home)['status'], 'completed')
        self.assertFalse((self.root / 'scratch/raw').exists())

    def test_lock_contention(self):
        import fcntl
        with (self.root / rc.LOCK).open('w') as locked:
            fcntl.flock(locked.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.run_cli_blocked('complete')['status'], 'blocked')
        self.assertTrue((self.root / 'scratch/raw').exists())

    def test_missing_and_duplicate_metadata(self):
        (self.root / rc.MANIFEST).write_text('{"format":"one","format":"two"}')
        self.assertEqual(self.run_cli_blocked('complete')['status'], 'blocked')
        self.assertTrue((self.root / 'scratch/raw').exists())

    def test_registered_cli_producer_and_actual_stop_command(self):
        # Start an entirely new, tiny Run through the ordinary executable producer.
        new = self.home / 'runs/repo/new-run'
        new.mkdir(parents=True)
        args = [sys.executable, str(Path(rc.__file__)), 'init', '--run', str(new),
                '--sejong-home', str(self.home), '--run-id', 'new-goal', '--owner', 'lead',
                '--session-id', 'new-session', '--repo-root', str(self.root)]
        initial = subprocess.run(args, capture_output=True, text=True, timeout=10)
        self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
        payload = {'hook_event_name':'Stop', 'session_id':'new-session', 'cwd':str(self.root)}
        callback = subprocess.run([sys.executable, str(Path(hook.__file__)), 'Stop',
                                   '--sejong-home', str(self.home)], input=json.dumps(payload),
                                  capture_output=True, text=True, timeout=10)
        self.assertEqual(callback.returncode, 0, callback.stderr)
        self.assertEqual(callback.stdout.strip(), '{}')
        self.assertEqual(json.loads((new / rc.HOOK_RECEIPT).read_text())['status'], 'skipped')
        self.assertEqual(subprocess.run(args, capture_output=True, timeout=10).returncode, 0)

    def test_nested_layout_success_with_fresh_registration(self):
        nested = self.home / 'runs/repo/nested-run'
        nested.parent.mkdir()
        self.root.rename(nested)
        self.root = nested
        data = json.loads((nested / rc.MANIFEST).read_text())
        data['root'] = str(nested)
        (nested / rc.MANIFEST).write_text(json.dumps(data))
        self.record['artifact_retention']['manifest_sha256'] = self.manifest_hash()
        self.save_record()
        result = self.finish()
        self.assertEqual(result['status'], 'completed', result)

    def test_session_binding_replacement_requires_completed_prior_and_cas(self):
        hook.register_session(self.home, 'session', self.root, 'goal-1', 'B', self.root, 'record.json')
        target = hook.binding_path(self.home, 'session')
        prior_hash = rc.sha(target.read_bytes())
        new = self.home / 'runs/next'
        new.mkdir()
        with self.assertRaises((ValueError, OSError)):
            hook.register_session(self.home, 'session', new, 'goal-2', 'B', self.root, 'record.json', prior_hash)
        self.assertEqual(self.finish()['status'], 'completed')
        with self.assertRaises(ValueError):
            hook.register_session(self.home, 'session', new, 'goal-2', 'B', self.root, 'record.json', '0' * 64)
        hook.register_session(self.home, 'session', new, 'goal-2', 'B', self.root, 'record.json', prior_hash)
        self.assertEqual(json.loads(target.read_text())['run'], str(new))

    def test_session_state_parent_symlink_is_rejected(self):
        outside = Path(self.temp.name) / 'foreign'
        outside.mkdir()
        (self.home / 'state').symlink_to(outside)
        with self.assertRaises(OSError):
            hook.register_session(self.home, 'bad', self.root, 'goal-1', 'B', self.root, 'record.json')
        self.assertEqual(list(outside.iterdir()), [])

    def test_rejected_retry_does_not_erase_success_receipt(self):
        self.assertEqual(self.finish()['status'], 'completed')
        receipt = (self.root / rc.RECEIPT).read_bytes()
        self.record['artifact_retention']['manifest_sha256'] = '0' * 64
        self.save_record()
        self.assertEqual(self.finish()['status'], 'blocked')
        self.assertEqual((self.root / rc.RECEIPT).read_bytes(), receipt)

    def test_preserve_changed_after_quarantine_restores_target(self):
        calls = 0
        def observe(root):
            nonlocal calls
            calls += 1
            if calls == 3:
                (root / 'report.md').write_text('changed during quarantine')
            return {'status':'synthetic'}
        value = self.finish(observe)
        self.assertEqual(value['status'], 'blocked', value)
        self.assertTrue((self.root / 'scratch/raw').exists())
        self.assertEqual(value['removed'], [])

    def test_hook_malformed_record_receipt_no_deletion(self):
        hook.register_session(self.home, 'bad-record', self.root, 'goal-1', 'B', self.root, 'record.json')
        (self.root / 'record.json').write_text('{"goal": []}')
        value = hook.dispatch({'hook_event_name':'Stop', 'session_id':'bad-record', 'cwd':str(self.root)}, self.home)
        self.assert_preserved(value)
        self.assertTrue((self.root / rc.HOOK_RECEIPT).exists())

    def test_undeclared_source_kept(self):
        (self.root / 'source.py').write_text('required unintegrated source')
        self.assertEqual(self.finish()['status'], 'completed')
        self.assertTrue((self.root / 'source.py').exists())

    def test_retained_only_run_completes_without_deletion(self):
        data = json.loads((self.root / rc.MANIFEST).read_text())
        data['disposable'] = []
        (self.root / rc.MANIFEST).write_text(json.dumps(data))
        self.record['artifact_retention']['manifest_sha256'] = self.manifest_hash()
        self.save_record()
        value = self.finish()
        self.assertEqual(value['status'], 'completed', value)
        self.assertEqual(value['removed'], [])
        self.assertTrue((self.root / 'scratch/raw').exists())

    def test_fresh_manifest_rejects_omitted_routing_decision(self):
        self.record.pop('routing_accounting', None)
        for task in self.record['tasks']:
            task.pop('routing_decision', None)
        self.save_record()
        self.assert_preserved(self.finish())

    def test_fresh_manifest_accepts_decision_without_record_flag(self):
        self.record.pop('routing_accounting', None)
        self.save_record()
        self.assertEqual(self.finish()['status'], 'completed')

    def test_legacy_manifest_without_routing_remains_valid(self):
        data = json.loads((self.root / rc.MANIFEST).read_text())
        data.pop('routing_accounting', None)
        (self.root / rc.MANIFEST).write_text(json.dumps(data))
        self.record.pop('routing_accounting', None)
        for task in self.record['tasks']:
            task.pop('routing_decision', None)
        self.record['artifact_retention']['manifest_sha256'] = self.manifest_hash()
        self.save_record()
        value = self.finish()
        self.assertEqual(value['status'], 'completed', value)

    def test_custom_codex_home_and_missing_host_cwd(self):
        with patch.dict(os.environ, {'CODEX_HOME':str(self.home.parent / 'custom-codex'), 'SEJONG_HOME':''}):
            self.assertEqual(rc.default_home(), self.home.parent / 'custom-codex/sejong')
        hook.register_session(self.home, 'no-cwd', self.root, 'goal-1', 'B', self.root, 'record.json')
        with self.assertRaises(ValueError):
            hook.dispatch({'hook_event_name':'Stop', 'session_id':'no-cwd'}, self.home)
        self.assertTrue((self.root / 'scratch/raw').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
