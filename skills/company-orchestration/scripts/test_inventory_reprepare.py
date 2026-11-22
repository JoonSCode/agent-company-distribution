"""Deterministic mutable-cache reproduction; host is always a fake."""
import copy
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

import routing_launch
import run_completion as rc
from catalog_test_support import PACKAGE, inventory_fixture
from storage_test_support import enrollment_path, pin, save


class InventoryReprepareTests(unittest.TestCase):
    def setUp(self):
        self.fixture = self.enterContext(inventory_fixture())

    def mutate(self, kind='timestamp'):
        current = copy.deepcopy(self.fixture.contents)
        current['fetched_at'] = '2025-01-02T00:00:00Z'
        if kind == 'candidate': current['models'][0]['supported_reasoning_levels'] = []
        if kind == 'capability': current['models'][0]['input_modalities'] = ['audio']
        if kind == 'pricing': current['models'][0]['pricing'] = {'input': 999}
        if kind == 'availability': current['models'][0]['visibility'] = 'hidden'
        if kind == 'etag': current['etag'] = 'changed'
        if kind == 'unknown': current['future_condition'] = False
        if kind == 'partial': current['models'] = []
        if kind == 'future': current['fetched_at'] = '2200-01-01T00:00:00Z'
        if kind == 'regressed': current['fetched_at'] = '2024-01-01T00:00:00Z'
        if kind == 'unchanged': current['fetched_at'] = self.fixture.contents['fetched_at']
        self.fixture.cache.write_text('{' if kind == 'malformed' else json.dumps(current))

    def output_paths(self, name):
        for flag, suffix in (('--result', '.result'), ('--receipt', '.preflight')):
            self.fixture.args[self.fixture.args.index(flag) + 1] = str(self.fixture.root / (name + suffix))

    def invoke(self, refresh=True, host_effect=None):
        output = io.StringIO()
        args = self.fixture.args + (['--reprepare-inventory', str(self.fixture.snapshot)] if refresh else [])
        with patch('routing_launch.subprocess.run', return_value=self.fixture.fake, side_effect=host_effect) as host, contextlib.redirect_stdout(output):
            try:
                code = routing_launch.main(args)
            except SystemExit as exc:
                code = exc.code
        return code, host.call_count, output.getvalue()

    def cli(self, script, *args):
        env = {key: os.environ[key] for key in ('PATH', 'HOME', 'CODEX_HOME', 'TMPDIR', 'PYTHONPYCACHEPREFIX', 'AGENT_COMPANY_CONFIG')
               if key in os.environ}
        env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', UV_OFFLINE='1', UV_PYTHON_DOWNLOADS='never')
        process = subprocess.run([sys.executable, '-B', PACKAGE / 'scripts' / script, *args],
                                 env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(process.stderr, '')
        return process.returncode, json.loads(process.stdout)

    def classify(self, refs, phase):
        root = self.fixture.root
        enrollment = enrollment_path(root)
        declarations = json.loads((root / rc.MANIFEST).read_bytes())['creation_contract']
        rows = [{key: value for key, value in declarations[ref].items() if key != 'state'} for ref in refs]
        request = save(enrollment.parent / 'classification.json', dict(
            schema='company-native-storage-classification/v1', enrollment=pin(enrollment),
            expect_manifest_sha256=pin(root / rc.MANIFEST)['sha256'], phase=phase, artifacts=rows))
        return self.cli('native_operations.py', 'storage', 'classify', '--request', request)

    def test_raw_hash_drift_denies_before_fake_host(self):
        self.mutate()
        code, calls, output = self.invoke(refresh=False)
        self.assertEqual((code, calls), (1, 0))
        self.assertIn('hash_mismatch', output)
        self.assertIn('canonical_inventory_hash_changed', output)
        self.assertEqual(json.loads((self.fixture.root/'result.json').read_text())['launch_state'], 'not_started')

    def test_explicit_reprepare_timestamp_once(self):
        original = self.fixture.decision.read_bytes()
        self.mutate()
        code, calls, output = self.invoke()
        self.assertEqual((code, calls), (0, 1), output)
        self.assertEqual(self.fixture.decision.read_bytes(), original)
        archive = self.fixture.root/'result.json.reprepare'
        self.assertEqual((archive/'inventory-before.json').read_bytes(), self.fixture.snapshot.read_bytes())
        self.assertEqual((archive/'inventory-current.json').read_bytes(), self.fixture.cache.read_bytes())
        refreshed = json.loads((archive/'decision.json').read_text())
        self.assertEqual(refreshed['selected'], self.fixture.packet['selected'])
        self.assertEqual(refreshed['evidence']['inventory']['sha256'], hashlib.sha256(self.fixture.cache.read_bytes()).hexdigest())
        self.assertEqual(self.invoke()[:2], (1, 0))

    def test_timing_keeps_authoritative_prestart_state_for_reprepare(self):
        self.fixture.args.append('--record-timing')
        self.mutate()
        code, calls, output = self.invoke()
        self.assertEqual((code, calls), (0, 1), output)
        result = json.loads((self.fixture.root / 'result.json').read_bytes())
        self.assertEqual(result['launch_state'], 'observed')
        self.assertEqual(result['timing']['reason'], 'readback_finished')
        self.assertIn('prepared', result['timing']['marks'])
        self.assertEqual(self.invoke()[:2], (1, 0))

    def test_public_cli_reprepares_both_packet_shapes_and_never_reissues_start(self):
        for ordinary in (True, False):
            with self.subTest(ordinary=ordinary), inventory_fixture() as fixture:
                self.fixture = fixture
                packet = fixture.packet
                if ordinary:
                    row = packet.pop('price_selection')['candidates'][0]
                    packet['binding']['inventory_evidence'] = 'inventory'
                    packet['selected_reason'] = packet['alternatives'][0]['reason'] = 'ordinary_assignment'
                    packet['selected_runtime'] = {key: row[key] for key in (
                        'route', 'family', 'model', 'effort', 'supported', 'authenticated', 'tools', 'billing', 'runtime_evidence')}
                original = (json.dumps(packet, indent=4) + '\n').encode()
                fixture.decision.write_bytes(original)
                before = fixture.cache.read_bytes()
                self.mutate()
                fake = fixture.root / 'fake-orca'
                starts = fixture.root / 'starts'
                fake.write_text(f'#!{sys.executable}\nimport sys\nfrom pathlib import Path\n'
                                'assert sys.argv[1:3] == ["orchestration", "worker-start"] and "--full" in sys.argv\n'
                                f'with Path({str(starts)!r}).open("a") as log: log.write("start\\n")\n'
                                f'print({fixture.fake.stdout!r})\n')
                fake.chmod(0o700)
                fixture.args[fixture.args.index('--orca') + 1] = str(fake)
                args = [*fixture.args, '--reprepare-inventory', str(fixture.snapshot)]
                code, reply = self.cli('routing_launch.py', *args)
                self.assertEqual((code, reply['ok']), (0, True), reply)
                self.assertEqual(starts.read_text().splitlines(), ['start'])
                archive = fixture.root / 'result.json.reprepare'
                self.assertEqual((archive / 'decision-before.json').read_bytes(), original)
                self.assertEqual(fixture.decision.read_bytes(), original)
                self.assertEqual(fixture.snapshot.read_bytes(), before)
                self.assertEqual((archive / 'inventory-before.json').read_bytes(), before)
                self.assertEqual((archive / 'inventory-current.json').read_bytes(), fixture.cache.read_bytes())
                provenance = json.loads((archive / 'provenance.json').read_bytes())
                self.assertEqual(provenance['original_decision_sha256'], hashlib.sha256(original).hexdigest())
                self.assertEqual(provenance['refresh_count'], 1)
                rejected = {(e['path'], e['code']) for e in provenance['rejected_check']['errors']}
                drift_path = '$.selected_runtime' if ordinary else '$.price_selection'
                self.assertEqual(rejected, {('$.evidence.inventory', 'hash_mismatch'),
                                            (drift_path, 'canonical_inventory_hash_changed')})
                self.assertEqual(self.cli('routing_launch.py', *args)[0], 1)
                self.assertEqual(starts.read_text().splitlines(), ['start'])

    def test_reprepare_terminal_absence_and_partial_originals_via_public_storage(self):
        for partial in (False, True):
            with self.subTest(partial=partial), inventory_fixture() as fixture:
                self.fixture = fixture
                self.mutate('timestamp' if partial else 'candidate')
                write = routing_launch.atomic_state

                def stop_after_originals(path, value, *args):
                    if path.parent.name.endswith('.reprepare'):
                        raise OSError('fixture interruption after original bytes')
                    return write(path, value, *args)

                with patch('routing_launch.atomic_state', side_effect=stop_after_originals):
                    self.assertEqual(self.invoke()[:2], (1, 0))
                root = fixture.root
                manifest = json.loads((root / rc.MANIFEST).read_bytes())
                refs = manifest['launch_contract']['result.json']['optional']
                self.assertEqual(len(refs), 5)
                present = {ref: (root / ref).read_bytes() for ref in refs if (root / ref).exists()}
                self.assertEqual(len(present), 3 if partial else 0)
                absent = [ref for ref in refs if ref not in present]
                if present:
                    code, reply = self.classify([*absent, next(iter(present))], 'absent')
                    self.assertEqual((code, reply['status']), (1, 'blocked'), reply)
                    self.assertEqual(json.loads((root / rc.MANIFEST).read_bytes()), manifest)
                    self.assertEqual(self.classify(list(present), 'freeze')[0], 0)
                self.assertEqual(self.classify([*absent, 'preflight.json'], 'absent')[0], 0)
                declarations = json.loads((root / rc.MANIFEST).read_bytes())['creation_contract']
                for ref in absent:
                    self.assertEqual(declarations[ref]['state'], 'absent')
                for ref, raw in present.items():
                    self.assertEqual(declarations[ref]['state'], 'frozen')
                    self.assertEqual((root / ref).read_bytes(), raw)
                self.assertEqual(self.invoke()[:2], (1, 0))

    def test_missing_reprepare_outputs_cannot_settle_after_possible_start(self):
        self.mutate('candidate')
        self.assertEqual(self.invoke()[:2], (1, 0))
        root = self.fixture.root
        original = (root / rc.MANIFEST).read_bytes()
        ref = json.loads(original)['launch_contract']['result.json']['optional'][0]
        for state in ('invocation_pending', 'unknown'):
            with self.subTest(state=state):
                save(root / 'result.json', {'launch_state_version': 1, 'launch_state': state})
                self.assertEqual(self.classify([ref], 'absent')[0], 1)
                self.assertEqual((root / rc.MANIFEST).read_bytes(), original)

    def test_material_malformed_partial_and_freshness_changes_deny(self):
        for kind in ('candidate', 'capability', 'pricing', 'availability', 'etag', 'unknown',
                     'partial', 'malformed', 'future', 'regressed', 'unchanged'):
            with self.subTest(kind=kind):
                self.mutate(kind)
                if kind == 'unchanged':
                    self.fixture.cache.write_bytes(self.fixture.cache.read_bytes() + b'\n')
                self.output_paths(kind)
                code, calls, output = self.invoke()
                self.assertEqual((code, calls), (1, 0), output)
                self.assertEqual(json.loads(output)['error'], 'inventory reprepare denied')

    def test_missing_or_wrong_snapshot_denies(self):
        self.mutate()
        self.fixture.snapshot.write_text('{}')
        self.assertEqual(self.invoke()[:2], (1, 0))

    def test_pending_unknown_or_existing_denial_is_not_rewritten(self):
        self.mutate()
        for state in ('invocation_pending', 'unknown', 'observed', 'not_started'):
            path = self.fixture.root/'result.json'
            raw = json.dumps({'launch_state_version': 1, 'launch_state': state}).encode()
            path.write_bytes(raw)
            self.assertEqual(self.invoke()[:2], (1, 0))
            self.assertEqual(path.read_bytes(), raw)

    def test_repeated_drift_denies_without_second_refresh(self):
        self.mutate()
        real_check = routing_launch.check_routing
        checks = []
        def checking(*args, **kwargs):
            result = real_check(*args, **kwargs)
            checks.append(result['ok'])
            if result['ok']:
                current = json.loads(self.fixture.cache.read_bytes())
                current['fetched_at'] = '2025-01-03T00:00:00Z'
                self.fixture.cache.write_text(json.dumps(current))
            return result
        with patch('routing_launch.check_routing', side_effect=checking):
            code, calls, output = self.invoke()
        self.assertEqual((code, calls), (1, 0), output)
        self.assertTrue(any(checks), checks)
        self.assertEqual(self.invoke()[:2], (1, 0))

    def test_profile_binding_is_recomputed_without_selection_change(self):
        import record_check
        profile = json.loads((PACKAGE/'assets/worker-profile-example.json').read_text())
        profile['units'][0]['id'] = 'new'
        table = json.loads((PACKAGE/'assets/worker-routing-table.json').read_text())
        for row in table['entries']:
            row['candidates'][0].update(input_modalities=['text'], output_modalities=['text'],
                capabilities=['general.execute'], evidence=['fixture assertion'])
        binding = record_check.make_profile_binding(profile, table, 'new')
        self.fixture.packet['profile_binding'] = binding
        from test_route_select import SelectionCLITests
        authority = SelectionCLITests()
        authority.setUp()
        self.addCleanup(authority.doCleanups)
        authority.authorize_profile(self.fixture.packet)
        self.fixture.decision.write_text(json.dumps(self.fixture.packet))
        self.mutate()
        with patch('record_check.make_profile_binding', wraps=record_check.make_profile_binding) as prepare:
            code, calls, output = self.invoke()
        self.assertEqual((code, calls), (0, 1), output)
        self.assertGreaterEqual(prepare.call_count, 3)
        saved = json.loads((self.fixture.root/'result.json.reprepare/decision.json').read_text())
        self.assertEqual(saved['profile_binding'], binding)

    def test_duplicate_keys_nonfinite_and_changed_json_types_deny(self):
        for kind in ('duplicate', 'nonfinite', 'boolean'):
            self.mutate()
            raw = self.fixture.cache.read_text()
            if kind == 'duplicate': raw = raw[:-1] + ', "etag": "same"}'
            if kind == 'nonfinite': raw = raw[:-1] + ', "future": NaN}'
            if kind == 'boolean': raw = raw.replace('"etag": "same"', '"etag": true')
            self.fixture.cache.write_text(raw)
            self.output_paths(kind)
            self.assertEqual(self.invoke()[:2], (1, 0))

    def test_precise_numeric_change_cannot_be_rounded_away(self):
        raw = self.fixture.snapshot.read_bytes().replace(b'"etag": "same"', b'"etag": 1.00000000000000001')
        self.fixture.snapshot.write_bytes(raw)
        self.fixture.packet['evidence']['inventory']['sha256'] = hashlib.sha256(raw).hexdigest()
        self.fixture.decision.write_text(json.dumps(self.fixture.packet))
        self.fixture.cache.write_bytes(raw.replace(b'1.00000000000000001', b'1.0').replace(b'2025-01-01', b'2025-01-02'))
        code, calls, output = self.invoke()
        self.assertEqual((code, calls), (1, 0), output)
        self.assertIn('inventory content changed', output)

    def test_other_denials_and_expiry_never_refresh(self):
        for kind in ('spec', 'profile', 'expiry'):
            packet = copy.deepcopy(self.fixture.packet)
            if kind == 'spec': packet['binding']['spec_sha256'] = '0'*64
            if kind == 'profile': packet['profile_binding'] = {'version': 0}
            if kind == 'expiry': packet['evidence']['inventory']['valid_until'] = '2001-01-01T00:00:00Z'
            self.fixture.decision.write_text(json.dumps(packet))
            self.mutate()
            self.output_paths(kind)
            self.assertEqual(self.invoke()[:2], (1, 0))

    def test_measurement_and_reuse_modes_deny_before_any_host_call(self):
        self.mutate()
        original = self.fixture.args.copy()
        for extra in (['--measurement-attempt', 'unknown-attempt'], ['--terminal', 'fake-terminal'],
                      ['--reuse-dispatch', 'fake-dispatch']):
            self.fixture.args = original + extra
            self.assertEqual(self.invoke()[:2], (1, 0))
        self.fixture.args = original
        record = self.fixture.root/'record.json'
        current = json.loads(record.read_text())
        current['measurement'] = {'mode': 'required', 'version': 2}
        record.write_text(json.dumps(current))
        self.assertEqual(self.invoke()[:2], (1, 0))

    def test_unknown_host_outcome_never_retries(self):
        self.mutate()
        import subprocess
        self.assertEqual(self.invoke(host_effect=subprocess.TimeoutExpired('fake', 1))[:2], (1, 1))
        self.assertEqual(json.loads((self.fixture.root/'result.json').read_text())['launch_state'], 'unknown')
        self.assertEqual(self.invoke()[:2], (1, 0))


if __name__ == '__main__':
    unittest.main()
