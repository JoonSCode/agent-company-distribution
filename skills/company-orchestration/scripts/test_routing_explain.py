"""Synthetic residue diagnostics against the actual checked launcher; no live host."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import company_config
from catalog_test_support import inventory_fixture, launch_fixture
import routing_explain
import routing_launch

SCRIPT = Path(__file__).with_name('routing_explain.py')
REQUEST = '3b212508-3e85-4f90-a56c-1e2c992c58d2'
RUNTIME = 'd663a6c6-d73d-4be7-9fbf-91c3e753439b'


def snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


class ExplainTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.temp)
        self.result = self.root / 'result.json'
        self.receipt = self.root / 'preflight.json'

    def state(self, state, **extra):
        self.result.write_text(json.dumps(dict(launch_state_version=1, launch_state=state, **extra)))

    def invoke(self, command='explain', result=None, receipt=None, *, fake_host=None):
        env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'PYTHONPYCACHEPREFIX') if key in os.environ}
        env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', UV_OFFLINE='1', UV_PYTHON_DOWNLOADS='never')
        if fake_host is not None:
            env['ORCA_CLI_COMMAND'] = str(fake_host)
        child = subprocess.run([sys.executable, '-B', str(SCRIPT), command,
            '--result', str(result or self.result), '--receipt', str(receipt or self.receipt),
            *(['--query-request'] if fake_host is not None else [])],
            capture_output=True, text=True, env=env, timeout=20)
        self.assertEqual(child.stderr, '')
        return child.returncode, json.loads(child.stdout)

    def assert_blocked(self, report):
        self.assertIs(report['launch_authorized'], False)
        self.assertIs(report['new_attempt_allowed'], False)
        self.assertIs(report['same_attempt_retry_allowed'], False)
        self.assertEqual(report['host_no_start'], 'unknown')
        self.assertIn('trustworthy_host_no_start_evidence_missing', report['reconcile_plan']['reasons'])

    def test_actual_refresh_then_final_check_denial_preserves_exclusive_residue(self):
        with launch_fixture(company_config.resolve) as fixture:
            root = fixture.inventory.root
            result, receipt = root/'result.json', root/'preflight.json'
            original = fixture.observed.read_bytes()
            fixture.change_at_refresh = lambda _: fixture.observed.write_text('changed auth policy')
            code, output = fixture.invoke(routing_launch.main)
            self.assertEqual((code, fixture.refreshes, fixture.starts), (1, 1, 0), output)
            self.assertIn('catalog prelaunch denied', output)
            self.assertIn('prelaunch context or selection changed', output)
            self.assertEqual(json.loads(result.read_bytes())['launch_state'], 'not_started')
            self.assertFalse(receipt.exists())
            refresh = root/'result.json.catalog-refresh'
            self.assertTrue((refresh/'manifest.json').is_file())
            before = snapshot(root)
            status, report = self.invoke(result=result, receipt=receipt)
            self.assertEqual(status, 0)
            self.assertEqual(report['last_observed_stage'], 'catalog_refresh_directory_present')
            self.assertEqual(report['artifacts']['receipt']['status'], 'absent')
            self.assert_blocked(report)
            self.assertEqual(self.invoke('reconcile-plan', result, receipt)[1], report)
            self.assertEqual(snapshot(root), before)
            # Characterize existing same-name denial, not a new retry feature.
            fixture.observed.write_bytes(original)
            residue = snapshot(refresh)
            code, output = fixture.invoke(routing_launch.main)
            self.assertEqual((code, fixture.refreshes, fixture.starts), (1, 2, 0), output)
            self.assertIn('catalog prelaunch denied', output)
            self.assertEqual(snapshot(refresh), residue)
            self.assertFalse(receipt.exists())

    def test_actual_unknown_explain_never_retries(self):
        with launch_fixture(company_config.resolve) as fixture:
            fixture.timeout_start = True
            code, output = fixture.invoke(routing_launch.main)
            self.assertEqual((code, fixture.starts, fixture.refreshes), (1, 1, 1), output)
            before = snapshot(fixture.inventory.root)
            for command in ('explain', 'reconcile-plan'):
                code, report = self.invoke(command, fixture.inventory.root/'result.json', fixture.inventory.root/'preflight.json')
                self.assertEqual(code, 0)
                self.assertEqual(report['local_state'], 'unknown')
                self.assert_blocked(report)
            self.assertEqual(snapshot(fixture.inventory.root), before)
            code, output = fixture.invoke(routing_launch.main)
            self.assertEqual((code, fixture.starts, fixture.refreshes), (1, 1, 1), output)
            self.assertEqual(snapshot(fixture.inventory.root), before)

    def test_timeout_diagnostic_unavailable_keeps_pending_no_second_refresh(self):
        with launch_fixture(company_config.resolve) as fixture:
            fixture.timeout_start = True
            with patch('routing_launch.write_timeout_state', side_effect=OSError('sk-private-error')):
                code, output = fixture.invoke(routing_launch.main)
            self.assertEqual((code, fixture.starts, fixture.refreshes), (1, 1, 1), output)
            self.assertEqual(json.loads(output)['diagnostic'], 'unavailable')
            self.assertNotIn('sk-private-error', output)
            result, receipt = fixture.inventory.root/'result.json', fixture.inventory.root/'preflight.json'
            self.assertEqual(json.loads(result.read_bytes())['launch_state'], 'invocation_pending')
            before = snapshot(fixture.inventory.root)
            code, report = self.invoke(result=result, receipt=receipt)
            self.assertEqual((code, report['local_state']), (0, 'invocation_pending'))
            self.assert_blocked(report)
            code, output = fixture.invoke(routing_launch.main)
            self.assertEqual((code, fixture.starts, fixture.refreshes), (1, 1, 1), output)
            self.assertEqual(snapshot(fixture.inventory.root), before)

    def test_actual_observed_remains_local_not_new_authority(self):
        with launch_fixture(company_config.resolve) as fixture:
            code, output = fixture.invoke(routing_launch.main)
            self.assertEqual((code, fixture.starts), (0, 1), output)
            before = snapshot(fixture.inventory.root)
            code, report = self.invoke(result=fixture.inventory.root/'result.json', receipt=fixture.inventory.root/'preflight.json')
            self.assertEqual((code, report['local_state'], report['receipt_binding']), (0, 'observed', 'matches'))
            self.assert_blocked(report)
            self.assertEqual(snapshot(fixture.inventory.root), before)

    def test_checked_launcher_retains_full_response_for_local_request_identification(self):
        with inventory_fixture() as fixture:
            start = json.loads(fixture.fake.stdout)
            start.update(id='transport-id', _meta={'runtimeId': RUNTIME})
            start['result'].update(mutation={'requestId': REQUEST, 'replayed': False})
            fixture.fake.stdout = json.dumps(start)
            output = io.StringIO()
            with patch('routing_launch.subprocess.run', return_value=fixture.fake) as host, contextlib.redirect_stdout(output):
                code = routing_launch.main(fixture.args)
            self.assertEqual((code, host.call_count), (0, 1), output.getvalue())
            root = fixture.root
            saved = json.loads((root / 'result.json').read_bytes())
            self.assertEqual(json.loads(saved['stdout']), start)
            self.assertIn('--full', json.loads((root / 'preflight.json').read_bytes())['receipt']['launch_argv'])
            _, report = self.invoke('reconcile-plan', root / 'result.json', root / 'preflight.json')
            self.assertEqual(report['reconcile_plan']['orca_request'], {
                'request_id': REQUEST, 'runtime_id': RUNTIME, 'source': 'orca_full_start_response'})
            self.assert_blocked(report)

    def request_fixture(self, *, runtime=RUNTIME, error=False):
        argv = ['/some/original/orca', 'orchestration', 'worker-start', '--from', 'fixture',
                '--task', 'task-exact', '--json', '--full', '--run', 'run-exact']
        digest = 'a' * 64
        self.receipt.write_text(json.dumps(dict(ok=True, label='real', receipt=dict(
            launch_argv=argv, decision_sha256=digest, requested_run='run-exact'))))
        self.start_ids = {'runId': 'run-exact', 'taskId': 'task-exact', 'dispatchId': 'dispatch-exact'}
        payload = dict(id='transport-id', ok=not error, _meta={'runtimeId': runtime})
        if error:
            payload['error'] = dict(code='runtime_timeout', data=dict(orchestrationRequestId=REQUEST,
                dispatchId='dispatch-exact', originalCommand=['orca', *argv[1:]], recovery=dict(
                    orchestrationRequestId=REQUEST, disposition='outcome_unknown')))
        else:
            payload['result'] = {**self.start_ids, 'mutation': {'requestId': REQUEST, 'replayed': False}}
        self.state('unknown', decision_sha256=digest, exit_code=1, stdout=json.dumps(payload),
                   prelaunch_receipt_sha256=hashlib.sha256(self.receipt.read_bytes()).hexdigest())
        return payload

    def test_exact_request_lookup_cli_states_and_authority_mismatches(self):
        self.request_fixture(error=True)
        fake = self.root / 'read-only-orca'
        for kind, expected in (('completed', 'completed'), ('pending', 'pending'), ('absent', 'absent'),
                               ('restart', 'runtime_mismatch'), ('request', 'request_mismatch'),
                               ('wrong_method', 'method_mismatch'), ('other_run', 'start_identity_mismatch'),
                               ('sibling_task', 'start_identity_mismatch'), ('other_dispatch', 'start_identity_mismatch'),
                               ('malformed', 'query_unavailable'), ('host_error', 'query_unavailable')):
            with self.subTest(kind=kind):
                result = {'requestId': REQUEST, 'state': 'completed', 'method': 'orchestration.workerStart',
                          'receipt': {**self.start_ids, 'mutation': {'requestId': REQUEST, 'replayed': False},
                                      'private_spec': 'never export original spec'}}
                runtime = RUNTIME
                if kind in ('absent', 'pending'):
                    result.pop('receipt')
                    result['state'] = kind
                if kind == 'absent':
                    result.pop('method')  # Same shape for a pruned request and a wrong caller.
                if kind == 'restart':
                    runtime = 'different-runtime'
                if kind == 'request':
                    result['requestId'] = 'different-request'
                if kind == 'wrong_method':
                    result['method'] = 'orchestration.runCreate'
                for case, key in (('other_run', 'runId'), ('sibling_task', 'taskId'), ('other_dispatch', 'dispatchId')):
                    if kind == case:
                        result['receipt'][key] = 'other'
                if kind == 'malformed':
                    result['receipt'] = []
                answer = {'ok': True, 'result': result, '_meta': {'runtimeId': runtime}}
                expected_argv = ['orchestration', 'request-show', '--request', REQUEST, '--environment', 'local', '--full', '--json']
                fake.write_text(f'#!{sys.executable}\nimport sys\nassert sys.argv[1:] == {expected_argv!r}\n'
                                f'print({json.dumps(answer)!r})\nsys.exit({int(kind == "host_error")})\n')
                fake.chmod(0o700)
                before = snapshot(self.root)
                code, report = self.invoke('reconcile-plan', fake_host=fake)
                lookup = report['reconcile_plan']['request_lookup']
                self.assertEqual((code, lookup['status']), (0, expected), report)
                self.assertEqual(lookup.get('recorded_start_ids'), self.start_ids if kind == 'completed' else None)
                self.assertNotIn('never export original spec', json.dumps(report))
                self.assert_blocked(report)
                self.assertEqual(snapshot(self.root), before)

    def test_lost_reply_and_unbound_or_suspicious_residue_never_queries(self):
        for kind in ('pending', 'lost_reply', 'wrong_argv', 'unbound_runtime', 'wrong_receipt', 'rpc_id_only', 'not_sent'):
            with self.subTest(kind=kind):
                state = self.request_fixture(error=kind != 'rpc_id_only', runtime=None if kind == 'unbound_runtime' else RUNTIME)
                saved = json.loads(self.result.read_bytes())
                if kind == 'pending':
                    saved['launch_state'] = 'invocation_pending'
                if kind == 'lost_reply':
                    state = {'partial_output': 'hash only'}
                if kind == 'wrong_argv':
                    state['error']['data']['originalCommand'][6] = 'sibling-task'
                if kind == 'wrong_receipt':
                    saved['prelaunch_receipt_sha256'] = '0' * 64
                if kind == 'rpc_id_only':
                    state['id'] = REQUEST
                    del state['result']['mutation']
                if kind == 'not_sent':
                    state['error']['data']['requestSent'] = False
                saved['stdout'] = json.dumps(state)
                self.result.write_text(json.dumps(saved))
                before = snapshot(self.root)
                with patch('routing_explain.subprocess.run') as host:
                    report = routing_explain.explain(self.result, self.receipt, query=True)
                    host.assert_not_called()
                plan = report['reconcile_plan']
                self.assertEqual(plan['request_lookup']['status'],
                                 'original_runtime_unavailable' if kind == 'unbound_runtime' else 'request_unavailable')
                self.assertEqual(plan['orca_request']['request_id'] if plan['orca_request'] else None,
                                 REQUEST if kind == 'unbound_runtime' else None)
                self.assert_blocked(report)
                self.assertEqual(snapshot(self.root), before)

    def test_state_matrix_deterministic_and_readonly_without_host_calls(self):
        for state in ('not_started', 'invocation_pending', 'unknown', 'observed'):
            with self.subTest(state=state):
                self.state(state)
                before = snapshot(self.root)
                with patch('routing_launch.subprocess.run') as host:
                    report = routing_explain.explain(self.result, self.receipt)
                    self.assertEqual(report, routing_explain.explain(self.result, self.receipt))
                    host.assert_not_called()
                self.assertEqual(report['local_state'], state)
                self.assert_blocked(report)
                self.assertEqual(snapshot(self.root), before)

    def test_missing_partial_archive_and_receipt_stages(self):
        code, report = self.invoke()
        self.assertEqual((code, report['last_observed_stage']), (0, 'unknown'))
        self.assertFalse(self.result.exists())
        self.assert_blocked(report)
        archive = self.root/'result.json.reprepare'
        archive.mkdir()
        (archive/'inventory-before.json').write_text('partial')
        code, report = self.invoke()
        self.assertEqual(report['last_observed_stage'], 'inventory_reprepare_archive_present')
        self.receipt.write_text(json.dumps({'receipt': {'secret_fixture_value': 'do not export'}}))
        before = snapshot(self.root)
        code, report = self.invoke()
        self.assertEqual(report['last_observed_stage'], 'prelaunch_receipt_present')
        self.assertNotIn('do not export', json.dumps(report))
        self.assertEqual(snapshot(self.root), before)
        self.assert_blocked(report)

    def test_invalid_state_json_types_and_receipt_binding_deny(self):
        for raw in ('{', '{"launch_state_version":1,"launch_state_version":1}',
                    '{"launch_state_version":1,"launch_state":[]}',
                    '{"launch_state_version":true,"launch_state":"not_started"}',
                    '{"launch_state_version":1,"launch_state":"new-state"}', 'NaN', '[]'):
            with self.subTest(raw=raw):
                self.result.write_text(raw)
                before = snapshot(self.root)
                code, report = self.invoke()
                self.assertEqual(code, 1)
                self.assert_blocked(report)
                self.assertEqual(snapshot(self.root), before)
        self.state('observed', prelaunch_receipt_sha256='0'*64)
        self.receipt.write_text('{"receipt":{}}')
        code, report = self.invoke()
        self.assertEqual((code, report['receipt_binding']), (1, 'mismatch'))
        self.receipt.write_text('malformed')
        self.assertEqual(self.invoke()[0], 1)

    def test_symlinks_directories_fifo_and_oversize_are_not_followed(self):
        target = self.root/'private'
        target.mkdir()
        (target/'secret').write_text('never export')
        self.result.symlink_to(target/'secret')
        code, report = self.invoke()
        self.assertEqual(code, 1)
        self.assertNotIn('never export', json.dumps(report))
        self.result.unlink()  # Test-owned fixture, never production cleanup.
        self.state('not_started')
        refresh = self.root/'result.json.catalog-refresh'
        refresh.symlink_to(target, target_is_directory=True)
        self.assertEqual(self.invoke()[0], 1)
        refresh.unlink()
        refresh.mkdir()
        (refresh/'manifest.json').symlink_to(target/'secret')
        self.assertEqual(self.invoke()[0], 1)
        os.mkfifo(self.receipt)
        self.assertEqual(self.invoke()[0], 1)
        self.receipt.unlink()
        self.receipt.write_bytes(b'x'*(routing_explain.LIMIT+1))
        self.assertEqual(self.invoke()[0], 1)

    def test_no_execution_or_mutation_cli_flags(self):
        env = {'PATH': os.environ.get('PATH', ''), 'PYTHONDONTWRITEBYTECODE': '1'}
        help_result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--help'], capture_output=True, text=True, timeout=20, env=env)
        self.assertEqual(help_result.returncode, 0)
        for flag in ('--launch', '--retry', '--delete', '--reset', '--output', '--host-no-start'):
            child = subprocess.run([sys.executable, '-B', str(SCRIPT), 'explain', '--result', str(self.result),
                '--receipt', str(self.receipt), flag], capture_output=True, text=True, timeout=20, env=env)
            self.assertEqual(child.returncode, 2)
        self.assertEqual(snapshot(self.root), {})


if __name__ == '__main__':
    unittest.main()
