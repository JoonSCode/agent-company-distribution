"""PreToolUse adapter checks without launching providers or Orca."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from routing_hook import bind, binding_path, guard, raw_launch
import test_route_select


class HookTests(unittest.TestCase):
    def test_completion_registration_distinguishes_missing_routing_scope(self):
        from completion_hook import register_session
        from routing_hook import registered_company
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            run = home / 'runs' / 'company'
            run.mkdir(parents=True)
            record = run / 'record.json'
            record.write_text(json.dumps({'goal': {'status': 'active'}}))
            register_session(home, 'company', run, 'company', 'owner', home, 'record.json')
            self.assertFalse(registered_company(home, 'unrelated'))
            self.assertTrue(registered_company(home, 'company'))
            event = {'hook_event_name': 'PreToolUse', 'session_id': 'company',
                     'tool_name': 'spawn_agent', 'tool_input': {}}
            self.assertEqual(guard(event, None, company_session=True)['hookSpecificOutput']['permissionDecision'], 'deny')
            self.assertEqual(guard(event, None, company_session=False), {})
            self.assertEqual(guard({**event, 'tool_name': 'write_stdin'}, None, company_session=True), {})
            env = dict(os.environ, SEJONG_HOME=str(home))
            env.pop('COMPANY_ROUTING_SCOPE', None)
            cmd = [sys.executable, '-B', str(Path(__file__).with_name('routing_hook.py'))]
            for observed, denied in ((event, True), ({**event, 'session_id': 'unrelated'}, False)):
                result = subprocess.run(cmd, input=json.dumps(observed), text=True, capture_output=True, env=env, check=True)
                self.assertEqual(bool(json.loads(result.stdout)), denied)
            record.write_text(json.dumps({'goal': {'status': 'succeeded'}}))
            self.assertTrue(registered_company(home, 'company'))
            record.write_text(json.dumps({'goal': {'status': 'failed'}}))
            self.assertTrue(registered_company(home, 'company'))
            record.write_text('{broken')
            self.assertTrue(registered_company(home, 'company'))
            # Explicit Company exit writes a session-bound routing marker;
            # it does not remove the independent completion registration.
            exit_result = subprocess.run(cmd + ['exit', '--session', 'company'], text=True, capture_output=True, env=env)
            self.assertEqual(exit_result.returncode, 0, exit_result.stderr)
            response = subprocess.run(cmd, input=json.dumps(event), text=True, capture_output=True, env=env, check=True)
            self.assertEqual(json.loads(response.stdout), {})
            self.assertTrue(registered_company(home, 'company'))
            marker = binding_path(home, 'company')
            original = hashlib.sha256(marker.read_bytes()).hexdigest()
            failed = subprocess.run(cmd + ['exit', '--session', 'company'], text=True, capture_output=True, env=env)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(hashlib.sha256(marker.read_bytes()).hexdigest(), original)

    def test_continuation_scope_and_completion_paths(self):
        def detected(command):
            return raw_launch('exec_command', {'cmd': command})
        self.assertTrue(detected('orca orchestration send --to dispatch:worker --body next'))
        self.assertTrue(detected('orca orchestration send --to=term_worker --body next'))
        self.assertFalse(detected('orca orchestration send --to run:coordinator --type status --body ready'))
        self.assertFalse(detected('orca orchestration send --type worker_done --to dispatch:worker'))
        self.assertFalse(detected('orca orchestration send --type escalation --body blocked'))
        self.assertFalse(detected('orca orchestration ask --question why'))
        self.assertFalse(detected('orca orchestration reply --id id --body answer'))
        with tempfile.TemporaryDirectory() as temp:
            scope = Path(temp) / 'scope.json'
            scope.write_text(json.dumps({'session_id': 'other'}))
            event = {'hook_event_name': 'PreToolUse', 'session_id': 'current',
                     'tool_name': 'exec_command', 'tool_input': {'cmd': 'orca orchestration worker-start'}}
            self.assertEqual(guard(event, str(scope)), {})

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        home = root / 'home'
        home.mkdir()
        config = root / 'user.md'
        config.write_text('---\nschema_version: 1\npreset: single\nservices: ["codex"]\napi_paid: false\n---\n')
        env = dict(os.environ)
        env.update(HOME=str(home), CODEX_HOME=str(root / 'codex'), AGENT_COMPANY_CONFIG=str(config))
        env.pop('AGENT_COMPANY_TASK_CONFIG', None)
        scope = patch.dict(os.environ, env, clear=True)
        scope.start()
        self.addCleanup(scope.stop)

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
        from record_check import make_profile_binding
        fixture = test_route_select.SelectionCLITests()
        fixture.setUp()
        decision = fixture.packet()
        decision['binding'].update(task='task-1', attempt='dispatch-current', planned=False)
        decision['binding']['spec_sha256'] = hashlib.sha256(b'bounded helper').hexdigest()
        profile = json.loads((test_route_select.PACKAGE / 'assets/worker-profile-example.json').read_text())
        profile['units'][0]['id'] = 'task-1'
        table = json.loads((test_route_select.PACKAGE / 'assets/worker-routing-table.json').read_text())
        for row in table['entries']:
            row['candidates'][0].update(input_modalities=['text'], output_modalities=['text'], capabilities=['general.execute'], evidence=['synthetic assertion'])
        decision['profile_binding'] = make_profile_binding(profile, table, 'task-1')
        self.addCleanup(fixture.doCleanups)
        fixture.authorize_profile(decision)
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
            no_config = dict(os.environ)
            no_config.pop('AGENT_COMPANY_CONFIG', None)
            no_config.pop('AGENT_COMPANY_TASK_CONFIG', None)
            with patch.dict(os.environ, no_config, clear=True):
                self.assertEqual(guard(event, str(scope))['hookSpecificOutput']['permissionDecision'], 'deny')
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
