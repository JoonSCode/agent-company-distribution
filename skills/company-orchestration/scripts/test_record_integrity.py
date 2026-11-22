"""Offline T0/T1 characterization and bounded historical diagnostic consumers."""
import copy
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import host_model_catalog
import record_check as rc
import record_integrity as integrity
import routing_launch
import run_completion
import status_view
from catalog_test_support import launch_fixture, bind_history_run


class HistoricalTests(unittest.TestCase):
    def setUp(self):
        self.f = self.enterContext(launch_fixture(rc.resolve))
        bind_history_run(self.f)
        self.i = self.f.inventory
        original = json.loads((self.i.root / 'record.json').read_text())
        code, output = self.f.invoke(routing_launch.main)
        self.assertEqual(code, 0, output)
        self.assertEqual((self.f.starts, self.f.refreshes), (1, 1))
        self.record = copy.deepcopy(original)
        self.record['label'] = 'real'
        for evidence in self.record['evidence'].values():
            evidence['kind'] = 'host'
        self.decision = copy.deepcopy(self.i.packet)
        task = self.record['tasks'][0]
        self.decision['binding'].update(task=task['id'], scope=self.record['goal']['scope'],
            revision=self.record['goal']['revision'], attempt=task['current_dispatch'], planned=False)
        self.decision['receipt_evidence'] = 'preflight'
        self.decision['launch_evidence'] = 'launch'
        self.preflight = self.i.root / 'preflight.json'
        self.record['evidence'].update(self.decision['evidence'])
        self.record['evidence']['preflight'] = {'ref': 'fixture://preflight', 'kind': 'host',
            'file': str(self.preflight), 'sha256': self.sha(self.preflight)}
        launch = self.i.root / 'result.json'
        self.record['evidence']['launch'] = {'ref': 'fixture://launch', 'kind': 'host',
            'file': str(launch), 'sha256': self.sha(launch)}
        task['routing_decision'] = self.decision
        task['model'].update(requested=self.decision['selected']['model'],
                             effort_requested=self.decision['selected']['effort'])

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def checked(self):
        return rc.check_record(self.record, self.i.root)

    def snapshot(self):
        roots = [self.f.catalog.root, self.i.root]
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                for root in roots for p in root.rglob('*') if p.is_file()}

    def test_characterization_t0_t1_configuration_and_policy_drift(self):
        # This asserts the old safe refusal, not a historical acceptance bypass.
        before = self.checked()
        self.assertTrue(before['ok'], before)
        self.assertEqual(before['historical_integrity']['status'], 'valid')
        self.assertEqual(before['current_readiness']['status'], 'ready')
        for path in (self.i.root / 'user.md', self.f.observed):
            with self.subTest(path=path.name):
                raw = path.read_bytes()
                path.write_bytes(raw + b'\nT1 changed input\n')
                frozen = self.snapshot()
                after = self.checked()
                self.assertFalse(after['ok'])
                self.assertEqual(after['historical_integrity'], before['historical_integrity'])
                self.assertEqual(after['current_readiness']['status'], 'blocked')
                self.assertIn('price_selection_invalid', {e['code'] for e in after['errors']})
                self.assertEqual(self.snapshot(), frozen)
                self.assertEqual((self.f.starts, self.f.refreshes), (1, 1))
                path.write_bytes(raw)

    def test_actual_record_cli_preserves_exit_and_dual_diagnostics(self):
        record_path = self.i.root / 'historical-record.json'
        record_path.write_text(json.dumps(self.record))
        env = {k: os.environ[k] for k in ('PATH', 'HOME', 'CODEX_HOME', 'TMPDIR',
               'PYTHONDONTWRITEBYTECODE', 'PYTHONNOUSERSITE', 'UV_OFFLINE',
               'UV_PYTHON_DOWNLOADS', 'AGENT_COMPANY_CONFIG') if k in os.environ}
        def invoke(*flags):
            result = subprocess.run([sys.executable, '-B', str(Path(rc.__file__)),
                'check', str(record_path), '--json', *flags], env=env, capture_output=True,
                text=True, timeout=20)
            self.assertEqual(result.stderr, '')
            return result.returncode, json.loads(result.stdout)
        code, before = invoke()
        self.assertEqual(code, 0, before)
        self.assertEqual(before['historical_integrity']['status'], 'valid')
        code, resources = invoke('--require-resources')
        self.assertEqual(code, 1, resources)
        self.assertEqual(resources['current_readiness']['status'], 'blocked')
        self.f.observed.write_text('T1 policy changed')
        code, after = invoke()
        self.assertEqual(code, 1, after)
        self.assertEqual(after['historical_integrity'], before['historical_integrity'])
        self.assertEqual(after['current_readiness']['status'], 'blocked')
        self.assertEqual((self.f.starts, self.f.refreshes), (1, 1))

    def catalog_cli(self, record_path, *, status=False):
        module = status_view if status else rc
        argv = [sys.executable, '-B', str(Path(module.__file__)),
                'render' if status else 'check', str(record_path), '--json']
        env = {k: os.environ[k] for k in ('PATH', 'HOME', 'CODEX_HOME', 'TMPDIR',
               'PYTHONDONTWRITEBYTECODE', 'PYTHONNOUSERSITE', 'UV_OFFLINE',
               'UV_PYTHON_DOWNLOADS', 'AGENT_COMPANY_CONFIG') if k in os.environ}
        result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.stderr, '', argv)
        # render reports diagnostics and deliberately exits 0, unlike check.
        payload = json.loads(result.stdout)
        return result.returncode, payload

    def test_malformed_catalog_receipts_actual_consumers_and_cli_matrix(self):
        prepared = self.f.catalog.root / 'manifest.json'
        refreshed = self.i.root / 'result.json.catalog-refresh/manifest.json'
        original_record = copy.deepcopy(self.record)
        preflight_raw = self.preflight.read_bytes()
        record_path = self.i.root / 'malformed-record.json'
        first = json.loads(prepared.read_bytes())['receipts'][0]
        shapes = {'empty': [], 'null': None, 'object': {},
                  'null_last': [first, None], 'string_last': [first, 'wrong'],
                  'list_last': [first, []], 'missing_time': [first, {}],
                  'null_time': [first, {'received_at': None}]}
        for target in (prepared, refreshed):
            raw = target.read_bytes()
            for name, receipts in shapes.items():
                for repin in (False, True):
                    with self.subTest(catalog=target.parent.name, shape=name, repin=repin):
                        self.record = copy.deepcopy(original_record)
                        self.preflight.write_bytes(preflight_raw)
                        manifest = json.loads(raw)
                        manifest['receipts'] = receipts
                        target.write_text(json.dumps(manifest))
                        if repin:
                            if target == prepared:
                                self.record['evidence']['inventory']['sha256'] = self.sha(target)
                            else:
                                preflight = json.loads(preflight_raw)
                                preflight['receipt']['host_catalog']['refreshed_manifest_sha256'] = self.sha(target)
                                self.preflight.write_text(json.dumps(preflight))
                                self.record['evidence']['preflight']['sha256'] = self.sha(self.preflight)
                        record_path.write_text(json.dumps(self.record))
                        frozen = self.snapshot()
                        direct = integrity.evaluate(self.record, self.i.root, rc.resolve(), legacy_ok=False)
                        result = self.checked()
                        view = status_view.build_view(self.record, base=self.i.root)
                        for diagnostics in (direct, result, view['snapshot']):
                            self.assertEqual(diagnostics['historical_integrity']['status'], 'invalid')
                            self.assertFalse(diagnostics['historical_integrity']['launch_authorized'])
                            self.assertFalse(diagnostics['current_readiness']['launch_authorized'])
                        reason = direct['historical_integrity']['tasks'][0]['reason']
                        if not repin:
                            self.assertEqual(reason, 'historical file hash mismatch')
                        else:
                            self.assertIn(reason, ('bounded status + catalog receipt sequence required',
                                                  'malformed receipt', 'missing timestamp'))
                        self.assertEqual(direct['current_readiness']['status'], 'blocked')
                        if target == prepared:
                            self.assertFalse(result['ok'])
                            self.assertEqual(result['current_readiness']['status'], 'blocked')
                            self.assertIn('price_selection_invalid', {e['code'] for e in result['errors']})
                        # Refreshed historical bytes do not redefine current prepared inputs
                        # or the legacy checker result: historical diagnostics are additive.
                        elif not repin:
                            self.assertTrue(result['ok'])
                            self.assertEqual(result['current_readiness']['status'], 'ready')
                        else:
                            # Repinning a changed prelaunch receipt cannot alter the
                            # original launch's receipt hash for the profile mapping.
                            self.assertFalse(result['ok'])
                            self.assertEqual(result['current_readiness']['status'], 'blocked')
                            self.assertIn('profile_binding_invalid', {e['code'] for e in result['errors']})
                        self.assertEqual(view['snapshot']['consistency_check']['ok'], result['ok'])
                        self.assertFalse(view['summary']['earned_overall_success'])
                        code, checked = self.catalog_cli(record_path)
                        self.assertEqual(code, 0 if result['ok'] else 1)
                        self.assertEqual(checked, result)
                        code, rendered = self.catalog_cli(record_path, status=True)
                        self.assertEqual(code, 0)
                        self.assertEqual(rendered['snapshot']['historical_integrity']['status'], 'invalid')
                        self.assertEqual(rendered['snapshot']['consistency_check']['ok'], result['ok'])
                        self.assertFalse(rendered['summary']['earned_overall_success'])
                        self.assertEqual(self.snapshot(), frozen)
                        self.assertEqual((self.f.starts, self.f.refreshes), (1, 1))
                        target.write_bytes(raw)
        self.record = original_record
        self.preflight.write_bytes(preflight_raw)

    def test_catalog_cli_normal_and_missing_history_controls(self):
        record_path = self.i.root / 'control-record.json'
        record_path.write_text(json.dumps(self.record))
        for missing in (False, True):
            if missing:
                self.preflight.unlink()
            frozen = self.snapshot()
            code, checked = self.catalog_cli(record_path)
            self.assertEqual(code, 1 if missing else 0)
            self.assertEqual(checked['historical_integrity']['status'], 'unknown' if missing else 'valid')
            code, rendered = self.catalog_cli(record_path, status=True)
            self.assertEqual(code, 0)
            self.assertEqual(rendered['snapshot']['historical_integrity']['status'],
                             'unknown' if missing else 'valid')
            self.assertFalse(rendered['summary']['earned_overall_success'])
            self.assertEqual(self.snapshot(), frozen)
            self.assertEqual((self.f.starts, self.f.refreshes), (1, 1))

    def test_rehashed_catalog_context_mismatch_still_refused(self):
        path = self.f.catalog.root / 'manifest.json'
        manifest = json.loads(path.read_bytes())
        manifest['worktree'] = 'id:other::/other'
        path.write_text(json.dumps(manifest))
        self.record['evidence']['inventory']['sha256'] = self.sha(path)
        frozen = self.snapshot()
        result = self.checked()
        self.assertFalse(result['ok'])
        self.assertEqual(result['historical_integrity']['status'], 'invalid')
        self.assertEqual(result['historical_integrity']['tasks'][0]['reason'],
                         'worktree context changed; reprepare')
        self.assertEqual(result['current_readiness']['status'], 'blocked')
        self.assertEqual(self.snapshot(), frozen)
        self.assertEqual((self.f.starts, self.f.refreshes), (1, 1))

    def test_legacy_fields_remain_exactly_the_existing_checker_result(self):
        for changed in (False, True):
            if changed:
                self.f.observed.write_text('changed external policy')
            old = rc.Checker(self.i.root).check(self.record)
            from goal_evidence import evaluate
            old['goal_evidence'], errors = evaluate(self.record, self.i.root, None)
            self.assertEqual(errors, [])
            result = self.checked()
            self.assertEqual({k: v for k, v in result.items() if k not in
                              ('historical_integrity', 'current_readiness')}, old)

    def test_current_expiry_is_not_historical_expiry_or_legacy_pass_permission(self):
        bound = host_model_catalog.bound_catalog
        with patch.object(integrity, 'bound_catalog', side_effect=lambda d, b, c:
                          bound(d, b, c, now=self.f.catalog.now + timedelta(days=1))):
            result = self.checked()
        self.assertTrue(result['ok'])  # Historical-time legacy validation unchanged.
        self.assertEqual(result['historical_integrity']['status'], 'valid')
        self.assertEqual(result['current_readiness']['status'], 'blocked')
        self.assertFalse(result['current_readiness']['launch_authorized'])

    def test_changed_configured_table_blocks_current_not_original_history(self):
        baseline = self.checked()
        self.assertTrue(baseline['ok'], baseline)
        table = copy.deepcopy(self.decision['profile_binding']['table'])
        table['entries'][0]['candidates'].reverse()
        path = self.i.root / 'later-table.json'
        path.write_text(json.dumps(table))
        config = rc.resolve()
        config['values']['worker_table'] = str(path) + '#sha256=' + self.sha(path)
        with patch('record_check.resolve', return_value=config):
            changed = self.checked()
        self.assertEqual(changed['historical_integrity']['status'], 'valid')
        self.assertEqual(changed['current_readiness']['status'], 'blocked')
        self.assertFalse(changed['current_readiness']['launch_authorized'])

    def test_historical_reader_never_resolves_or_reads_live_context(self):
        self.f.observed.unlink()
        (self.i.root / 'user.md').unlink()
        frozen = self.snapshot()
        with patch.object(rc, 'resolve', side_effect=AssertionError('no current resolver')), \
             patch('semantic_settings.validate_rows', side_effect=AssertionError('no live DB')), \
             patch('subprocess.run', side_effect=AssertionError('no host calls')):
            captured = integrity.historical_catalog(self.decision, self.record['evidence'], self.i.root)
        self.assertEqual(captured, self.f.catalog.now.isoformat())
        self.assertEqual(self.snapshot(), frozen)

    def test_historical_catalog_accepts_common_inventory_reference(self):
        decision = copy.deepcopy(self.decision)
        decision['binding']['inventory_evidence'] = decision['price_selection']['inventory_evidence']
        del decision['price_selection']
        captured = integrity.historical_catalog(decision, self.record['evidence'], self.i.root)
        self.assertEqual(captured, self.f.catalog.now.isoformat())

    def test_planned_profile_maps_only_to_matching_original_host_launch(self):
        original_receipt = json.loads(self.preflight.read_text())
        original_launch = json.loads((self.i.root / 'result.json').read_text())
        expected = {'task': 'task-1', 'dispatch': 'dispatch-current', 'run': 'goal-1'}
        receipt_path = self.i.root / 'mapping-receipt.json'
        launch_path = self.i.root / 'mapping-launch.json'

        def check(receipt, launch, decision=None):
            receipt_path.write_text(json.dumps(receipt))
            launch_path.write_text(json.dumps(launch))
            refs = copy.deepcopy(self.record['evidence'])
            refs['preflight'].update(file=str(receipt_path), sha256=self.sha(receipt_path))
            refs['launch'].update(file=str(launch_path), sha256=self.sha(launch_path))
            checker = rc.Checker(self.i.root)
            checker.refs = refs
            rc.check_profile_binding(checker, decision or self.decision, '$', historical=expected)
            return [item['code'] for item in checker.errors]

        # Pin this test's original prelaunch bytes in the simulated launch.
        receipt_path.write_text(json.dumps(original_receipt))
        launch = copy.deepcopy(original_launch)
        launch['prelaunch_receipt_sha256'] = self.sha(receipt_path)
        self.assertEqual(check(original_receipt, launch), [])
        for field, value in [('runId', 'other-run'), ('taskId', 'other-task'), ('dispatchId', 'other-dispatch')]:
            changed = copy.deepcopy(launch)
            envelope = json.loads(changed['stdout'])
            envelope['result'][field] = value
            changed['stdout'] = json.dumps(envelope)
            self.assertIn('profile_binding_invalid', check(original_receipt, changed), field)
        for field in ('profile_binding_sha256', 'profile_unit', 'spec_sha256', 'decision_sha256'):
            changed = copy.deepcopy(original_receipt)
            changed['receipt'][field] = 'wrong'
            self.assertIn('profile_binding_invalid', check(changed, launch), field)
        changed = copy.deepcopy(self.decision)
        del changed['launch_evidence']
        self.assertIn('profile_binding_invalid', check(original_receipt, launch, changed))
        changed = copy.deepcopy(launch)
        envelope = json.loads(changed['stdout'])
        start = envelope['result']
        effective = start.pop('launch')['effective']
        start.update(terminal='term', processIncarnation='inc')
        changed['stdout'] = json.dumps(envelope)
        full = {'ok': True, 'result': {'dispatch': {'id': 'dispatch-current', 'taskId': 'task-1',
                 'runId': 'goal-1', 'assigneeHandle': 'term', 'processIncarnation': 'inc'},
                 'worker': {'dispatchId': 'dispatch-current', 'startOptions': {'launch': {'effective': effective}}},
                 'terminal': {'handle': 'term'}}}
        changed['full_readback'] = {'status': 'observed', 'exit_code': 0, 'stdout': json.dumps(full)}
        self.assertEqual(check(original_receipt, changed), [])
        full['result']['dispatch']['processIncarnation'] = 'other'
        changed['full_readback']['stdout'] = json.dumps(full)
        self.assertIn('profile_binding_invalid', check(original_receipt, changed))

    def test_missing_historical_bytes_and_bare_pins_stay_unknown(self):
        paths = [self.preflight, self.f.catalog.root / 'manifest.json',
                 self.f.catalog.root / 'response-1.json',
                 self.i.root / 'result.json.catalog-refresh/manifest.json',
                 self.i.root / 'result.json.catalog-refresh/status.json']
        for path in paths:
            with self.subTest(path=str(path)):
                raw = path.read_bytes()
                path.unlink()
                self.assertEqual(self.checked()['historical_integrity']['status'], 'unknown')
                path.write_bytes(raw)
        ev = self.record['evidence']['preflight']
        for field in ('file', 'sha256'):
            with self.subTest(field=field):
                value = ev.pop(field)
                self.assertEqual(self.checked()['historical_integrity']['status'], 'unknown')
                ev[field] = value

    def test_tamper_and_malformed_history_never_validate(self):
        for path in (self.preflight, self.f.catalog.root / 'manifest.json',
                     self.f.catalog.root / 'response-1.json',
                     self.i.root / 'result.json.catalog-refresh/response-1.json'):
            with self.subTest(path=str(path)):
                raw = path.read_bytes()
                path.write_bytes(raw + b' ')
                frozen = self.snapshot()
                self.assertEqual(self.checked()['historical_integrity']['status'], 'invalid')
                self.assertEqual(self.snapshot(), frozen)
                path.write_bytes(raw)
        raw = self.preflight.read_bytes()
        for content in (b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', b'{bad'):
            self.preflight.write_bytes(content)
            self.record['evidence']['preflight']['sha256'] = self.sha(self.preflight)
            self.assertEqual(self.checked()['historical_integrity']['status'], 'invalid')
        self.preflight.write_bytes(raw)
        self.record['evidence']['preflight']['sha256'] = self.sha(self.preflight)

    def test_rehashed_receipt_binding_mismatches_are_invalid(self):
        raw = self.preflight.read_bytes()
        for key, value in (('spec_sha256', '0' * 64), ('configuration_sha256', '0' * 64)):
            receipt = json.loads(raw)
            receipt['receipt'][key] = value
            self.preflight.write_text(json.dumps(receipt))
            self.record['evidence']['preflight']['sha256'] = self.sha(self.preflight)
            self.assertEqual(self.checked()['historical_integrity']['status'], 'invalid')
        receipt = json.loads(raw)
        del receipt['receipt']['host_catalog']
        self.preflight.write_text(json.dumps(receipt))
        self.record['evidence']['preflight']['sha256'] = self.sha(self.preflight)
        self.assertEqual(self.checked()['historical_integrity']['status'], 'unknown')

    def test_status_refreshes_diagnostics_and_does_not_promote_success(self):
        fake = self.checked()
        t0 = status_view.build_view(self.record, base=self.i.root)
        self.assertTrue(t0['snapshot']['consistency_check']['ok'])
        self.assertEqual(t0['snapshot']['historical_integrity']['status'], 'valid')
        self.assertFalse(t0['summary']['earned_overall_success'])
        self.f.observed.write_text('T1 changed policy')
        frozen = self.snapshot()
        view = status_view.build_view(self.record, check_result=fake, base=self.i.root)
        snap = view['snapshot']
        self.assertEqual(snap['historical_integrity']['status'], 'valid')
        self.assertEqual(snap['current_readiness']['status'], 'blocked')
        self.assertFalse(snap['consistency_check']['ok'])
        self.assertFalse(view['summary']['earned_overall_success'])
        html = status_view.render_html(view)
        self.assertIn('과거 catalog/receipt 무결성', html)
        self.assertIn('현재 catalog 입력 준비도', html)
        self.assertEqual(self.snapshot(), frozen)
        with self.assertRaisesRegex(ValueError, 'record contradictions'):
            run_completion.validate_acceptance(self.record, self.i.root / 'record.json', {}, 'unused')
        self.assertEqual(self.snapshot(), frozen)

    def test_no_catalog_history_and_untrusted_annotations_cannot_supply_history(self):
        self.record['tasks'][0].pop('routing_decision')
        self.record['historical_integrity'] = {'status': 'valid', 'launch_authorized': True}
        self.record['current_readiness'] = {'status': 'ready', 'launch_authorized': True}
        result = self.checked()
        self.assertEqual(result['historical_integrity']['status'], 'unknown')
        self.assertEqual(result['current_readiness']['status'], 'unknown')
        self.assertFalse(result['historical_integrity']['launch_authorized'])
        self.assertFalse(result['current_readiness']['launch_authorized'])


if __name__ == '__main__':
    unittest.main()
