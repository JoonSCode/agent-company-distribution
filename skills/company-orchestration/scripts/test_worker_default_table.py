#!/usr/bin/env python3
"""Default policy configuration contracts; no provider/model calls."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from worker_profile import ASSETS, ProfileError, load_json
from worker_route import prepare, validate_table


class DefaultTableTests(unittest.TestCase):
    def setUp(self):
        self.table = load_json(ASSETS / 'worker-routing-table.json')
        self.doc = load_json(ASSETS / 'worker-profile-example.json')

    def test_complete_distinct_ordered_policy_and_provenance(self):
        validate_table(self.table)
        families = {'general', 'language', 'structured_data', 'reasoning', 'code',
                    'research', 'visual', 'design', 'media_generation', 'tool_use'}
        self.assertEqual({(r['family'], r['difficulty']) for r in self.table['entries']},
                         {(f, d) for f in families for d in ('easy', 'medium', 'hard')})
        self.assertEqual(len(self.table['entries']), 30)
        for row in self.table['entries']:
            self.assertEqual(len(row['candidates']), 3)
            self.assertEqual(len({c['identity']['model'] for c in row['candidates']}), 3)
            self.assertEqual([c['priority'] for c in row['candidates']], [0, 1, 2])
            if row['family'] != 'media_generation':
                self.assertEqual({c['identity']['route'] for c in row['candidates']}, {'codex', 'agy'})
            for c in row['candidates']:
                self.assertEqual(c['enabled'], row['family'] != 'media_generation')
                self.assertEqual(c['tools'], [])
                self.assertEqual(c['constraints'], [])
                self.assertEqual(c['context_limit'], 0)
                evidence = ' '.join(c['evidence'])
                for marker in ('editorial_prior:', 'policy_order:', 'identity:', 'observed_smoke:', 'modalities_and_runner:'):
                    self.assertIn(marker, evidence)
                self.assertIn('worker-routing-evidence.md#' + row['family'], evidence)
                self.assertNotIn('image.generate', c['capabilities'])
                self.assertNotIn('image', c['output_modalities'])
                if row['family'] == 'design' and 'no local result' not in evidence: self.assertIn('design=fail', evidence)

    def test_actual_default_cli_all_families_and_difficulties(self):
        examples = {
            'general': ('text', 'text', 'general.execute'),
            'language': ('text', 'text', 'text.translate'),
            'structured_data': ('structured_data', 'structured_data', 'data.transform'),
            'reasoning': ('text', 'text', 'logical.reason'),
            'code': ('code', 'code', 'code.reason'),
            'research': ('text', 'text', 'evidence.synthesize'),
            'visual': ('image', 'text', 'vision.read'),
            'design': ('text', 'structured_data', 'ui.design'),
            'tool_use': ('text', 'structured_data', 'tool.call'),
            'media_generation': ('text', 'image', 'image.generate'),
        }
        expected = {'easy': ('gpt-6.1-terra', 'low'),
                    'medium': ('gpt-6.1-terra', 'medium'), 'hard': ('gpt-6.2-sol', 'high')}
        with tempfile.TemporaryDirectory() as temp:
            profile = Path(temp) / 'profile.json'
            for family, (inp, out, cap) in examples.items():
                for difficulty in expected:
                    with self.subTest(family=family, difficulty=difficulty):
                        doc = copy.deepcopy(self.doc)
                        doc['units'][0]['profile'].update(family=family, difficulty=difficulty,
                            input_modalities=[inp], output_modalities=[out], required_capabilities=[cap])
                        profile.write_text(json.dumps(doc))
                        # No --table: exercises the real distributed default, not a synthetic table.
                        result = subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('worker_route.py')),
                            'prepare', str(profile)], capture_output=True, text=True)
                        self.assertEqual(result.returncode, 2 if family == 'media_generation' else 0,
                                         result.stdout + result.stderr)
                        r = json.loads(result.stdout)['results'][0]
                        if family == 'media_generation':
                            self.assertEqual(r['status'], 'NO_MATCH')
                            self.assertIsNone(r['selected'])
                            self.assertEqual(r['eligible_chain'], [])
                        else:
                            self.assertEqual(r['status'], 'MATCH')
                            wanted = expected[difficulty]
                            if difficulty == 'hard' and family in ('research', 'structured_data'):
                                wanted = ('gpt-6.2-astra', 'high')
                            if family == 'tool_use' and difficulty != 'easy':
                                effort = 'high' if difficulty == 'hard' else 'medium'
                                wanted = (f'gemini-4-hydrogen-{effort}', effort)
                            if (family, difficulty) == ('visual', 'hard'):
                                wanted = ('gemini-4-neon-high', 'high')
                            if (family, difficulty) == ('code', 'hard'):
                                wanted = ('gpt-6.2-sol', 'high')
                                self.assertEqual([item['identity']['model'] for item in r['eligible_chain']],
                                                 ['gpt-6.2-sol', 'gpt-6.2-astra', 'gemini-4-neon-high'])
                            self.assertEqual((r['selected']['model'], r['selected']['effort']), wanted)
                            self.assertEqual([c['fallback_index'] for c in r['eligible_chain']], [0, 1, 2])

    def test_gemini_identity_binds_route_and_effort(self):
        row = next(r for r in self.table['entries'] if (r['family'], r['difficulty']) == ('code', 'hard'))
        identity = row['candidates'][2]['identity']
        self.assertEqual(identity, dict(route='agy', model='gemini-4-neon-high', effort='high'))
        for change in (dict(route='codex'), dict(effort='low')):
            row['candidates'][2]['identity'] = identity | change
            with self.assertRaisesRegex(ProfileError, 'unknown policy identity'):
                validate_table(self.table)

    def test_default_fallbacks_and_exact_pin_no_substitution(self):
        row = self.table['entries'][0]
        for index in range(3):
            r = prepare(self.doc, self.table)['results'][0]
            self.assertEqual(r['fallback_index'], index)
            self.assertEqual(len(r['selection_reasons']), index)
            row['candidates'][index]['enabled'] = False
        self.assertEqual(prepare(self.doc, self.table)['results'][0]['status'], 'NO_MATCH')
        self.table = load_json(ASSETS / 'worker-routing-table.json')
        pin = copy.deepcopy(self.table['entries'][0]['candidates'][2]['identity'])
        self.assertEqual(prepare(self.doc, self.table, {'one': pin})['results'][0]['selected'], pin)
        pin['effort'] = 'high'
        self.assertEqual(prepare(self.doc, self.table, {'one': pin})['results'][0]['status'], 'NO_MATCH')

    def test_default_all_mandatory_constraints_are_anded(self):
        for field, value in [('input_modalities', ['text', 'audio']),
                             ('output_modalities', ['text', 'image']),
                             ('required_capabilities', ['general.execute', 'image.generate']),
                             ('required_tools', ['calculator']),
                             ('context_requirement', 1), ('hard_constraints', ['sandbox'])]:
            with self.subTest(field=field):
                doc = copy.deepcopy(self.doc)
                doc['units'][0]['profile'][field] = value
                r = prepare(doc, self.table)['results'][0]
                self.assertEqual(r['status'], 'NO_MATCH')
                self.assertEqual(len(r['rejected']), 3)
        doc = copy.deepcopy(self.doc)
        doc['units'][0]['profile'].update(family='tool_use', required_capabilities=['tool.call'], required_tools=['calculator'])
        self.assertEqual(prepare(doc, self.table)['results'][0]['status'], 'NO_MATCH')

    def test_default_rejects_third_backup_and_duplicate_models(self):
        row = self.table['entries'][0]
        row['candidates'].append(copy.deepcopy(row['candidates'][0]))
        with self.assertRaises(ProfileError): validate_table(self.table)
        row['candidates'].pop()
        row['candidates'][2]['identity'] = dict(row['candidates'][0]['identity'], effort='high')
        with self.assertRaisesRegex(ProfileError, 'duplicate model'): validate_table(self.table)


if __name__ == '__main__': unittest.main()
