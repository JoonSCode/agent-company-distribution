"""PreToolUse adapter checks without launching providers or Orca."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from routing_hook import bind, binding_path, guard
import test_route_select


class HookTests(unittest.TestCase):
    def test_session_binding_is_exclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp).resolve()
            bind(home, 'session-1', '/tmp/decision', '/tmp/record', home)
            path = binding_path(home, 'session-1')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text())['session_id'], 'session-1')
            with self.assertRaises(FileExistsError):
                bind(home, 'session-1', '/tmp/other', '/tmp/record', home)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            bind(home, 'session-1', '/tmp/other', '/tmp/record', home, digest)
            self.assertEqual(json.loads(path.read_text())['decision'], '/private/tmp/other')
            with self.assertRaises(FileExistsError):
                bind(home, 'session-1', '/tmp/decision', '/tmp/record', home, digest)

    def test_inactive_and_recognized_paths(self):
        fixture = test_route_select.SelectionCLITests()
        fixture.setUp()
        decision = fixture.packet()
        decision['binding'].update(task='task-1', attempt='dispatch-current', planned=False)
        decision['binding']['spec_sha256'] = hashlib.sha256(b'bounded helper').hexdigest()
        record = copy.deepcopy(json.loads((test_route_select.PACKAGE / 'assets/record-cases.json').read_text())['cases'][0]['record'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache_home = patch('record_check.canonical_home', return_value=root)
            cache_home.start()
            self.addCleanup(cache_home.stop)
            decision['label'] = 'real'
            for item in decision['evidence'].values():
                if item['kind'] == 'synthetic':
                    item['kind'] = 'host'
            inventory = root / 'models_cache.json'
            inventory.write_text(json.dumps({'models': decision['evidence']['inventory']['host_models']}))
            decision['evidence']['inventory'].update(file='models_cache.json', sha256=hashlib.sha256(inventory.read_bytes()).hexdigest(), observed_at='2020-01-01T00:00:00Z', valid_until='2100-01-01T00:00:00Z')
            dp, rp, scope = root / 'decision.json', root / 'record.json', root / 'scope.json'
            dp.write_text(json.dumps(decision))
            rp.write_text(json.dumps(record))
            scope.write_text(json.dumps({'session_id': 's', 'decision': str(dp), 'record': str(rp), 'receipt_dir': str(root)}))
            event = {'hook_event_name': 'PreToolUse', 'session_id': 's', 'tool_name': 'spawn_agent',
                     'tool_use_id': 'tool-1', 'tool_input': {'model': decision['selected']['model'],
                                                             'reasoning_effort': decision['selected']['effort'], 'message': 'bounded helper'}}
            self.assertEqual(guard(event, None), {})
            self.assertEqual(guard({**event, 'session_id': 'unrelated'}, str(scope)), {})
            self.assertEqual(guard({**event, 'tool_name': 'write_stdin'}, str(scope)), {})
            bad = {**event, 'tool_input': {'model': 'other', 'reasoning_effort': 'high'}}
            self.assertEqual(guard(bad, str(scope))['hookSpecificOutput']['permissionDecision'], 'deny')
            bad = {**event, 'tool_input': {**event['tool_input'], 'message': 'different'}}
            self.assertEqual(guard(bad, str(scope))['hookSpecificOutput']['permissionDecision'], 'deny')
            self.assertEqual(guard(event, str(scope)), {})
            self.assertTrue((root / 'tool-1.json').exists())
            raw = {**event, 'tool_name': 'Bash', 'tool_input': {'command': 'orca orchestration worker-start --model other'}}
            self.assertEqual(guard(raw, str(scope))['hookSpecificOutput']['permissionDecision'], 'deny')
            raw = {**event, 'tool_name': 'exec_command', 'tool_input': {'cmd': 'orca agent launch --model other'}}
            self.assertEqual(guard(raw, str(scope))['hookSpecificOutput']['permissionDecision'], 'deny')
            raw = {**event, 'tool_name': 'functions.exec', 'tool_input': {'code': 'tools.exec_command({cmd:"orca orchestration worker-start"})'}}
            self.assertEqual(guard(raw, str(scope))['hookSpecificOutput']['permissionDecision'], 'deny')
            raw = {**event, 'tool_name': 'Bash', 'tool_input': {'command': 'orca worktree create --name empty'}}
            self.assertEqual(guard(raw, str(scope)), {})
            raw = {**event, 'tool_name': 'Bash', 'tool_input': {'command': 'orca orchestration dispatch-show --dispatch some-id'}}
            self.assertEqual(guard(raw, str(scope)), {})
            for command in ('orca orchestration send --body "please run orca orchestration worker-start later"',
                            'orca orchestration reply --body "orca agent launch is a command example"',
                            'orca orchestration send --body ";" orca agent launch'):
                self.assertEqual(guard({**event, 'tool_name': 'exec_command', 'tool_input': {'cmd': command}}, str(scope)), {})
            raw = {**event, 'tool_name': 'Bash', 'tool_input': {'command': 'echo hello && orca agent launch --model other'}}
            self.assertEqual(guard(raw, str(scope))['hookSpecificOutput']['permissionDecision'], 'deny')
            raw = {**event, 'tool_name': 'Bash', 'tool_input': {'command': 'echo hello\norca agent launch --model other'}}
            self.assertEqual(guard(raw, str(scope))['hookSpecificOutput']['permissionDecision'], 'deny')
            for command in ('echo harmless;\norca agent launch --agent codex',
                            'echo harmless &&\norca orchestration worker-start --agent codex',
                            'echo harmless\n\norca worktree create --name probe --agent codex'):
                raw = {**event, 'tool_name': 'Bash', 'tool_input': {'command': command}}
                self.assertEqual(guard(raw, str(scope))['hookSpecificOutput']['permissionDecision'], 'deny')


if __name__ == '__main__':
    unittest.main()
