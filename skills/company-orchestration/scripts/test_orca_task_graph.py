"""Contract fixtures for a local Orca Task capture and its portable view."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import status_tui
import status_tui_input
from orca_task_graph import task_graph
from record_check import Checker, check_profile_binding, make_profile_binding


def capture():
    return {'ok': True, '_meta': {'runtimeId': 'runtime'}, 'result': {
        'runId': 'run', 'count': 2, 'tasks': [
            {'id': 'a', 'run_id': 'run', 'task_title': 'Capture A', 'status': 'ready', 'deps': '[]',
             'parent_id': None, 'dispatch_id': None, 'spec': 'private specification'},
            {'id': 'b', 'run_id': 'run', 'task_title': 'Verify B', 'status': 'pending', 'deps': '["a"]',
             'parent_id': None, 'dispatch_id': None},
        ],
    }}


class TaskGraphTests(unittest.TestCase):
    def test_route_dependency_binding_also_matches_prepared_profile(self):
        assets = Path(__file__).parents[1] / 'assets'
        profile = json.loads((assets / 'worker-profile-example.json').read_text())
        profile['units'].append({**profile['units'][0], 'id': 'two', 'depends_on': ['one']})
        table = json.loads((assets / 'worker-routing-table.json').read_text())
        prepared = make_profile_binding(profile, table, 'two')
        for needs, matches in [(['one'], True), ([], False), (['unreviewed'], False)]:
            with self.subTest(needs=needs):
                checker = Checker(assets)
                check_profile_binding(checker, {'binding': {'task': 'two', 'task_deps': needs},
                    'selected': prepared['selected'], 'profile_binding': prepared}, '$')
                self.assertEqual(not checker.errors, matches, checker.errors)

    def test_exact_graph_and_invalid_host_captures(self):
        document = capture()
        graph = task_graph(document, 'run')
        self.assertEqual(graph['b']['needs'], ['a'])
        self.assertIsNone(graph['b']['parent_id'])
        self.assertNotIn('spec', graph['a'])
        document['result']['tasks'].reverse()
        self.assertEqual(list(task_graph(document, 'run')), ['a', 'b'])
        document['result']['tasks'].reverse()
        for replacement in ('["missing"]', '["b"]', '["a","a"]', {'a': 1}):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                broken = copy.deepcopy(document)
                broken['result']['tasks'][1]['deps'] = replacement
                task_graph(broken, 'run')
        document['result']['page'] = {'hasMore': True}
        with self.assertRaises(ValueError):
            task_graph(document, 'run')

    def test_view_joins_host_tasks_without_adding_acceptance(self):
        document = capture()
        view = {'tasks': [{'id': 'b', 'state': 'ACC', 'current_dispatch': 'planned:b'}],
                'dependencies': [], 'warnings': []}
        proc = subprocess.CompletedProcess([], 0, json.dumps(document).encode(), b'')
        with patch('status_tui_input.subprocess.run', return_value=proc) as host:
            status_tui_input._attach_orca_tasks(view, 'run')
        self.assertIn('--full', host.call_args.args[0])
        self.assertEqual([task['state'] for task in view['tasks']], ['?', '?'])
        self.assertEqual(view['tasks'][1]['host_status'], 'pending')
        self.assertEqual(view['tasks'][1]['needs'], ['a'])
        self.assertIn('Orca Tasks', status_tui._provenance(view, ascii=True))
        self.assertNotIn('private specification', json.dumps(view))
        with patch('status_tui_input.subprocess.run', return_value=proc):
            with self.assertRaisesRegex(ValueError, 'differ from attached plan'):
                status_tui_input._attach_orca_tasks({
                    'tasks': [], 'dependencies': [{'task': 'b', 'needs': []}], 'warnings': [],
                }, 'run')

    def test_reviewed_plan_comparison_rejects_a_valid_but_missing_edge(self):
        profile = {'version': 1, 'vocabulary_version': 1, 'family': 'code', 'difficulty': 'easy',
                   'input_modalities': ['text'], 'output_modalities': ['text'],
                   'required_capabilities': ['code.reason'], 'required_tools': [],
                   'context_requirement': 'not_applicable', 'hard_constraints': [], 'uncertainties': []}
        first = {'id': 'a', 'objective': 'Capture', 'inputs': ['accepted change'],
                 'deliverables': ['capture'], 'done_when': ['capture is readable'],
                 'depends_on': [], 'profile': profile}
        second = {**first, 'id': 'b', 'objective': 'Verify', 'depends_on': ['a']}
        with tempfile.TemporaryDirectory() as temp:
            accepted, candidate = (Path(temp) / name for name in ('accepted.json', 'candidate.json'))
            accepted.write_text(json.dumps({'version': 1, 'units': [first, second]}))
            script = Path(__file__).with_name('worker_profile.py')
            argv = [sys.executable, '-B', str(script), 'compare', str(candidate), str(accepted)]
            candidate.write_text(json.dumps({'version': 1, 'units': [second, first]}))
            result = subprocess.run(argv, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout)
            candidate.write_text(json.dumps({'version': 1, 'units': [first, {**second, 'depends_on': []}]}))
            result = subprocess.run(argv, capture_output=True, check=False)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertEqual(json.loads(result.stdout)['changed'], {'b': ['depends_on']})

    def test_view_requires_current_dispatch_in_same_task_snapshot(self):
        for current, expected in [('ctx_a', 'model-a'), ('ctx_new', None), (None, None)]:
            with self.subTest(current=current):
                document = capture()
                document['result']['tasks'][0].update(status='completed', dispatch_id=current)
                snapshot = {'tasks': [{'id': 'a', 'state': 'DONE', 'current_dispatch': 'ctx_a',
                                       'assigned_model': 'model-a', 'model_basis': 'assigned'}],
                            'dependencies': [], 'warnings': []}
                response = subprocess.CompletedProcess([], 0, json.dumps(document).encode(), b'')
                with patch('status_tui_input.subprocess.run', return_value=response) as host:
                    status_tui_input._attach_orca_tasks(snapshot, 'run')
                self.assertEqual([call.args[0][2] for call in host.call_args_list], ['task-list'])
                shown = snapshot['tasks'][0]
                self.assertEqual(shown.get('assigned_model'), expected)
                self.assertEqual(shown['state'], 'DONE' if expected else '?')
                self.assertEqual(shown['host_status'], 'completed')
                if current is None:
                    self.assertEqual(shown['current_dispatch'], None)
                    self.assertEqual(status_tui.graph.model_label(shown), '실행 상세 확인 중')
                if expected:
                    model_label = 'Assigned: model-a'
                elif current is None:
                    model_label = 'Execution details pending'
                else:
                    model_label = 'Model unknown'
                self.assertEqual(status_tui.wide.content(shown, 80, ascii=True)[0]['model'], model_label)
                self.assertIn(model_label, status_tui.graph.task_fields(shown, '@1', 80, False, ascii=True))
                narrow = status_tui.navigation.plan(snapshot, status_tui.navigation.State(), 30, 4, ascii=True)
                self.assertIn(model_label, [line for page in narrow['pages'] for line in page])
