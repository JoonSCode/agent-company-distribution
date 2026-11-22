#!/usr/bin/env python3
"""Shared last-resort proposal contracts, never provider or runtime retries."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from worker_profile import ASSETS, ProfileError, load_json
from worker_route import prepare, validate_table
from record_check import Checker, check_profile_binding, make_profile_binding


class SharedDefaultTests(unittest.TestCase):
    def setUp(self):
        self.doc = load_json(ASSETS / 'worker-profile-example.json')
        self.table = load_json(ASSETS / 'worker-routing-table.json')
        self.chain = self.table['entries'][0]['candidates']
        for c, model in zip(self.chain, ['gpt-6-luna', 'gpt-6.1-sol', 'gpt-6-astra']):
            c['identity']['model'] = model
        self.default = self.table['common_default']

    def result(self, pins=None):
        return prepare(self.doc, self.table, pins)['results'][0]

    def test_external_unlisted_identity_is_proposal_only_and_null_effort_survives(self):
        self.chain[0]['identity'] = {'route': 'grok', 'model': 'grok-fixture', 'effort': None}
        result = self.result()
        self.assertEqual(result['selected'], {'route': 'grok', 'model': 'grok-fixture', 'effort': None})
        binding = make_profile_binding(self.doc, self.table, self.doc['units'][0]['id'])
        self.assertEqual(binding['selected']['effort'], None)
        for bad in ({'route': 'invented', 'model': 'm', 'effort': None},
                    {'route': 'grok', 'model': '', 'effort': None},
                    {'route': 'codex', 'model': 'invented', 'effort': 'low'},
                    {'route': 'codex', 'model': 'gpt-6.1-terra', 'effort': None}):
            changed = copy.deepcopy(self.table)
            changed['entries'][0]['candidates'][0]['identity'] = bad
            with self.subTest(identity=bad), self.assertRaises(ProfileError):
                validate_table(changed)

    def exhaust(self):
        for c in self.chain: c['enabled'] = False

    def test_local_primary_fb1_fb2_then_separate_default(self):
        for index, c in enumerate(self.chain):
            r = self.result()
            self.assertEqual(r['selected'], c['identity'])
            self.assertEqual(r['fallback_index'], index)
            self.assertEqual(r['selected_source'], 'local')
            self.assertFalse(r['default_provenance']['consulted'])
            self.assertFalse(r['default_provenance']['selected'])
            c['enabled'] = False
        r = self.result()
        self.assertEqual(r['selected'], self.default['identity'])
        self.assertEqual(r['selected_source'], 'common_default')
        self.assertIsNone(r['fallback_index'])
        self.assertEqual(r['eligible_chain'], [])
        self.assertEqual(len(r['selection_reasons']), 3)
        self.assertTrue(r['default_provenance']['consulted'])
        self.assertTrue(r['default_provenance']['selected'])
        self.default['enabled'] = False
        self.assertEqual(self.result()['status'], 'NO_MATCH')

    def test_third_backup_rejected_and_required_default_identity(self):
        self.chain.append(copy.deepcopy(self.default))
        self.chain[-1]['priority'] = 3
        with self.assertRaisesRegex(ProfileError, 'too many items'): validate_table(self.table)
        self.chain.pop()
        for model in ['gpt-6-astra', 'unknown']:
            self.default['identity']['model'] = model
            with self.assertRaises(ProfileError): validate_table(self.table)
        self.default['identity']['model'] = 'gpt-6.1-terra'
        del self.table['common_default']
        with self.assertRaises(ProfileError): validate_table(self.table)

    def test_duplicate_route_model_skipped_even_different_effort(self):
        self.exhaust()
        self.chain[0]['identity']['model'] = 'gpt-6.1-terra'
        self.assertNotEqual(self.chain[0]['identity']['effort'], self.default['identity']['effort'])
        r = self.result()
        self.assertEqual(r['status'], 'NO_MATCH')
        self.assertTrue(r['default_provenance']['consulted'])
        self.assertFalse(r['default_provenance']['selected'])
        self.assertEqual(r['default_provenance']['reasons'], ['duplicate local route/model'])
        # Ineligible capability evidence cannot be upgraded through the shared entry.
        self.chain[0]['enabled'] = True
        self.chain[0]['capabilities'] = []
        self.assertEqual(self.result()['status'], 'NO_MATCH')

    def test_all_filters_apply_to_shared_default(self):
        self.exhaust()
        self.doc['units'][0]['profile'].update(required_tools=['repo'], hard_constraints=['sandbox'], context_requirement=10)
        self.default.update(tools=['repo'], constraints=['sandbox'], context_limit=10)
        self.assertEqual(self.result()['selected_source'], 'common_default')
        for field, bad in [('input_modalities', []), ('output_modalities', []), ('capabilities', []),
                           ('tools', []), ('constraints', []), ('context_limit', 9), ('enabled', False)]:
            with self.subTest(field=field):
                old = self.default[field]; self.default[field] = bad
                r = self.result()
                self.assertEqual(r['status'], 'NO_MATCH')
                self.assertTrue(r['default_provenance']['reasons'])
                self.default[field] = old

    def test_exact_pin_and_no_row_no_escape(self):
        pin = copy.deepcopy(self.default['identity'])
        r = self.result({'one': pin})
        self.assertEqual(r['selected'], pin)
        self.assertEqual(r['selected_source'], 'common_default')
        pin['effort'] = 'high'
        self.assertEqual(self.result({'one': pin})['status'], 'NO_MATCH')
        local_pin = copy.deepcopy(self.chain[1]['identity'])
        self.chain[1]['enabled'] = False
        self.assertEqual(self.result({'one': local_pin})['status'], 'NO_MATCH')
        self.table['entries'] = [r for r in self.table['entries'] if r['family'] == 'general']
        self.doc['units'][0]['profile']['family'] = 'language'
        r = self.result()
        self.assertEqual(r['reason'], 'no table row')
        self.assertFalse(r['default_provenance']['consulted'])

    def test_media_cannot_escape_default_even_when_not_duplicate(self):
        self.doc['units'][0]['profile'].update(family='media_generation', output_modalities=['image'], required_capabilities=['image.generate'])
        row = next(r for r in self.table['entries'] if r['family'] == 'media_generation')
        for c, model in zip(row['candidates'], ['gpt-6-luna', 'gpt-6.1-sol', 'gpt-6-astra']):
            c['identity']['model'] = model
        r = self.result()
        self.assertEqual(r['status'], 'NO_MATCH')
        self.assertIn("output_modalities: missing ['image']", r['default_provenance']['reasons'])
        self.assertIn("required_capabilities: missing ['image.generate']", r['default_provenance']['reasons'])

    def test_binding_recomputes_default_provenance_and_rejects_downgrade(self):
        self.exhaust()
        binding = make_profile_binding(self.doc, self.table, 'one')
        decision: dict = dict(binding={'task': 'one'}, selected=binding['selected'], profile_binding=binding)
        def errors(d):
            checker = Checker(ASSETS); check_profile_binding(checker, d, '$'); return checker.errors
        self.assertFalse(errors(decision))
        for key, value in [('consulted', False), ('consulted', 1), ('selected', False), ('selected', 1), ('identity', self.chain[0]['identity']),
                           ('evidence', ['forged']), ('reasons', ['forged'])]:
            d = copy.deepcopy(decision); d['profile_binding']['default_provenance'][key] = value
            with self.subTest(key=key): self.assertTrue(errors(d))
        for key, value in [('selected_source', 'local'), ('fallback_index', 3), ('eligible_chain', [{}]),
                           ('selection_reasons', []), ('version', 1), ('version', 2)]:
            d = copy.deepcopy(decision); d['profile_binding'][key] = value
            with self.subTest(key=key): self.assertTrue(errors(d))
        d = copy.deepcopy(decision); d['profile_binding']['table']['common_default']['enabled'] = False
        self.assertTrue(errors(d))
        d = copy.deepcopy(decision); d['selected'] = self.chain[0]['identity']
        self.assertTrue(errors(d))

    def test_cli_default_binding(self):
        self.exhaust()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); profile = root/'profile.json'; table = root/'table.json'
            profile.write_text(json.dumps(self.doc)); table.write_text(json.dumps(self.table))
            for script, args in [('worker_route.py', ['prepare', str(profile)]),
                                 ('record_check.py', ['profile-prepare', str(profile), '--unit', 'one'])]:
                result = subprocess.run([sys.executable, '-B', str(Path(__file__).with_name(script)), *args,
                                         '--table', str(table)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                data = json.loads(result.stdout)
                r = data['results'][0] if script == 'worker_route.py' else data['profile_binding']
                self.assertEqual(r['selected_source'], 'common_default')
                self.assertTrue(r['default_provenance']['consulted'])
                self.assertTrue(r['default_provenance']['selected'])


if __name__ == '__main__': unittest.main()
