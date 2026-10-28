#!/usr/bin/env python3
"""Focused routing preflight CLI regressions using only synthetic local inputs."""
import copy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import record_check
import test_route_select

PACKAGE = Path(__file__).resolve().parents[1]
CLI = PACKAGE / 'scripts/record_check.py'


class RoutingPreflightTests(unittest.TestCase):
    def test_recorded_prelaunch_preserves_nondominated_selection_and_receipt(self):
        fixture = test_route_select.SelectionCLITests()
        fixture.setUp()
        fixture.selection['candidates'] = [test_route_select.candidate('terra', 'low'), test_route_select.candidate('terra', 'medium')]
        packet = fixture.packet()
        for row in (packet['selected'], packet['alternatives'][0]):
            row['effort'] = 'medium'
        packet['label'] = 'real'
        packet['binding']['spec_sha256'] = 'a' * 64
        packet['receipt_evidence'] = 'receipt'
        for value in packet['evidence'].values():
            value['kind'] = 'host'
        inventory = self.root / 'archive.json'
        inventory.write_text(json.dumps({'models': packet['evidence']['inventory']['host_models']}))
        packet['evidence']['inventory'].update(file=inventory.name, sha256=hashlib.sha256(inventory.read_bytes()).hexdigest())
        with patch('record_check.resolve', return_value=fixture.config):
            checker = record_check.Checker(self.root)
            checker.refs = packet['evidence']
            from route_select import select
            comparison = select(packet['price_selection'], packet['evidence'], fixture.config, synthetic=False,
                                prelaunch=True, requested=packet['selected'], host_models=packet['evidence']['inventory']['host_models'])
            receipt = {'ok': True, 'label': 'real', 'receipt': {'binding': copy.deepcopy(packet['binding']), 'selected': copy.deepcopy(packet['selected']),
                       'spec_sha256': 'a' * 64, 'price_selection': comparison}}
            receipt_path = self.root / 'receipt.json'
            receipt_path.write_text(json.dumps(receipt))
            packet['evidence']['receipt'] = {'kind': 'source', 'ref': 'receipt', 'file': receipt_path.name,
                                             'sha256': hashlib.sha256(receipt_path.read_bytes()).hexdigest()}
            checker.refs = packet['evidence']
            result = checker.price_selection(packet, '$.price', recorded_prelaunch=True)
            self.assertEqual(result['selected']['effort'], 'medium')
            self.assertFalse(checker.errors)
            receipt['receipt']['selected']['effort'] = 'low'
            receipt_path.write_text(json.dumps(receipt))
            checker = record_check.Checker(self.root)
            checker.refs = packet['evidence']
            self.assertIsNone(checker.price_selection(packet, '$.price', recorded_prelaunch=True))
            self.assertIn('price_selection_invalid', [error['code'] for error in checker.errors])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.record_path = self.root / 'records/current.json'
        self.decision_path = self.root / 'decisions/route.json'
        self.record_path.parent.mkdir()
        self.decision_path.parent.mkdir()
        records = json.loads((PACKAGE / 'assets/record-cases.json').read_text())
        routes = json.loads((PACKAGE / 'assets/routing-cases.json').read_text())
        self.record = copy.deepcopy(records['cases'][0]['record'])
        self.decision = copy.deepcopy(next(case['decision'] for case in routes['cases']
                                           if not case['expected_errors']))
        fixture = test_route_select.SelectionCLITests()
        fixture.setUp()
        self.decision = fixture.packet()
        self.record['tasks'][0]['model']['requested'] = self.decision['selected']['model']
        self.record['tasks'][0]['model']['effort_requested'] = self.decision['selected']['effort']

    def planned(self):
        self.decision['binding'].update(task='task-next', attempt='planned:task-next', planned=True)

    def save(self):
        self.record_path.write_text(json.dumps(self.record))
        self.decision_path.write_text(json.dumps(self.decision))

    def invoke(self, expected=0, standalone=False, save=True):
        if save:
            self.save()
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns)
                  for p in self.root.rglob('*') if p.is_file()}
        args = [sys.executable, '-I', str(CLI), 'routing-check', str(self.decision_path), '--json']
        if not standalone:
            args += ['--record', str(self.record_path)]
        process = subprocess.run(args, cwd=self.root, capture_output=True, text=True)
        self.assertEqual(process.returncode, expected, process.stdout + process.stderr)
        self.assertNotIn('Traceback', process.stderr)
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns)
                                  for p in self.root.rglob('*') if p.is_file()})
        result = json.loads(process.stdout)
        self.assertEqual(result['ok'], expected == 0)
        return result

    def test_observed_r2_packet_rejects_current_r1_goal(self):
        self.planned()
        self.decision['binding']['revision'] = 'r2'
        self.assertTrue(self.invoke(standalone=True)['ok'])
        result = self.invoke(expected=1)
        self.assertIn({'path': '$.binding.revision', 'code': 'stale_binding',
                       'message': 'Decision binding must match current task, scope, revision and attempt'},
                      result['errors'])
        self.decision['binding']['revision'] = 'r1'
        self.assertTrue(self.invoke()['ok'])

    def test_scope_mismatch_for_new_and_recorded_tasks(self):
        for planned in (False, True):
            with self.subTest(planned=planned):
                if planned:
                    self.planned()
                self.decision['binding']['scope'] = 'different-scope'
                self.assertTrue(any(e['path'] == '$.binding.scope' and e['code'] == 'stale_binding'
                                    for e in self.invoke(expected=1)['errors']))

    def test_new_planned_task_needs_no_record_membership(self):
        self.planned()
        self.record['tasks'] = []
        result = self.invoke()
        self.assertEqual(result['receipt']['record_sha256'],
                         hashlib.sha256(self.record_path.read_bytes()).hexdigest())
        self.assertEqual(result['receipt']['decision_sha256'],
                         hashlib.sha256(self.decision_path.read_bytes()).hexdigest())

    def test_unrecorded_nonplanned_task_rejected(self):
        self.decision['binding']['task'] = 'task-missing'
        self.assertIn('unknown_task', [e['code'] for e in self.invoke(expected=1)['errors']])

    def test_recorded_task_requires_current_dispatch(self):
        self.assertTrue(self.invoke()['ok'])
        for attempt, planned in [('dispatch-old', False), ('planned:task-1', True)]:
            with self.subTest(attempt=attempt):
                self.decision['binding'].update(attempt=attempt, planned=planned)
                self.assertTrue(any(e['path'] == '$.binding.attempt' and e['code'] == 'stale_binding'
                                    for e in self.invoke(expected=1)['errors']))

    def test_recorded_task_known_model_and_effort_use_existing_semantics(self):
        model = self.record['tasks'][0]['model']
        for field, selected in [('requested', 'model'), ('effort_requested', 'effort')]:
            with self.subTest(field=field):
                model[field] = 'different'
                self.assertTrue(any(e['path'] == '$.selected.' + selected and e['code'] == 'selected_mismatch'
                                    for e in self.invoke(expected=1)['errors']))
                model[field] = self.decision['selected'][selected]
        self.assertTrue(self.invoke()['ok'])

    def test_malformed_record_structures_do_not_pass(self):
        original = copy.deepcopy(self.record)
        for record in [None, [], {}, {**original, 'goal': []}, {**original, 'tasks': None},
                       {**original, 'goal': {**original['goal'], 'revision': ''}},
                       {**original, 'goal': {**original['goal'], 'scope': None}}]:
            with self.subTest(record=record):
                self.record = record
                self.assertTrue(self.invoke(expected=1)['errors'])

    def test_invalid_json_and_unreadable_record_are_input_errors(self):
        for raw in ['{', '{"goal":{},"goal":{}}', '{"version":NaN}']:
            with self.subTest(raw=raw):
                self.save()
                self.record_path.write_text(raw)
                self.assertEqual(self.invoke(expected=2, save=False)['errors'][0]['code'], 'input_read')
        self.save()
        self.record_path = self.root / 'missing.json'
        self.assertEqual(self.invoke(expected=2, save=False)['errors'][0]['code'], 'input_read')

    def test_stale_embedded_task_and_invalid_owner_record_rejected(self):
        self.record['tasks'][0]['goal_revision'] = 'r0'
        result = self.invoke(expected=1)
        self.assertTrue(any(e['path'] == '$.record.tasks[0].goal_revision' and e['code'] == 'goal_binding'
                            for e in result['errors']))
        self.record['tasks'][0]['goal_revision'] = 'r1'
        self.record['goal']['current_owner'] = 'unaccepted-owner'
        self.assertIn('unaccepted_owner', [e['code'] for e in self.invoke(expected=1)['errors']])

    def test_separate_record_and_decision_evidence_roots_and_tampering(self):
        for folder, evidence in [(self.record_path.parent, self.record['evidence']['plan']),
                                 (self.decision_path.parent, self.decision['evidence']['luna-ev'])]:
            path = folder / 'source.txt'
            path.write_text(folder.name)
            evidence.update(file='source.txt', sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertTrue(self.invoke()['ok'])
        for folder in [self.record_path.parent, self.decision_path.parent]:
            path = folder / 'source.txt'
            original = path.read_bytes()
            path.write_text('changed')
            self.assertIn('hash_mismatch', [e['code'] for e in self.invoke(expected=1)['errors']])
            path.write_bytes(original)

    def test_standalone_receipt_unchanged(self):
        result = self.invoke(standalone=True)
        self.assertEqual(set(result['receipt']),
                         {'format', 'binding', 'selected', 'limits', 'decision_sha256', 'configuration_sha256', 'price_selection'})

    def test_receipt_hashes_bind_checked_bytes_when_inputs_change_after_read(self):
        self.save()
        expected = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for name, path in [('record_sha256', self.record_path),
                                       ('decision_sha256', self.decision_path)]}
        original = record_check.check_routing

        def concurrent_writer(*args, **kwargs):
            result = original(*args, **kwargs)
            self.record_path.write_text('{}')
            self.decision_path.write_text('{}')
            return result

        output = io.StringIO()
        with patch.object(record_check, 'check_routing', side_effect=concurrent_writer), contextlib.redirect_stdout(output):
            code = record_check.main(['routing-check', str(self.decision_path),
                                      '--record', str(self.record_path), '--json'])
        self.assertEqual(code, 0)
        receipt = json.loads(output.getvalue())['receipt']
        for key, digest in expected.items():
            self.assertEqual(receipt[key], digest)

    def test_record_option_keeps_standalone_decision_validation(self):
        del self.decision['label']
        self.assertIn('required', [e['code'] for e in self.invoke(expected=1)['errors']])
        self.decision['label'] = 'synthetic'
        self.decision['binding']['planned'] = 'true'
        self.assertIn('type', [e['code'] for e in self.invoke(expected=1)['errors']])
        self.planned()
        self.decision['binding']['attempt'] = 'planned:another-task'
        self.assertIn('planned_binding', [e['code'] for e in self.invoke(expected=1)['errors']])


if __name__ == '__main__':
    unittest.main()
