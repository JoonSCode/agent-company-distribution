#!/usr/bin/env python3
"""Synthetic chain contracts; no model or network calls."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from worker_profile import ASSETS, ProfileError, load_json
from worker_route import prepare, validate_table
from record_check import Checker, check_profile_binding, make_profile_binding


class ChainTests(unittest.TestCase):
    def setUp(self):
        self.doc = load_json(ASSETS / 'worker-profile-example.json')
        self.table = load_json(ASSETS / 'worker-routing-table.json')
        # This fixture intentionally omits specialized rows to test absent-row refusal.
        self.table['entries'] = [r for r in self.table['entries'] if r['family'] == 'general']
        base = copy.deepcopy(self.table['entries'][0]['candidates'][0])
        base.update(input_modalities=['text'], output_modalities=['text'],
                    capabilities=['general.execute'], evidence=['synthetic fixture only'])
        self.chain = []
        for index, model in enumerate(['gpt-6.1-terra', 'gpt-6.1-sol', 'gpt-6-astra']):
            c = copy.deepcopy(base)
            c.update(priority=index)
            c['identity'] = dict(route='codex', model=model, effort='low')
            self.chain.append(c)
        self.table['entries'][0]['candidates'] = self.chain

    def result(self, pins=None):
        return prepare(self.doc, self.table, pins)['results'][0]

    def test_primary_and_two_fallbacks(self):
        for index in range(3):
            with self.subTest(index=index):
                r = self.result()
                self.assertEqual(r['fallback_index'], index)
                self.assertEqual(r['selected'], self.chain[index]['identity'])
                self.assertEqual([c['fallback_index'] for c in r['eligible_chain']], list(range(index, 3)))
                self.assertEqual([c['fallback_index'] for c in r['selection_reasons']], list(range(index)))
                self.chain[index]['enabled'] = False
        r = self.result()
        self.assertEqual(r['status'], 'NO_MATCH')
        self.assertEqual(r['eligible_chain'], [])
        self.assertIsNone(r['fallback_index'])
        self.assertIsNone(r['selected'])

    def test_zero_backups_excess_and_duplicate_model(self):
        self.table['entries'][0]['candidates'] = self.chain[:1]
        self.assertEqual(self.result()['fallback_index'], 0)
        self.table['entries'][0]['candidates'] = self.chain + [copy.deepcopy(self.chain[0])]
        with self.assertRaisesRegex(ProfileError, 'too many items'): validate_table(self.table)
        duplicate = copy.deepcopy(self.chain[0]); duplicate['identity']['effort'] = 'high'
        self.table['entries'][0]['candidates'] = [self.chain[0], duplicate]
        with self.assertRaisesRegex(ProfileError, 'duplicate model'): validate_table(self.table)

    def test_every_required_filter_applies_to_backups(self):
        p = self.doc['units'][0]['profile']
        p.update(required_tools=['repo'], hard_constraints=['sandbox'], context_requirement=10)
        for c in self.chain: c.update(tools=['repo'], constraints=['sandbox'], context_limit=10)
        for field, bad in [('input_modalities', []), ('output_modalities', []),
                           ('capabilities', []), ('tools', []), ('constraints', []),
                           ('context_limit', 9), ('enabled', False)]:
            with self.subTest(field=field):
                t = copy.deepcopy(self.table)
                for c in t['entries'][0]['candidates'][:2]: c[field] = bad
                r = prepare(self.doc, t)['results'][0]
                self.assertEqual(r['fallback_index'], 2)
                self.assertEqual(len(r['selection_reasons']), 2)
                t['entries'][0]['candidates'][2][field] = bad
                self.assertEqual(prepare(self.doc, t)['results'][0]['status'], 'NO_MATCH')

    def test_exact_pin_conflict_and_missing_row(self):
        pin = copy.deepcopy(self.chain[2]['identity'])
        r = self.result({'one': pin})
        self.assertEqual(r['selected'], pin)
        self.assertEqual(len(r['eligible_chain']), 1)
        self.chain[2]['enabled'] = False
        self.assertEqual(self.result({'one': pin})['status'], 'NO_MATCH')
        pin['effort'] = 'high'
        self.assertEqual(self.result({'one': pin})['status'], 'NO_MATCH')
        self.doc['units'][0]['profile']['family'] = 'language'
        self.assertEqual(self.result()['reason'], 'no table row')

    def test_order_is_legacy_priority_then_identity(self):
        before = prepare(self.doc, self.table)
        self.chain.reverse()
        after = prepare(self.doc, self.table)
        self.assertEqual(before['results'], after['results'])
        self.assertNotEqual(before['table_sha256'], after['table_sha256'])

    def test_binding_recomputes_chain_and_legacy_compatibility(self):
        self.chain[0]['enabled'] = False
        binding = make_profile_binding(self.doc, self.table, 'one')
        decision: dict = dict(binding={'task': 'one'}, selected=binding['selected'], profile_binding=binding)
        def errors(d):
            checker = Checker(ASSETS)
            check_profile_binding(checker, d, '$')
            return checker.errors
        self.assertFalse(errors(decision))
        for key, value in [('eligible_chain', []), ('fallback_index', 3), ('selection_reasons', []), ('table_sha256', '0'*64)]:
            d = copy.deepcopy(decision); d['profile_binding'][key] = value
            with self.subTest(key=key): self.assertTrue(errors(d))
        legacy = copy.deepcopy(decision); legacy['profile_binding']['version'] = 1
        for key in ('eligible_chain', 'fallback_index', 'selection_reasons'): legacy['profile_binding'].pop(key)
        self.assertTrue(errors(legacy))
        d = copy.deepcopy(decision); d['selected'] = self.chain[2]['identity']
        self.assertTrue(errors(d))
        d = copy.deepcopy(decision); d['selected_reason'] = 'user_pin'
        self.assertTrue(errors(d))

    def test_full_prelaunch_checks_profile_and_selected_identity(self):
        from record_check import check_routing
        from test_route_select import PACKAGE, SelectionCLITests
        fixture = SelectionCLITests()
        fixture.setUp()
        packet = fixture.packet()
        packet['binding']['task'] = 'one'
        packet['profile_binding'] = make_profile_binding(self.doc, self.table, 'one')
        self.addCleanup(fixture.doCleanups)
        fixture.authorize_profile(packet)
        self.assertTrue(check_routing(packet, PACKAGE, prelaunch=True)['ok'])
        packet['profile_binding']['selected']['model'] = 'gpt-6.1-sol'
        result = check_routing(packet, PACKAGE, prelaunch=True)
        self.assertIn('profile_binding_invalid', [e['code'] for e in result['errors']])

    def test_no_candidate_cannot_produce_execution_binding(self):
        for candidate in self.chain:
            candidate['enabled'] = False
        with self.assertRaisesRegex(ProfileError, 'no eligible candidate'):
            make_profile_binding(self.doc, self.table, 'one')

    def test_cli_chain_and_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = root/'profile.json'; table = root/'table.json'
            profile.write_text(json.dumps(self.doc))
            command = []
            for index in range(3):
                table.write_text(json.dumps(self.table))
                for script, extra in [('worker_route.py', ['prepare', str(profile)]),
                                      ('record_check.py', ['profile-prepare', str(profile), '--unit', 'one'])]:
                    command = [sys.executable, '-B', str(Path(__file__).with_name(script)), *extra, '--table', str(table)]
                    result = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    data = json.loads(result.stdout)
                    selected = data['results'][0] if script == 'worker_route.py' else data['profile_binding']
                    self.assertEqual(selected['fallback_index'], index)
                self.chain[index]['enabled'] = False
            table.write_text(json.dumps(self.table))
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('NO_MATCH', result.stdout)


class RequiredExecutionBindingTests(unittest.TestCase):
    def test_missing_binding_rejected_at_execution_but_historical_readable(self):
        from record_check import check_routing
        from unittest.mock import patch
        decision = {'label': 'real'}
        with patch.object(Checker, 'evidence_map'), patch.object(Checker, 'routing'), patch.object(Checker, 'routing_receipt', return_value={}):
            historical = check_routing(decision, ASSETS)
            execution = check_routing(decision, ASSETS, prelaunch=True)
        self.assertTrue(historical['ok'], historical)
        self.assertIn('profile_binding_required', [error['code'] for error in execution['errors']])
        with patch.object(Checker, 'evidence_map'), patch.object(Checker, 'routing'), patch.object(Checker, 'routing_receipt', return_value={}):
            malformed = check_routing({**decision, 'profile_binding': None}, ASSETS, prelaunch=True)
        self.assertIn('profile_binding_invalid', [error['code'] for error in malformed['errors']])


if __name__ == '__main__': unittest.main()
