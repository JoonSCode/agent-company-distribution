"""Executable successor regressions; all identities and approvals are synthetic."""
import contextlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

import run_completion as rc
from test_native_operations import digest, pin, save, tree
from test_storage_lifecycle import StorageLifecycleTests, MaintenanceStorageTests, PACKAGE


@contextlib.contextmanager
def lifecycle_case():
    case = StorageLifecycleTests('test_enroll_before_any_supported_write')
    case.setUp()
    try:
        yield case
    finally:
        case.doCleanups()


@contextlib.contextmanager
def maintenance_case():
    case = MaintenanceStorageTests('test_apply_uses_common_engine_and_verifies_external_receipts')
    case.setUp()
    try:
        yield case
    finally:
        case.doCleanups()


class RepairTests(unittest.TestCase):
    def test_reserved_creation_cannot_be_accepted(self):
        with lifecycle_case() as c:
            c.accepted()
            record = json.loads((c.run_root / 'record.json').read_bytes())
            record['goal']['status'] = 'active'
            record.pop('artifact_retention')
            save(c.run_root / 'record.json', record)
            c.classify([c.artifact('unfinished-worker-output')])
            record['goal']['status'] = 'succeeded'
            record['artifact_retention'] = dict(run_id='goal-1', manifest_sha256=digest(c.run_root / rc.MANIFEST), consumers=[], quiescent=True)
            save(c.run_root / 'record.json', record)
            manifest = json.loads((c.run_root / rc.MANIFEST).read_bytes())
            with self.assertRaisesRegex(ValueError, 'creation.*unfinished|unfinished.*creation'):
                rc.validate_acceptance(record, c.run_root / 'record.json', manifest, digest(c.run_root / rc.MANIFEST), require_routing=True)

    def test_public_summary_unknown_removed_and_reappeared_readonly(self):
        with lifecycle_case() as c:
            c.enroll()
            before = tree(c.run_root)
            unknown = c.close()
            self.assertIn('status=unknown', unknown['final_summary'])
            self.assertIn('removed=unknown', unknown['final_summary'])
            self.assertEqual(before, tree(c.run_root))
        with lifecycle_case() as c:
            request = c.accepted()
            c.apply(request)
            before = tree(c.run_root)
            result = c.close()
            self.assertIn('status=removed', result['final_summary'])
            self.assertIn('removed=1 files/15 logical bytes', result['final_summary'])
            self.assertIn(result['receipt']['sha256'], result['final_summary'])
            self.assertIn('prior receipt', result['final_summary'])
            self.assertEqual(before, tree(c.run_root))
            (c.run_root / 'scratch/raw').write_text('replacement must remain')
            blocked = c.close(expected=1)
            self.assertIn('status=blocked', blocked['final_summary'])
            self.assertEqual((c.run_root / 'scratch/raw').read_text(), 'replacement must remain')

    def test_rejection_only_summary_preserves_actual_trigger(self):
        with lifecycle_case() as c:
            c.accepted()
            (c.run_root / '.pin').write_text('retained active marker')
            p = subprocess.run([sys.executable, '-B', str(PACKAGE / 'scripts/run_completion.py'), 'complete', '--run', str(c.run_root), '--sejong-home', str(c.home), '--record', 'record.json', '--expect-manifest-sha256', digest(c.run_root / rc.MANIFEST)], env=c.env, capture_output=True, text=True, timeout=30)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            result = c.close(expected=1)
            self.assertEqual(result['trigger']['mode'], 'direct_complete')
            self.assertIn('direct_complete', result['final_summary'])
            self.assertIn('removed=unknown', result['final_summary'])

    def test_shipped_status_renderer_consumes_exact_closeout(self):
        with lifecycle_case() as c:
            request = c.accepted()
            c.apply(request)
            close = c.close()
            before = tree(c.run_root)
            output = c.root / 'storage-view.html'
            command = [sys.executable, '-B', str(PACKAGE / 'scripts/status_view.py'), 'render', str(c.run_root / 'record.json'), '--storage-closeout-request', str(c.root / 'closeout.json'), '--output', str(output), '--json']
            p = subprocess.run(command, env=c.env, capture_output=True, text=True, timeout=30)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            view = json.loads(p.stdout)
            self.assertEqual(view['storage_closeout'], close)
            self.assertIn(close['receipt']['sha256'], output.read_text())
            self.assertIn('Storage closeout', output.read_text())
            self.assertEqual(before, tree(c.run_root))

    def test_public_maintenance_result_no_receipt_then_exact_action(self):
        with maintenance_case() as c:
            root, request, plan, auth, review, _, _ = c.legacy_fixture()
            result_request = save(c.root / 'maintenance-closeout.json', dict(schema='company-native-storage-maintenance-closeout-request/v1', plan=pin(plan), authorization=pin(auth), review=pin(review)))
            before = tree(root)
            unknown = c.cli('storage', 'maintenance-closeout', '--request', result_request)
            self.assertEqual(unknown['status'], 'unknown')
            self.assertIsNone(unknown['removed_files'])
            self.assertEqual(before, tree(root))
            action = c.invoke_apply(plan, auth, review)
            before = tree(root)
            observed = c.cli('storage', 'maintenance-closeout', '--request', result_request)
            self.assertEqual(observed['status'], 'completed')
            self.assertEqual(observed['receipt'], action['receipt'])
            self.assertEqual(observed['removed_files'], 1)
            self.assertIn('prior receipt', observed['final_summary'])
            self.assertEqual(before, tree(root))
            (root / 'generated').write_text('reappeared original owner data')
            blocked = c.cli('storage', 'maintenance-closeout', '--request', result_request, expected=1)
            self.assertEqual(blocked['status'], 'blocked')
            self.assertIsNone(blocked['removed_files'])
            self.assertEqual((root / 'generated').read_text(), 'reappeared original owner data')

    def test_prepare_missing_enrollment_allocates_nothing(self):
        with lifecycle_case() as c:
            output = c.run_root / 'unbound-bundle'
            command = [sys.executable, '-B', str(PACKAGE / 'scripts/routing_prepare.py'), 'prepare', '--record', str(c.run_root / 'missing-record'), '--decision', str(c.run_root / 'missing-decision'), '--spec-file', str(c.root / 'missing-spec'), '--worktree', 'id:fixture::/fixture', '--output', str(output)]
            p = subprocess.run(command, env=c.env, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(p.returncode, 0)
            self.assertFalse(output.exists())

    def test_accepted_canonical_record_cannot_launch_new_result(self):
        import routing_launch
        from unittest.mock import patch
        with lifecycle_case() as c:
            c.accepted()
            decision = save(c.root / 'not-authority.json', {})
            args = ['--enrollment-request', str(c.enroll_path), '--expect-enrollment-sha256', digest(c.enroll_path), '--record', str(c.run_root / 'record.json'), '--decision', str(decision), '--receipt', str(c.run_root / 'late-receipt'), '--result', str(c.run_root / 'late-result'), '--from', 'fixture', '--spec', 'late', '--worktree', 'current']
            before = tree(c.run_root)
            with patch('routing_launch._main', side_effect=AssertionError('accepted record reached start path')) as host:
                self.assertEqual(routing_launch.main(args), 1)
                host.assert_not_called()
            self.assertEqual(before, tree(c.run_root))

    def test_measurement_writer_exact_retained_inventory(self):
        from test_measurement_lifecycle import LifecycleTests
        c = LifecycleTests('test_cli_prepare_checked_launch_settle_and_record')
        c.setUp()
        try:
            c.prepare(); c.launch('B'); c.close('B')
            manifest = json.loads((c.base / rc.MANIFEST).read_bytes())
            declarations = manifest['creation_contract']
            for path in c.root.iterdir():
                if path.is_file():
                    relative = path.relative_to(c.base).as_posix()
                    self.assertIn(relative, declarations)
                    self.assertEqual(declarations[relative]['origin'], 'measurement_lifecycle.py')
                    self.assertEqual(declarations[relative]['class'], 'preserve')
            self.assertIn('measurement-v2', manifest['consumers'])
        finally:
            c.doCleanups()

    def test_summary_without_storage_request_does_not_invent_zero(self):
        import status_view
        record = json.loads((PACKAGE / 'assets/record-cases.json').read_bytes())['cases'][0]['record']
        view = status_view.build_view(record, base=PACKAGE)
        self.assertEqual(view['storage_closeout']['status'], 'unknown')
        self.assertIsNone(view['storage_closeout']['removed_files'])
        self.assertIn('not supplied', view['storage_closeout']['final_summary'])


if __name__ == '__main__':
    unittest.main()
