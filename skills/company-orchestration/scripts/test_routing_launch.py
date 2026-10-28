"""Synthetic prelaunch checks; no actual Orca worker is launched."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import routing_launch
import test_route_select


class LaunchTests(unittest.TestCase):
    def test_existing_task_retry_and_explicit_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            decision = {'binding': {'task': 'task', 'attempt': 'old', 'planned': False, 'parent_task': None,
                                    'run': 'run', 'spec_sha256': hashlib.sha256(b'original').hexdigest()}}
            task = {'id': 'task', 'current_dispatch': 'old', 'execution': {'state': 'settled', 'result': {'outcome': 'failed'}}}
            record = {'run': 'run', 'tasks': [task]}
            (root / 'decision').write_text(json.dumps(decision))
            (root / 'record').write_text(json.dumps(record))
            args = ['--decision', str(root / 'decision'), '--record', str(root / 'record'), '--receipt', str(root / 'receipt'),
                    '--result', str(root / 'result'), '--from', 'sender', '--task', 'task', '--retry-of', 'old', '--run', 'run', '--worktree', 'current']
            selected = {'route': 'codex', 'model': 'model', 'effort': 'high'}
            check = {'ok': True, 'label': 'real', 'errors': [], 'receipt': {'selected': selected}}
            listed = {'ok': True, 'result': {'runId': 'run', 'tasks': [{'id': 'task', 'run_id': 'run', 'parent_id': None, 'spec': 'original', 'status': 'failed'}]}}
            latest = {'ok': True, 'result': {'dispatch': {'id': 'old'}}}
            failed = {'ok': True, 'result': {'dispatch': {'id': 'old', 'taskId': 'task', 'runId': 'run', 'status': 'failed'}}}
            launched = {'ok': True, 'result': {'runId': 'run', 'taskId': 'task', 'dispatchId': 'new', 'launch': {'effective': {'agent': 'codex', 'model': 'model', 'effort': 'high'}}}}
            def response(value):
                return SimpleNamespace(returncode=0, stdout=json.dumps(value), stderr='')
            with patch('routing_launch.check_routing', return_value=copy.deepcopy(check)), patch('routing_launch.subprocess.run', side_effect=[response(listed), response(latest), response(failed), response(launched)]) as host:
                self.assertEqual(routing_launch.main(args), 0)
                command = host.call_args.args[0]
                self.assertEqual(command[command.index('--task') + 1], 'task')
                self.assertEqual(command[command.index('--retry-of') + 1], 'old')
                self.assertEqual(command[command.index('--run') + 1], 'run')
                self.assertNotIn('--spec', command)
            for index, (changed, expected_calls) in enumerate([('spec', 3), ('dispatch', 3), ('run', 0), ('record', 0)]):
                args[args.index('--receipt') + 1] = str(root / f'receipt-{index}')
                args[args.index('--result') + 1] = str(root / f'result-{index}')
                bad_list, bad_latest = copy.deepcopy(listed), copy.deepcopy(latest)
                if changed == 'spec': bad_list['result']['tasks'][0]['spec'] = 'changed'
                if changed == 'dispatch': bad_latest['result']['dispatch']['id'] = 'newer'
                if changed == 'run': args[args.index('--run') + 1] = 'wrong'
                if changed == 'record':
                    args[args.index('--run') + 1] = 'run'
                    record['tasks'][0]['execution']['result']['outcome'] = 'succeeded'
                    (root / 'record').write_text(json.dumps(record))
                with patch('routing_launch.check_routing', return_value=copy.deepcopy(check)), patch('routing_launch.subprocess.run', side_effect=[response(bad_list), response(bad_latest), response(failed)]) as host:
                    self.assertEqual(routing_launch.main(args), 1)
                    self.assertEqual(host.call_count, expected_calls)
            for invalid in (['--spec', 'extra'],):
                with self.assertRaises(SystemExit): routing_launch.main(args + invalid)
            record['tasks'][0]['execution']['result']['outcome'] = 'failed'
            (root / 'record').write_text(json.dumps(record))
            for index, mutation in enumerate(('missing_run', 'wrong_run', 'wrong_task', 'same_dispatch', 'missing_settings', 'nonzero')):
                args[args.index('--receipt') + 1] = str(root / f'readback-pre-{index}')
                result_path = root / f'readback-post-{index}'
                args[args.index('--result') + 1] = str(result_path)
                payload = copy.deepcopy(launched)
                if mutation == 'missing_run': del payload['result']['runId']
                if mutation == 'wrong_run': payload['result']['runId'] = 'other'
                if mutation == 'wrong_task': payload['result']['taskId'] = 'other'
                if mutation == 'same_dispatch': payload['result']['dispatchId'] = 'old'
                if mutation == 'missing_settings': del payload['result']['launch']
                final = response(payload)
                if mutation == 'nonzero': final.returncode = 1
                with patch('routing_launch.check_routing', return_value=copy.deepcopy(check)), patch('routing_launch.subprocess.run', side_effect=[response(listed), response(latest), response(failed), final]) as host:
                    self.assertEqual(routing_launch.main(args), 1)
                    self.assertEqual(host.call_count, 4)
                    saved = json.loads(result_path.read_text())
                    self.assertEqual(saved['stdout'], final.stdout)
                    self.assertNotEqual(saved['readback_status'], 'observed')
            decision['binding'].update(attempt='planned:task', planned=True)
            (root / 'decision').write_text(json.dumps(decision))
            task['current_dispatch'] = 'planned:task'
            task['execution'] = {'state': 'unknown', 'result': None}
            (root / 'record').write_text(json.dumps(record))
            initial_list = copy.deepcopy(listed)
            initial_list['result']['tasks'][0]['status'] = 'pending'
            initial_args = args.copy()
            i = initial_args.index('--retry-of')
            del initial_args[i:i + 2]
            initial_args[initial_args.index('--receipt') + 1] = str(root / 'first-pre')
            initial_args[initial_args.index('--result') + 1] = str(root / 'first-post')
            with patch('routing_launch.check_routing', return_value=copy.deepcopy(check)), patch('routing_launch.subprocess.run', side_effect=[response(initial_list), response(launched)]) as host:
                self.assertEqual(routing_launch.main(initial_args), 0)
                self.assertNotIn('--retry-of', host.call_args.args[0])
            initial_list['result']['tasks'][0]['status'] = 'ready'
            initial_args[initial_args.index('--receipt') + 1] = str(root / 'ready-pre')
            initial_args[initial_args.index('--result') + 1] = str(root / 'ready-post')
            with patch('routing_launch.check_routing', return_value=copy.deepcopy(check)), patch('routing_launch.subprocess.run', side_effect=[response(initial_list), response(launched)]) as host:
                self.assertEqual(routing_launch.main(initial_args), 0)
                self.assertEqual(host.call_count, 2)

    def test_reuse_requires_original_effective_and_same_live_incarnation(self):
        fixture = test_route_select.SelectionCLITests()
        fixture.setUp()
        packet = fixture.packet()
        packet['binding'].update(task='new', attempt='planned:new', planned=True,
                                 spec_sha256=hashlib.sha256(b'reuse task').hexdigest())
        record = copy.deepcopy(json.loads((test_route_select.PACKAGE / 'assets/record-cases.json').read_text())['cases'][0]['record'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache_home = patch('record_check.canonical_home', return_value=root)
            cache_home.start()
            self.addCleanup(cache_home.stop)
            packet['label'] = 'real'
            for item in packet['evidence'].values():
                if item['kind'] == 'synthetic':
                    item['kind'] = 'host'
            inventory = root / 'models_cache.json'
            inventory.write_text(json.dumps({'models': packet['evidence']['inventory']['host_models']}))
            packet['evidence']['inventory'].update(file='models_cache.json', sha256=hashlib.sha256(inventory.read_bytes()).hexdigest(), observed_at='2020-01-01T00:00:00Z', valid_until='2100-01-01T00:00:00Z')
            binding = {'dispatch': 'origin', 'terminal': 'term', 'incarnation': 'inc', 'settings_unchanged': True,
                       'observed_at': '2020-01-01T00:00:00Z', 'valid_until': '2100-01-01T00:00:00Z'}
            prior = root / 'unchanged.json'
            prior.write_text(json.dumps(binding))
            packet['evidence']['reuse'] = {'kind': 'host', 'ref': 'fixture:reuse', 'file': prior.name,
                                           'sha256': hashlib.sha256(prior.read_bytes()).hexdigest(), 'reuse_binding': binding}
            origin = {'ok': True, 'result': {'dispatchId': 'origin', 'launch': {'effective': {'agent': 'codex',
                      'model': packet['selected']['model'], 'effort': packet['selected']['effort']}},
                      'prompt': {'processIncarnation': 'inc'}, 'effects': [{'kind': 'terminal', 'id': 'term'}]}}
            origin_path = root / 'origin.json'
            origin_path.write_text(json.dumps(origin))
            packet['reuse_evidence'] = {'origin_sha256': hashlib.sha256(origin_path.read_bytes()).hexdigest(), 'unchanged_evidence': 'reuse'}
            decision, current = root / 'decision.json', root / 'record.json'
            decision.write_text(json.dumps(packet))
            current.write_text(json.dumps(record))
            args = ['--decision', str(decision), '--record', str(current), '--receipt', str(root / 'receipt.json'),
                    '--result', str(root / 'result.json'), '--from', 'sender', '--spec', 'reuse task',
                    '--worktree', 'current', '--terminal', 'term', '--reuse-dispatch', 'origin', '--origin-receipt', str(origin_path)]
            live = {'ok': True, 'result': {'terminal': {'handle': 'term', 'incarnationId': 'inc'},
                    'dispatch': {'assigneeHandle': 'term', 'processIncarnation': 'pty:inc'},
                    'projection': {'liveness': {'verdict': 'live'}},
                    'observation': {'status': 'live', 'exactWorker': True}}}
            probe = SimpleNamespace(returncode=0, stdout=json.dumps(live), stderr='')
            result = SimpleNamespace(returncode=0, stdout=json.dumps({'ok': True, 'result': {'taskId': 'new-task', 'dispatchId': 'new-dispatch', 'effects': [{'kind': 'terminal', 'id': 'term'}]}}), stderr='')
            with patch('routing_launch.subprocess.run', side_effect=[probe, result]) as host:
                self.assertEqual(routing_launch.main(args), 0)
                command = host.call_args.args[0]
                self.assertIn('--terminal', command)
                self.assertNotIn('--model', command)
            live['result']['terminal']['incarnationId'] = 'different'
            probe.stdout = json.dumps(live)
            args[args.index('--receipt') + 1] = str(root / 'receipt-2.json')
            args[args.index('--result') + 1] = str(root / 'result-2.json')
            with patch('routing_launch.subprocess.run', return_value=probe) as host:
                self.assertEqual(routing_launch.main(args), 1)
                self.assertEqual(host.call_count, 1)
            live['result']['terminal']['incarnationId'] = 'inc'
            live['result']['projection']['liveness']['verdict'] = 'unverifiable'
            probe.stdout = json.dumps(live)
            with patch('routing_launch.subprocess.run', return_value=probe) as host:
                self.assertEqual(routing_launch.main(args), 1)
                self.assertEqual(host.call_count, 1)

    def test_rejected_and_valid_packet_before_fake_host(self):
        fixture = test_route_select.SelectionCLITests()
        fixture.setUp()
        packet = fixture.packet()
        packet['binding'].update(task='new', attempt='planned:new', planned=True)
        packet['binding']['spec_sha256'] = hashlib.sha256(b'bounded test').hexdigest()
        packet['binding']['parent_task'] = 'parent-task'
        record = copy.deepcopy(json.loads((test_route_select.PACKAGE / 'assets/record-cases.json').read_text())['cases'][0]['record'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache_home = patch('record_check.canonical_home', return_value=root)
            cache_home.start()
            self.addCleanup(cache_home.stop)
            packet['label'] = 'real'
            for item in packet['evidence'].values():
                if item['kind'] == 'synthetic':
                    item['kind'] = 'host'
            inventory = root / 'models_cache.json'
            inventory.write_text(json.dumps({'models': packet['evidence']['inventory']['host_models']}))
            packet['evidence']['inventory'].update(file='models_cache.json', sha256=hashlib.sha256(inventory.read_bytes()).hexdigest(), observed_at='2020-01-01T00:00:00Z', valid_until='2100-01-01T00:00:00Z')
            decision, current, receipt = root / 'decision.json', root / 'record.json', root / 'receipt.json'
            current.write_text(json.dumps(record))
            args = ['--decision', str(decision), '--record', str(current), '--receipt', str(receipt), '--result', str(root / 'host.json'),
                    '--from', 'term-example', '--spec', 'bounded test', '--worktree', 'current', '--parent', 'parent-task']
            invalid = copy.deepcopy(packet)
            invalid['price_selection']['candidates'].pop()
            decision.write_text(json.dumps(invalid))
            with patch('routing_launch.subprocess.run') as host:
                self.assertEqual(routing_launch.main(args), 1)
                host.assert_not_called()
                self.assertFalse(receipt.exists())
            decision.write_text(json.dumps(packet))
            bad_parent = args.copy()
            bad_parent[bad_parent.index('--parent') + 1] = 'wrong-parent'
            with patch('routing_launch.subprocess.run') as host:
                self.assertEqual(routing_launch.main(bad_parent), 1)
                host.assert_not_called()
            with patch('routing_launch.subprocess.run') as host:
                with self.assertRaises(SystemExit):
                    routing_launch.main(args + ['--model', 'other'])
                host.assert_not_called()
            bound = copy.deepcopy(packet)
            bound['binding']['run'] = 'intended-run'
            record['run'] = 'intended-run'
            decision.write_text(json.dumps(bound))
            current.write_text(json.dumps(record))
            with patch('routing_launch.subprocess.run') as host:
                self.assertEqual(routing_launch.main(args), 1)
                host.assert_not_called()
            record.pop('run')
            current.write_text(json.dumps(record))
            decision.write_text(json.dumps(packet))
            with patch('routing_launch.subprocess.run') as host:
                host.return_value.returncode = 0
                host.return_value.stdout = json.dumps({'ok': True, 'result': {'taskId': 'task-host', 'dispatchId': 'dispatch-host',
                    'launch': {'effective': {'agent': 'codex', 'model': packet['selected']['model'], 'effort': packet['selected']['effort']}}}})
                host.return_value.stderr = ''
                self.assertEqual(routing_launch.main(args), 0)
                command = host.call_args.args[0]
                self.assertEqual(command[command.index('--model') + 1], packet['selected']['model'])
                self.assertEqual(command[command.index('--effort') + 1], packet['selected']['effort'])
                self.assertEqual(command[command.index('--parent') + 1], 'parent-task')
                self.assertTrue(receipt.exists())
                self.assertIn('task-host', (root / 'host.json').read_text())
            for index, (payload, expected) in enumerate([
                ({'ok': True, 'result': {'taskId': 'task', 'dispatchId': 'dispatch'}}, 'unverified'),
                ({'ok': True, 'result': {'taskId': 'task', 'dispatchId': 'dispatch', 'launch': {'effective': {'agent': 'codex', 'model': 'wrong', 'effort': packet['selected']['effort']}}}}, 'failed'),
            ]):
                args[args.index('--receipt') + 1] = str(root / ('pre-' + str(index)))
                result_path = root / ('post-' + str(index))
                args[args.index('--result') + 1] = str(result_path)
                with patch('routing_launch.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr='')) as host:
                    self.assertEqual(routing_launch.main(args), 1)
                    self.assertEqual(host.call_count, 1)
                    self.assertEqual(json.loads(result_path.read_text())['readback_status'], expected)


if __name__ == '__main__':
    unittest.main()
