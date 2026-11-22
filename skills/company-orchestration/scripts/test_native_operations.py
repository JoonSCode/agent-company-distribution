"""Native CLI conformance, owned disposable data; no real model or host calls.

Run with Python -B -m unittest test_native_operations -v. NATIVE_OPS_RECEIPTS
optionally appends exact child CLI receipts to an explicitly owned artifact.
"""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

CLI = Path(__file__).with_name('native_operations.py')
PACKAGE = CLI.parent.parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin(path):
    return {'path': str(path), 'sha256': digest(path)}


def save(path, value):
    path.write_text(json.dumps(value) + '\n')
    return path


def tree(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


class NativeCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix='company-native-')))
        self.env = {k: os.environ[k] for k in ('PATH', 'TMPDIR', 'NATIVE_OPS_RECEIPTS', 'PYTHONPATH') if k in os.environ}
        self.env.update(HOME=str(self.root), CODEX_HOME=str(self.root / 'codex'),
                        PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
                        UV_OFFLINE='1', UV_PYTHON_DOWNLOADS='never')

    def cli(self, *args, expected=0, env=None):
        argv = [sys.executable, '-B', str(CLI), *map(str, args)]
        process = subprocess.run(argv, env=env or self.env, cwd=self.root,
                                 capture_output=True, text=True, timeout=60)
        receipt = {'argv': argv, 'cwd': str(self.root), 'exit': process.returncode,
                   'stdout': process.stdout, 'stderr': process.stderr,
                   'product_origin': str(CLI)}
        if destination := os.environ.get('NATIVE_OPS_RECEIPTS'):
            with Path(destination).open('a') as stream:
                stream.write(json.dumps(receipt) + '\n')
        self.assertEqual(process.returncode, expected, receipt)
        self.assertNotIn('Traceback', process.stderr)
        return json.loads(process.stdout)


class UsageTests(NativeCase):
    def setUp(self):
        super().setUp()
        fields = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
                  'output_tokens', 'reasoning_output_tokens', 'total_tokens')
        counts = dict(zip(fields, (10, 3, 0, 5, 2, 15)))
        response = dict(thread_id='session', session_id='session', turn_id='turn',
                        root_turn_id='turn', response_id='response', usage=counts,
                        turn_token_usage=counts, thread_token_usage=counts)
        rows = [{'type': 'session_meta', 'payload': {'id': 'session'}},
                {'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': 'turn'}},
                {'type': 'token_usage_record', 'payload': response},
                {'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {
                    'total_token_usage': counts, 'last_token_usage': counts}}},
                {'type': 'event_msg', 'payload': {'type': 'task_complete', 'turn_id': 'turn'}}]
        self.trace = self.root / 'trace.jsonl'
        self.trace.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        self.binding = self.root / 'binding.json'
        self.identity = dict(provider='codex', session_id='session', turn_id='turn', run_id='run',
                             task_id='task', dispatch_id='dispatch', actor='worker', model='fixture-model')
        save(self.binding, self.identity)
        self.source = dict(id='a', provider='codex', trace=str(self.trace), sha256=digest(self.trace),
                           turn_id='turn', scope='executor', run_id='run', task_id='task',
                           dispatch_id='dispatch', actor='worker', model='fixture-model',
                           binding={**pin(self.binding), 'pointer': ''})
        self.request = dict(schema='company-native-usage-request/v1', required_scopes=['executor'],
                            sources=[self.source])
        self.request_path = self.root / 'request.json'

    def report(self, expected=0):
        save(self.request_path, self.request)
        return self.cli('usage', 'report', '--request', self.request_path, expected=expected)

    def test_u01_bound_parser_and_breakdowns(self):
        result = self.report()
        self.assertEqual(result['schema'], 'company-native-usage/v1')
        self.assertEqual((result['coverage'], result['observed_raw_total'], result['total_raw_tokens']),
                         ('complete', 15, 15))
        for key in ('run', 'task', 'actor', 'model', 'capture'):
            self.assertTrue(result['breakdown'][key])
            self.assertEqual(result['breakdown'][key][0]['total_raw_tokens'], 15)

    def test_u02_duplicate_exports_union_once(self):
        self.request['sources'].append({**self.source, 'id': 'again'})
        result = self.report()
        self.assertEqual(result['observed_raw_total'], 15)
        self.assertEqual(result['deduped_response_count'], 1)
        self.assertEqual(result['duplicate_response_count'], 1)

    def test_u03_conflicting_response_identity_rejected(self):
        other = self.root / 'other.jsonl'
        other.write_bytes(self.trace.read_bytes().replace(b'"session"', b'"different"'))
        binding = self.root / 'other-binding.json'
        save(binding, {**self.identity, 'session_id': 'different'})
        self.request['sources'].append({**self.source, 'id': 'other', 'trace': str(other),
                                       'sha256': digest(other), 'binding': {**pin(binding), 'pointer': ''}})
        self.report(expected=2)

    def test_u04_shared_response_is_not_allocated_twice(self):
        binding = self.root / 'shared.json'
        save(binding, {**self.identity, 'task_id': 'other', 'dispatch_id': 'other-dispatch'})
        self.request['sources'].append({**self.source, 'id': 'other', 'scope': 'reviewer',
            'task_id': 'other', 'dispatch_id': 'other-dispatch', 'binding': {**pin(binding), 'pointer': ''}})
        result = self.report()
        self.assertEqual(result['total_raw_tokens'], 15)
        groups = result['breakdown']['task']
        self.assertEqual(sum(x['observed_raw_total'] or 0 for x in groups), 15)
        self.assertTrue(any(x['id'] == 'shared/unallocated' for x in groups))

    def test_task_identity_does_not_merge_same_local_id_across_runs(self):
        binding = self.root / 'other-run.json'
        save(binding, {**self.identity, 'run_id': 'other-run'})
        self.request['sources'].append({**self.source, 'id': 'other-run', 'run_id': 'other-run',
                                        'binding': {**pin(binding), 'pointer': ''}})
        result = self.report()
        self.assertEqual(result['observed_raw_total'], 15)
        self.assertEqual(result['breakdown']['task'][0]['id'], 'shared/unallocated')
        self.assertIsNone(result['breakdown']['task'][0]['total_raw_tokens'])

    def test_u05_missing_required_scope_is_null_not_zero(self):
        self.request['required_scopes'].append('reviewer')
        result = self.report()
        self.assertIsNone(result['total_raw_tokens'])
        self.assertEqual(result['missing_required_scopes'], ['reviewer'])
        self.assertEqual(result['observed_raw_total'], 15)

    def test_u05_unknown_attribution_not_fabricated(self):
        self.source['actor'] = self.source['model'] = None
        save(self.binding, {**self.identity, 'actor': None, 'model': None})
        self.source['binding'] = {**pin(self.binding), 'pointer': ''}
        result = self.report()
        self.assertEqual(result['breakdown']['actor'][0]['id'], 'unknown')
        self.assertEqual(result['breakdown']['actor'][0]['attribution'], 'unknown')

    def test_u05_unbound_and_partial_capture_are_incomplete(self):
        self.source['binding'] = None
        self.assertIsNone(self.report()['total_raw_tokens'])
        self.source['binding'] = {**pin(self.binding), 'pointer': ''}
        self.trace.write_bytes(self.trace.read_bytes().split(b'{"type": "event_msg", "payload": {"type": "task_complete"')[0])
        self.source['sha256'] = digest(self.trace)
        result = self.report()
        self.assertEqual(result['coverage'], 'partial')
        self.assertIsNone(result['total_raw_tokens'])

    def test_u06_unsupported_provider_unknown_no_billing(self):
        self.source['provider'] = 'other-provider'
        result = self.report()
        self.assertIsNone(result['observed_raw_total'])
        self.assertIsNone(result['total_raw_tokens'])
        self.assertEqual(result['unsupported_source_count'], 1)
        self.assertNotIn('billing', result)
        self.assertNotIn('savings', result)
        self.assertNotIn('skill', result['breakdown'])

    def test_binding_hash_pointer_and_claim_conflicts_reject(self):
        for change in ('hash', 'pointer', 'actor'):
            with self.subTest(change=change):
                original = copy.deepcopy(self.source)
                if change == 'hash': self.source['binding']['sha256'] = '0' * 64
                if change == 'pointer': self.source['binding']['pointer'] = '/absent'
                if change == 'actor': self.source['actor'] = 'invented'
                self.report(expected=2)
                self.source.clear(); self.source.update(original)

    def test_strict_json_schema_and_duplicate_source_ids(self):
        save(self.request_path, {**self.request, 'surprise': True})
        self.cli('usage', 'report', '--request', self.request_path, expected=2)
        self.request_path.write_text('{"schema":1,"schema":2}')
        self.cli('usage', 'report', '--request', self.request_path, expected=2)
        self.request['sources'].append(copy.deepcopy(self.source))
        self.report(expected=2)


class StorageTests(NativeCase):
    def setUp(self):
        super().setUp()
        import run_completion as rc
        from test_run_completion import ordinary_routing
        self.rc = rc
        self.home = self.root / 'sejong'
        self.run_root = self.home / 'runs/native-fixture'
        self.run_root.mkdir(parents=True)
        (self.run_root / 'scratch').mkdir()
        (self.run_root / 'scratch/raw').write_bytes(b'disposable only')
        (self.run_root / 'report.md').write_text('retained evidence')
        (self.run_root / 'acceptance.json').write_text('{"accepted":true}')
        self.config = self.root / 'user.md'
        self.config.write_text('---\nschema_version: 1\npreset: single\nservices: ["antigravity"]\n---\n')
        self.env['AGENT_COMPANY_CONFIG'] = str(self.config)
        self.enterContext(patch.dict(os.environ, {'AGENT_COMPANY_CONFIG': str(self.config)}))
        self.retention('init', '--run-id', 'goal-1', '--owner', 'B')
        self.retention('register', '--disposable', 'scratch/raw', '--preserve', 'report.md',
                       '--preserve', 'acceptance.json')
        cases = json.loads((PACKAGE / 'assets/record-cases.json').read_bytes())['cases']
        self.record = copy.deepcopy(next((x['record'] for x in cases if x['name'] == 'required-resource-record-valid'), cases[0]['record']))
        self.record.update(label='real', resource_accounting='required', routing_accounting='required')
        self.record['goal'].update(status='succeeded', known_failure=False)
        self.record['goal']['assessment'].update(verdict='succeeded')
        for row in self.record['evidence'].values(): row['kind'] = 'host'
        for key in ('route-ev', 'receipt-ev'):
            self.record['evidence'][key] = {'ref': 'fixture://' + key, 'sha256': None, 'kind': 'host'}
        self.record['evidence']['assessment'].update(kind='independent', file='acceptance.json', sha256=digest(self.run_root / 'acceptance.json'))
        for task in self.record['tasks']:
            task['routing_decision'] = ordinary_routing()
            task['resource_preflight'] = dict(host='fixture', cpu='1', ram='small', disk='small', evidence='result')
            task['resources'] = []
        self.record['artifact_retention'] = dict(run_id='goal-1', manifest_sha256=digest(self.run_root / rc.MANIFEST), consumers=[], quiescent=True)
        save(self.run_root / 'record.json', self.record)
        self.request_path = self.root / 'storage-request.json'
        self.request = dict(schema='company-native-storage-request/v1',
            roots=[dict(path=str(self.run_root), kind='company-run', run_id='goal-1', owner='B')],
            sejong_home=str(self.home), record='record.json', expect_manifest_sha256=digest(self.run_root / rc.MANIFEST))
        save(self.request_path, self.request)

    def retention(self, command, *extra):
        args = [command, '--run', str(self.run_root), '--sejong-home', str(self.home), *extra]
        if command != 'init': args += ['--expect-manifest-sha256', digest(self.run_root / self.rc.MANIFEST)]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.rc.main(args), 0)

    def plan(self, expected=0):
        return self.cli('storage', 'plan', '--request', self.request_path, expected=expected)

    def test_s01_s02_readonly_inventory_and_plan(self):
        before = tree(self.run_root)
        result = self.cli('storage', 'report', '--request', self.request_path)
        self.assertEqual(result['schema'], 'company-native-storage/v1')
        self.assertEqual(result['roots'][0]['breakdown']['declared_disposable']['bytes'], len(b'disposable only'))
        prepared = self.plan()
        self.assertFalse(prepared['apply_authorized'])
        self.assertTrue(prepared['ready'])
        self.assertEqual(before, tree(self.run_root))
        self.assertNotIn(self.rc.RECEIPT, before)

    def test_s03_s04_apply_existing_complete_and_readback(self):
        prepared = self.plan()
        path = save(self.root / 'plan.json', prepared)
        result = self.cli('storage', 'apply', '--plan', path, '--expect-plan-sha256', digest(path))
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['receipt']['status'], 'completed')
        self.assertFalse((self.run_root / 'scratch/raw').exists())
        self.assertEqual(json.loads((self.run_root / self.rc.RECEIPT).read_bytes()), result['receipt'])
        self.assertEqual((self.run_root / 'report.md').read_text(), 'retained evidence')

    def test_s05_wrong_hash_and_stale_target_record_manifest(self):
        path = save(self.root / 'plan.json', self.plan())
        self.cli('storage', 'apply', '--plan', path, '--expect-plan-sha256', '0' * 64, expected=1)
        for name in ('scratch/raw', 'record.json', self.rc.MANIFEST):
            with self.subTest(name=name):
                target = self.run_root / name
                raw = target.read_bytes()
                target.write_bytes(raw + b' ')
                self.cli('storage', 'apply', '--plan', path, '--expect-plan-sha256', digest(path), expected=1)
                target.write_bytes(raw)
        self.assertTrue((self.run_root / 'scratch/raw').exists())
        self.assertFalse((self.run_root / self.rc.RECEIPT).exists())

    def test_s06_symlink_hardlink_pins_and_current_run_block(self):
        raw = self.run_root / 'scratch/raw'
        raw.unlink(); raw.symlink_to(self.run_root / 'report.md')
        self.plan(expected=1)
        raw.unlink(); os.link(self.run_root / 'report.md', raw)
        self.plan(expected=1)
        raw.unlink(); raw.write_text('changed disposable')
        self.plan(expected=1)
        (self.run_root / '.pin').write_text('live')
        self.plan(expected=1)
        self.assertTrue(raw.exists())

    def test_s06_live_unaccepted_owner_and_evidence_block(self):
        self.record['goal']['status'] = 'active'
        save(self.run_root / 'record.json', self.record)
        self.plan(expected=1)
        self.request['roots'][0]['owner'] = 'other'
        save(self.request_path, self.request)
        self.plan(expected=1)

    def test_s06_unregistered_files_preserved_not_candidates(self):
        (self.run_root / 'not-registered').write_text('unknown')
        result = self.cli('storage', 'report', '--request', self.request_path)
        self.assertGreater(result['roots'][0]['breakdown']['unknown']['files'], 0)
        plan = self.plan()
        self.assertEqual([x['path'] for x in plan['disposable']], ['scratch/raw'])

    def test_s06_git_worktree_source_dirty_and_untracked_protected(self):
        subprocess.run(['git', 'init', '-q', str(self.run_root)], check=True, env=self.env, capture_output=True)
        self.plan(expected=1)
        self.assertTrue((self.run_root / 'scratch/raw').exists())

    def test_s06_shared_writable_namespace_and_target_block(self):
        target = self.run_root / 'scratch/raw'
        target.chmod(0o666)
        self.plan(expected=1)
        target.chmod(0o644)
        (self.run_root / 'scratch').chmod(0o777)
        self.plan(expected=1)
        (self.run_root / 'scratch').chmod(0o755)
        self.home.chmod(0o777)
        self.plan(expected=1)
        self.assertTrue(target.exists())

    def test_s06_open_activity_and_missing_probe_block(self):
        import native_storage
        with patch('run_completion.probe_activity', side_effect=FileNotFoundError('no lsof')):
            result = native_storage.plan(self.request_path)
        self.assertFalse(result['ready'])
        with (self.run_root / 'scratch/raw').open('rb'):
            self.plan(expected=1)

    def test_s06_evidence_never_disposable(self):
        self.record['evidence']['raw'] = {'ref': 'fixture://raw', 'file': 'scratch/raw',
                                         'sha256': digest(self.run_root / 'scratch/raw'), 'kind': 'host'}
        save(self.run_root / 'record.json', self.record)
        result = self.plan(expected=1)
        self.assertTrue(any('protected' in error for error in result['blockers']))

    def test_s05_root_replaced_same_name_blocks_original_plan(self):
        prepared = self.plan()
        path = save(self.root / 'plan.json', prepared)
        moved = self.run_root.with_name('moved-owned-fixture')
        self.run_root.rename(moved)
        self.run_root.mkdir()
        self.cli('storage', 'apply', '--plan', path, '--expect-plan-sha256', digest(path), expected=1)
        self.assertTrue((moved / 'scratch/raw').exists())

    def test_s02_unreadable_or_outside_root_is_unknown_not_zero(self):
        self.request['roots'][0]['path'] = str(self.root / 'missing')
        save(self.request_path, self.request)
        result = self.cli('storage', 'report', '--request', self.request_path)
        self.assertEqual(result['coverage'], 'unknown')
        self.assertIsNone(result['roots'][0]['bytes'])
        self.assertIsNone(result['roots'][0]['breakdown']['unknown']['bytes'])

    def test_root_escape_and_unregistered_manifest_block(self):
        self.request['roots'][0]['path'] = str(self.root)
        save(self.request_path, self.request)
        self.plan(expected=1)
        self.request['roots'][0]['path'] = str(self.run_root)
        save(self.request_path, self.request)
        (self.run_root / self.rc.MANIFEST).unlink()
        self.plan(expected=1)


class ReasoningTests(NativeCase):
    def setUp(self):
        super().setUp()
        import company_config
        import semantic_settings
        from catalog_test_support import launch_fixture, semantic_database
        self.fixture = self.enterContext(launch_fixture(company_config.resolve))
        self.inventory = self.fixture.inventory
        self.sqlite = self.enterContext(semantic_database(self.inventory.root))
        self.inventory.packet['binding']['host_catalog']['observed_files'] = semantic_settings.prepare(
            self.sqlite.database, self.fixture.catalog.worktree)
        self.fixture.write_packet()
        self.record_path = self.inventory.root / 'record.json'
        record = json.loads(self.record_path.read_bytes()); record['label'] = 'real'
        for row in record['evidence'].values(): row['kind'] = 'host'
        save(self.record_path, record)
        self.spec = self.inventory.root / 'spec.txt'; self.spec.write_bytes(b'bounded test')
        self.bundle = self.inventory.root / 'native-bundle'
        self.request_path = self.inventory.root / 'native-request.json'
        from storage_test_support import enrollment_path
        import routing_prepare, native_reasoning
        self.request = dict(schema='company-native-reasoning-request/v2', enrollment=pin(enrollment_path(self.inventory.root)),
            output_files=[*routing_prepare.FILES, 'manifest.json', native_reasoning.SIDECAR], depth='deep',
            effort=self.inventory.packet['selected']['effort'], record=pin(self.record_path),
            decision=pin(self.inventory.decision), spec_file=pin(self.spec), worktree=self.fixture.catalog.worktree)
        self.env.update(HOME=str(self.sqlite.home), CODEX_HOME=str(self.inventory.root),
                        AGENT_COMPANY_CONFIG=str(self.inventory.root / 'user.md'))

    def prepare(self, expected=0):
        save(self.request_path, self.request)
        return self.cli('reasoning', 'prepare', '--request', self.request_path, '--output', self.bundle, expected=expected)

    def launch(self, extra=()):
        import routing_launch
        args = self.inventory.args.copy()
        args[args.index('--decision') + 1] = str(self.bundle / 'decision.json')
        args += ['--prepared-bundle', str(self.bundle)]
        args[args.index('--spec') + 1] = (self.bundle / 'spec.txt').read_text()
        self.inventory.args = [*args, *extra]
        code, output = self.fixture.invoke(routing_launch.main)
        if destination := os.environ.get('NATIVE_OPS_RECEIPTS'):
            with Path(destination).open('a') as stream:
                stream.write(json.dumps({'argv': [str(Path(routing_launch.__file__)), *self.inventory.args],
                    'transport': 'unchanged routing_launch.main with counted fake host I/O only',
                    'exit': code, 'stdout': output, 'starts': self.fixture.starts,
                    'catalog_refreshes': self.fixture.refreshes}) + '\n')
        return code, output

    def test_r01_r02_actual_bundle_checked_launch_fake_host(self):
        result = self.prepare()
        self.assertEqual(result['requested']['depth'], 'deep')
        self.assertEqual(result['approved']['effort'], self.request['effort'])
        self.assertEqual(result['effective'], dict(model=None, effort=None, status='not_launched'))
        self.cli('reasoning', 'check', '--bundle', self.bundle)
        code, output = self.launch()
        self.assertEqual((code, self.fixture.starts, self.fixture.refreshes), (0, 1, 1), output)
        self.assertEqual(digest(self.bundle / 'spec.txt'), self.request['spec_file']['sha256'])
        self.assertEqual(json.loads((self.bundle / 'decision.json').read_bytes())['selected'], self.inventory.packet['selected'])

    def test_r01_ultrathink_alias_no_magic_effort_change(self):
        self.request['depth'] = 'ultrathink'
        result = self.prepare()
        self.assertEqual(result['requested']['depth'], 'deep')
        self.assertEqual(result['approved']['effort'], 'low')

    def test_r03_mismatched_effort_blocked_no_output_or_host(self):
        self.request['effort'] = 'universal-xhigh'
        self.prepare(expected=1)
        self.assertFalse(self.bundle.exists())
        self.assertEqual((self.fixture.starts, self.fixture.refreshes), (0, 0))

    def test_r03_paid_service_cap_and_auth_denials(self):
        original = copy.deepcopy(self.inventory.packet)
        for field, value in (('billing', 'paid_api'), ('authenticated', None), ('supported', False), ('effort', 'xhigh')):
            with self.subTest(field=field):
                self.inventory.packet = copy.deepcopy(original)
                self.inventory.packet['price_selection']['candidates'][0][field] = value
                self.fixture.write_packet(); self.request['decision'] = pin(self.inventory.decision)
                self.bundle = self.inventory.root / ('denied-' + field)
                self.prepare(expected=1)
                self.assertEqual((self.fixture.starts, self.fixture.refreshes), (0, 0))

    def test_r03_selected_service_and_excluded_model_deny(self):
        import company_config
        config = self.inventory.root / 'user.md'
        for label, settings in (('service', 'services: ["antigravity"]'),
                                ('model', 'services: ["codex"]\nexcluded_models: ["gpt-6.1-terra"]')):
            config.write_text('---\nschema_version: 1\npreset: single\napi_paid: false\n' + settings + '\n---\n')
            self.inventory.packet['binding']['host_catalog']['configuration_sha256'] = company_config.resolve()['configuration_sha256']
            self.fixture.write_packet(); self.request['decision'] = pin(self.inventory.decision)
            self.bundle = self.inventory.root / ('config-denied-' + label)
            result = self.prepare(expected=1)
            self.assertTrue(result['blockers'])
            self.assertEqual((self.fixture.starts, self.fixture.refreshes), (0, 0))

    def test_r03_next_launcher_effort_cap_and_spend_guards_zero_host(self):
        self.prepare()
        selected = self.inventory.packet['selected']
        resource = {'service': 'codex', 'approval_ref': 'fixture-approval', 'auth': 'authenticated',
            'hosts': ['fixture-host'], 'models': [selected['model']], 'efforts': ['high'], 'tools': ['read'],
            'billing': 'subscription', 'quota': 'available', 'spending_ceiling': 0,
            'observed_at': '2020-01-01T00:00:00Z', 'valid_until': '2100-01-01T00:00:00Z'}
        manifest = save(self.inventory.root / 'resource.json', {'format': 'company-resource-manifest/v1', 'resources': [resource]})
        flags = ['--require-resource-manifest', '--resource-manifest', str(manifest),
                 '--declared-host', 'fixture-host', '--declared-tool', 'read',
                 '--declared-billing', 'subscription', '--declared-spend', '0']
        code, output = self.launch(flags)
        self.assertEqual((code, self.fixture.starts, self.fixture.refreshes), (1, 0, 0), output)
        self.assertIn('efforts mismatch', output)
        self.assertEqual(json.loads((self.inventory.root / 'result.json').read_bytes())['launch_state'], 'not_started')
        resource.update(efforts=[selected['effort']], billing='paid_api')
        save(manifest, {'format': 'company-resource-manifest/v1', 'resources': [resource]})
        spend_flags = flags.copy()
        spend_flags[spend_flags.index('--declared-billing') + 1] = 'paid_api'
        spend_flags[spend_flags.index('--declared-spend') + 1] = '1'
        code, output = self.launch(spend_flags)
        self.assertEqual((code, self.fixture.starts, self.fixture.refreshes), (1, 0, 0), output)
        self.assertIn('paid spending authorization missing or exceeded', output)

    def test_r03_next_launcher_unknown_result_no_retry_zero_host(self):
        self.prepare()
        saved = self.inventory.root / 'result.json'
        save(saved, {'launch_state_version': 1, 'launch_state': 'unknown'})
        before = saved.read_bytes()
        code, output = self.launch()
        self.assertEqual((code, self.fixture.starts, self.fixture.refreshes), (1, 0, 0), output)
        self.assertEqual(saved.read_bytes(), before)

    def test_r03_provider_selection_preserved_without_codex_fallback(self):
        self.inventory.packet['selected']['route'] = 'agy'
        self.fixture.write_packet(); self.request['decision'] = pin(self.inventory.decision)
        result = self.prepare(expected=1)
        self.assertEqual(result['approved']['route'], 'agy')
        self.assertEqual(result['blockers'][0]['code'], 'checked_launch_bridge_unavailable')
        self.assertFalse(self.bundle.exists())

    def test_r04_bundle_and_original_input_drift_block(self):
        self.prepare()
        self.spec.write_bytes(b'changed spec')
        self.cli('reasoning', 'check', '--bundle', self.bundle, expected=1)
        self.assertEqual((self.fixture.starts, self.fixture.refreshes), (0, 0))

    def test_r04_stale_request_pin_invalid_no_bundle(self):
        self.request['decision']['sha256'] = '0' * 64
        self.prepare(expected=2)
        self.assertFalse(self.bundle.exists())

    def dual_requests(self):
        # Both decisions use the same unchanged, explicitly dual-effort catalog.
        for model in self.fixture.catalog.response['result']['models']:
            model['efforts'] = [{'value': 'low'}, {'value': 'high'}]
        self.fixture.catalog.save()
        self.inventory.packet['evidence']['inventory']['sha256'] = self.fixture.catalog.digest
        for model in self.inventory.packet['evidence']['inventory']['host_models']:
            model['supported_reasoning_levels'] = [{'effort': 'low'}, {'effort': 'high'}]
        # An explicitly configured fixture table authorizes independent easy/low
        # and hard/high profile preparation without fabricating a user pin.
        import company_config
        from record_check import make_profile_binding
        table = json.loads((PACKAGE / 'assets/worker-routing-table.json').read_text())
        hard = next(row for row in table['entries'] if row['family'] == 'general' and row['difficulty'] == 'hard')
        easy = next(row for row in table['entries'] if row['family'] == 'general' and row['difficulty'] == 'easy')
        terra = copy.deepcopy(next(c for c in easy['candidates'] if c['identity']['model'] == 'gpt-6.1-terra'))
        terra['identity']['effort'] = 'high'
        terra['priority'] = 0
        hard['candidates'] = [terra]
        table_path = save(self.inventory.root / 'dual-table.json', table)
        task_config = self.inventory.root / 'dual-task.md'
        task_config.write_text('---\nschema_version: 1\nworker_table: "' + str(table_path) + '#sha256=' + digest(table_path) + '"\n---\n')
        self.enterContext(patch.dict(os.environ, {'AGENT_COMPANY_TASK_CONFIG': str(task_config)}))
        self.env['AGENT_COMPANY_TASK_CONFIG'] = str(task_config)
        self.inventory.packet['binding']['host_catalog']['configuration_sha256'] = company_config.resolve()['configuration_sha256']
        profile = copy.deepcopy(self.inventory.packet['profile_binding']['profile'])
        unit = self.inventory.packet['binding']['task']
        self.inventory.packet['profile_binding'] = make_profile_binding(profile, table, unit)
        self.fixture.write_packet()
        self.request['decision'] = pin(self.inventory.decision)
        def highify(value):
            if isinstance(value, dict):
                return {key: ('high' if key == 'effort' and item == 'low' else highify(item))
                        for key, item in value.items()}
            if isinstance(value, list): return [highify(item) for item in value]
            return value
        # Rebuild the high profile from its source, not by rewriting a signed
        # profile snapshot or its table recursively.
        without_profile = {key: value for key, value in self.inventory.packet.items() if key != 'profile_binding'}
        high = highify(without_profile)
        high_profile = copy.deepcopy(profile)
        high_profile['units'][0]['profile']['difficulty'] = 'hard'
        high['profile_binding'] = make_profile_binding(high_profile, table, unit)
        decision = save(self.inventory.root / 'approved-high.json', high)
        request = copy.deepcopy(self.request)
        request.update(effort='high', decision=pin(decision))
        return save(self.inventory.root / 'request-high.json', request), self.inventory.root / 'bundle-high'

    def assert_binding_rejected(self, bundle):
        import native_reasoning
        before = tree(bundle)
        result = self.cli('reasoning', 'check', '--bundle', bundle, expected=1)
        self.assertEqual(result['status'], 'blocked')
        self.assertIsNone(result['next_checked_launch'])
        self.assertFalse(result['launch_authorized'])
        # A refusal must not launch, consult a host/provider, or repair the bundle.
        with patch('subprocess.run', side_effect=AssertionError('host/provider I/O on rejection')):
            direct = native_reasoning.check(bundle)
        self.assertEqual(direct['status'], 'blocked')
        self.assertIsNone(direct['next_checked_launch'])
        self.assertEqual(before, tree(bundle))
        self.assertEqual((self.fixture.starts, self.fixture.refreshes), (0, 0))

    def test_r06_valid_low_and_separately_approved_high_exact_next_launch(self):
        high_request, high_bundle = self.dual_requests()
        low = self.prepare()
        high = self.cli('reasoning', 'prepare', '--request', high_request, '--output', high_bundle)
        for bundle, effort, prepared in ((self.bundle, 'low', low), (high_bundle, 'high', high)):
            checked = self.cli('reasoning', 'check', '--bundle', bundle)
            self.assertEqual(checked['next_checked_launch'], prepared['next_checked_launch'])
            self.assertEqual(checked['requested']['effort'], effort)
            self.assertEqual(checked['approved']['effort'], effort)
            self.assertEqual(checked['effective']['status'], 'not_launched')
            for key, name in (('record', 'record.json'), ('decision', 'decision.json'), ('spec_file', 'spec.txt')):
                expected = self.record_path if key == 'record' else bundle / name
                self.assertEqual(checked['next_checked_launch'][key], str(expected))
            self.assertEqual(checked['next_checked_launch']['enrollment'], self.request['enrollment'])
        # Existing low checked-launch regression is retained; exercise high too.
        self.bundle = high_bundle
        self.inventory.fake.stdout = json.dumps({'ok': True, 'result': {'taskId': 'fake-task',
            'dispatchId': 'fake-dispatch', 'launch': {'effective': {
                'agent': 'codex', 'model': high['approved']['model'], 'effort': 'high'}}}})
        code, output = self.launch()
        self.assertEqual((code, self.fixture.starts, self.fixture.refreshes), (0, 1, 1), output)
        self.assertEqual(json.loads((high_bundle / 'decision.json').read_bytes())['selected']['effort'], 'high')

    def test_r06_low_sidecar_on_independently_valid_high_bundle_rejected(self):
        high_request, high_bundle = self.dual_requests()
        self.prepare()
        self.cli('reasoning', 'prepare', '--request', high_request, '--output', high_bundle)
        self.cli('reasoning', 'check', '--bundle', high_bundle)
        (high_bundle / 'native-reasoning.json').write_bytes((self.bundle / 'native-reasoning.json').read_bytes())
        self.assert_binding_rejected(high_bundle)
        sidecar_path = high_bundle / 'native-reasoning.json'
        sidecar = json.loads(sidecar_path.read_bytes())
        sidecar['bundle'].update(path=str(high_bundle), manifest_sha256=digest(high_bundle / 'manifest.json'))
        save(sidecar_path, sidecar)
        self.assert_binding_rejected(high_bundle)

    def test_r06_same_effort_distinct_bundle_sidecar_cannot_move_or_rebind(self):
        self.prepare()
        other = self.inventory.root / 'other-low-bundle'
        self.cli('reasoning', 'prepare', '--request', self.request_path, '--output', other)
        (other / 'native-reasoning.json').write_bytes((self.bundle / 'native-reasoning.json').read_bytes())
        self.assert_binding_rejected(other)

    def test_r06_original_record_decision_spec_identity_not_just_equal_bytes(self):
        self.prepare()
        original_sidecar = json.loads((self.bundle / 'native-reasoning.json').read_bytes())
        for key in ('record', 'decision', 'spec_file'):
            with self.subTest(key=key):
                alias = self.inventory.root / ('alias-' + key)
                source = {'record': self.record_path, 'decision': self.inventory.decision, 'spec_file': self.spec}[key]
                alias.write_bytes(source.read_bytes())
                request = copy.deepcopy(self.request); request[key] = pin(alias)
                request_path = save(self.inventory.root / ('request-' + key + '.json'), request)
                other = self.inventory.root / ('bundle-' + key)
                self.cli('reasoning', 'prepare', '--request', request_path, '--output', other)
                sidecar = copy.deepcopy(original_sidecar)
                # Even a substituted outer root/manifest pin cannot conceal a
                # distinct original file identity from native cross-validation.
                sidecar['bundle'].update(path=str(other), manifest_sha256=digest(other / 'manifest.json'))
                save(other / 'native-reasoning.json', sidecar)
                self.assert_binding_rejected(other)

    def test_r06_request_identity_replacement_cannot_silently_rebind(self):
        self.prepare()
        alias = self.inventory.root / 'identical-request.json'
        alias.write_bytes(self.request_path.read_bytes())
        sidecar_path = self.bundle / 'native-reasoning.json'
        sidecar = json.loads(sidecar_path.read_bytes()); sidecar['request'] = pin(alias)
        save(sidecar_path, sidecar)
        self.assert_binding_rejected(self.bundle)

    def test_r06_manifest_worktree_and_replaced_manifest_rejected(self):
        self.prepare()
        path = self.bundle / 'manifest.json'; raw = path.read_bytes()
        for change in ('worktree', 'replacement'):
            with self.subTest(change=change):
                manifest = json.loads(raw)
                if change == 'worktree': manifest['worktree'] = 'id:other-repo::/different/workspace'
                else: manifest['replacement'] = True
                save(path, manifest)
                self.assert_binding_rejected(self.bundle)
                path.write_bytes(raw)

    def test_r06_prepared_bytes_pair_and_binding_even_with_refreshed_artifact_pins(self):
        self.prepare()
        manifest_path = self.bundle / 'manifest.json'
        sidecar_path = self.bundle / 'native-reasoning.json'
        manifest_raw, sidecar_raw = manifest_path.read_bytes(), sidecar_path.read_bytes()
        for change, name in (('record', 'record.json'), ('selected', 'decision.json'),
                             ('binding', 'decision.json'), ('spec', 'spec.txt'),
                             ('original', 'original-record.json')):
            with self.subTest(change=change):
                target = self.bundle / name; raw = target.read_bytes()
                if change == 'spec': target.write_bytes(b'different exact spec')
                else:
                    document = json.loads(raw)
                    if change == 'selected': document['selected']['effort'] = 'high'
                    elif change == 'binding': document['binding']['revision'] = 'other-revision'
                    else: document['goal']['scope'] = 'other-scope'
                    save(target, document)
                manifest = json.loads(manifest_raw); manifest['artifacts'][name] = digest(target)
                save(manifest_path, manifest)
                sidecar = json.loads(sidecar_raw); sidecar['bundle']['manifest_sha256'] = digest(manifest_path)
                save(sidecar_path, sidecar)
                self.assert_binding_rejected(self.bundle)
                target.write_bytes(raw); manifest_path.write_bytes(manifest_raw); sidecar_path.write_bytes(sidecar_raw)

    def test_r06_stale_request_sources_and_sidecar_rejected_without_rewrite(self):
        self.prepare()
        targets = [self.request_path, self.record_path, self.inventory.decision, self.spec,
                   self.bundle / 'native-reasoning.json']
        for target in targets:
            with self.subTest(target=target.name):
                raw = target.read_bytes()
                if target.name == 'native-reasoning.json':
                    sidecar = json.loads(raw); sidecar['approved']['model'] = 'replaced-model'
                    save(target, sidecar)
                else: target.write_bytes(raw + b' ')
                self.assert_binding_rejected(self.bundle)
                target.write_bytes(raw)

    def test_r06_old_unbound_sidecar_requires_explicit_new_preparation(self):
        self.prepare()
        path = self.bundle / 'native-reasoning.json'
        sidecar = json.loads(path.read_bytes()); sidecar.pop('bundle'); save(path, sidecar)
        self.assert_binding_rejected(self.bundle)

    def test_r06_preparation_source_replaced_before_router_never_returns_prepared(self):
        import native_reasoning, routing_prepare
        save(self.request_path, self.request)
        original = routing_prepare.prepare
        def replace(args):
            # A replaced valid original record used to be prepared with the old
            # native request still pinned; preparation must now fail itself.
            self.record_path.write_bytes(self.record_path.read_bytes() + b' ')
            return original(args)
        with patch('routing_prepare.prepare', side_effect=replace):
            result = native_reasoning.prepare(self.request_path, self.bundle)
        self.assertEqual(result['status'], 'blocked')
        self.assertIsNone(result['next_checked_launch'])
        self.assertEqual((self.fixture.starts, self.fixture.refreshes), (0, 0))

    def test_r06_sidecar_replaced_during_router_check_rejected(self):
        import native_reasoning, routing_prepare
        self.prepare()
        original = routing_prepare.check_bundle
        def replace(root):
            result = original(root)
            path = root / 'native-reasoning.json'; path.write_bytes(path.read_bytes() + b' ')
            return result
        with patch('routing_prepare.check_bundle', side_effect=replace):
            result = native_reasoning.check(self.bundle)
        self.assertEqual(result['status'], 'blocked')
        self.assertIsNone(result['next_checked_launch'])
        self.assertEqual((self.fixture.starts, self.fixture.refreshes), (0, 0))

    def test_r05_no_current_turn_or_global_config_write(self):
        originals = [self.record_path, self.inventory.decision, self.spec, self.inventory.root / 'user.md']
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in originals}
        self.prepare()
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in originals})
        self.assertEqual((self.fixture.starts, self.fixture.refreshes), (0, 0))


class BoundaryTests(NativeCase):
    def test_bad_cli_is_single_json_not_traceback(self):
        self.cli('reasoning', 'launch', expected=2)
        self.cli('storage', 'plan', expected=2)

    def test_modules_have_no_claude_or_network_dependency(self):
        import ast
        names = set()
        for name in ('native_operations', 'native_storage', 'native_usage', 'native_reasoning'):
            module = __import__(name)
            self.assertEqual(Path(module.__file__).parent, CLI.parent)
            parsed = ast.parse(Path(module.__file__).read_text())
            for node in ast.walk(parsed):
                if isinstance(node, ast.Import): names.update(x.name for x in node.names)
                if isinstance(node, ast.ImportFrom): names.add(node.module)
        self.assertFalse({'requests', 'urllib', 'httpx', 'anthropic', 'claude', 'routing_launch'} & names)


if __name__ == '__main__':
    unittest.main()
