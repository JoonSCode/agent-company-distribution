"""Actual prepare/check CLI → existing checker → counted fake host only."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import unittest
from unittest.mock import patch

import company_config
import routing_launch
import routing_prepare
import semantic_settings
from catalog_test_support import launch_fixture, semantic_database
from storage_test_support import flags as enrollment_flags

PACKAGE = Path(__file__).resolve().parents[1]
CLI = PACKAGE / 'scripts/routing_prepare.py'
CHECKER = PACKAGE / 'scripts/record_check.py'


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.fixture = self.enterContext(launch_fixture(company_config.resolve))
        self.inventory = self.fixture.inventory
        self.sqlite = self.enterContext(semantic_database(self.inventory.root))
        self.inventory.packet['binding']['host_catalog']['observed_files'] = semantic_settings.prepare(
            self.sqlite.database, self.fixture.catalog.worktree)
        self.fixture.write_packet()
        self.record = self.inventory.root / 'record.json'
        record = json.loads(self.record.read_bytes())
        record['label'] = 'real'
        for row in record['evidence'].values():
            row['kind'] = 'host'
        self.record.write_text(json.dumps(record))
        self.spec = self.inventory.root / 'spec.txt'
        self.spec.write_bytes(b'bounded test')
        self.bundle = self.inventory.root / 'bundle'
        # Fresh child env, with no ambient provider/remote settings. Existing fake
        # fixture HOME is made explicit so real CLI semantic observation agrees.
        self.env = {key: os.environ[key] for key in ('PATH', 'TMPDIR') if key in os.environ}
        self.env.update(HOME=str(self.sqlite.home), CODEX_HOME=str(self.inventory.root),
                        AGENT_COMPANY_CONFIG=str(self.inventory.root / 'user.md'),
                        PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
                        UV_OFFLINE='1', UV_PYTHON_DOWNLOADS='never')

    def command(self, output=None):
        return [sys.executable, '-B', str(CLI), 'prepare', '--record', str(self.record),
                '--decision', str(self.inventory.decision), '--spec-file', str(self.spec),
                '--worktree', self.fixture.catalog.worktree, '--output', str(output or self.bundle), *enrollment_flags(self.inventory.root)]

    def run_cli(self, args=None, expected=0):
        process = subprocess.run(args or self.command(), env=self.env, capture_output=True,
                                 text=True, timeout=30, cwd=self.inventory.root)
        self.assertEqual(process.returncode, expected, process.stdout + process.stderr)
        self.assertNotIn('Traceback', process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result['ok'], expected == 0)
        self.assertFalse(result['launch_authorized'])
        return result

    def check(self, expected=0):
        return self.run_cli([sys.executable, '-B', str(CLI), 'check', str(self.bundle)], expected)

    def old_check(self, record, decision):
        process = subprocess.run([sys.executable, '-B', str(CHECKER), 'routing-check',
                                  str(decision), '--record', str(record), '--json'],
                                 env=self.env, cwd=self.inventory.root,
                                 capture_output=True, text=True, timeout=30)
        return process.returncode, json.loads(process.stdout)

    def launch_bundle(self):
        args = self.inventory.args.copy()
        args[args.index('--decision') + 1] = str(self.bundle / 'decision.json')
        args += ['--prepared-bundle', str(self.bundle)]
        original = self.inventory.args
        self.inventory.args = args
        try:
            return self.fixture.invoke(routing_launch.main)
        finally:
            self.inventory.args = original

    def tree(self):
        return {str(p.relative_to(self.bundle)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.bundle.rglob('*') if p.is_file()}

    def test_actual_cli_old_checker_and_fake_launch_same_input(self):
        before = self.old_check(self.record, self.inventory.decision)
        self.assertEqual(before[0], 0, before)
        originals = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (self.record, self.inventory.decision, self.spec)}
        self.assertEqual(self.run_cli()['status'], 'prepared')
        after = self.old_check(self.bundle / 'record.json', self.bundle / 'decision.json')
        # Only serialized decision bytes can differ due to explicit path relocation.
        for result in (before[1], after[1]):
            result['receipt'].pop('decision_sha256')
            result['receipt'].pop('record_sha256')
        self.assertEqual(before, after)
        self.assertEqual(originals, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in originals})
        for path, name in ((self.record, 'original-record.json'), (self.inventory.decision, 'original-decision.json'), (self.spec, 'spec.txt')):
            self.assertEqual(path.read_bytes(), (self.bundle / name).read_bytes())
        self.assertEqual(json.loads((self.bundle / 'decision.json').read_bytes()), self.inventory.packet)
        self.assertEqual(json.loads((self.bundle / 'patch.json').read_bytes()), [])
        snapshot = self.tree()
        self.check()
        self.assertEqual(snapshot, self.tree())
        self.assertEqual(stat.S_IMODE(self.bundle.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in self.bundle.iterdir()))
        code, output = self.launch_bundle()
        self.assertEqual((code, self.fixture.starts, self.fixture.refreshes), (0, 1, 1), output)

    def test_relative_file_patch_does_not_create_authority(self):
        evidence = self.inventory.root / 'support.txt'
        evidence.write_text('supplied bounded support')
        self.inventory.packet['evidence']['quality'].update(file='support.txt', sha256=hashlib.sha256(evidence.read_bytes()).hexdigest())
        self.fixture.write_packet()
        self.run_cli()
        rows = json.loads((self.bundle / 'patch.json').read_bytes())
        self.assertEqual(rows, [{'target': 'decision.json', 'op': 'replace', 'path': '/evidence/quality/file', 'value': str(evidence)}])
        candidate = json.loads((self.bundle / 'decision.json').read_bytes())
        candidate['evidence']['quality']['file'] = 'support.txt'
        self.assertEqual(candidate, self.inventory.packet)
        self.assertEqual(self.old_check(self.bundle / 'record.json', self.bundle / 'decision.json')[0], 0)

    def test_source_record_decision_spec_config_and_catalog_drift(self):
        self.run_cli()
        paths = [self.record, self.inventory.decision, self.spec,
                 self.inventory.root / 'user.md', self.fixture.catalog.root / 'response-1.json',
                 self.bundle / 'decision.json']
        for path in paths:
            with self.subTest(path=path.name):
                raw = path.read_bytes()
                path.write_bytes(raw + b' ')
                self.check(expected=1)
                path.write_bytes(raw)
        # Source-only change is tested in a copied package, never this checkout.
        import shutil
        staged = self.inventory.root / 'source-copy'
        shutil.copytree(PACKAGE, staged)
        source_cli = staged / 'scripts/routing_prepare.py'
        output = self.inventory.root / 'source-bundle'
        args = self.command(output)
        args[2] = str(source_cli)
        self.run_cli(args)
        source = staged / 'scripts/route_select.py'
        source.write_bytes(source.read_bytes() + b'\n# drift\n')
        self.run_cli([sys.executable, '-B', str(source_cli), 'check', str(output)], expected=1)
        self.assertEqual((self.fixture.starts, self.fixture.refreshes), (0, 0))

    def test_missing_auth_paid_optin_tools_and_unavailable_host_deny_zero_start(self):
        original = copy.deepcopy(self.inventory.packet)
        for field, value in (('authenticated', None), ('tools', 'unknown'), ('billing', 'paid_api'), ('supported', False)):
            with self.subTest(field=field):
                self.inventory.packet = copy.deepcopy(original)
                self.inventory.packet['price_selection']['candidates'][0][field] = value
                self.fixture.write_packet()
                self.bundle = self.inventory.root / ('denied-' + field)
                result = self.run_cli(expected=1)
                self.assertTrue(result['missing_fields'])
                self.assertEqual(self.old_check(self.bundle / 'record.json', self.bundle / 'decision.json')[0], 1)
                code, output = self.launch_bundle()
                self.assertEqual((code, self.fixture.starts, self.fixture.refreshes), (1, 0, 0), output)

    def test_missing_and_changed_semantics_deny_zero_start(self):
        original = copy.deepcopy(self.inventory.packet)
        for missing in (True, False):
            with self.subTest(missing=missing):
                self.inventory.packet = copy.deepcopy(original)
                self.bundle = self.inventory.root / ('semantic-' + str(missing))
                if missing:
                    self.inventory.packet['binding']['host_catalog']['observed_files'] = []
                else:
                    self.sqlite.db.execute("UPDATE profile_state_documents SET payload=? WHERE domain='settings'", (json.dumps({**self.sqlite.value, 'provider': 'changed'}),))
                    self.sqlite.db.commit()
                self.fixture.write_packet()
                self.run_cli(expected=1)
                code, output = self.launch_bundle()
                self.assertEqual((code, self.fixture.starts, self.fixture.refreshes), (1, 0, 0), output)

    def test_legacy_byte_only_semantics_stay_manual(self):
        # Old/manual byte-only consumer remains compatible, but the new helper
        # does not pretend that it observed the active profile settings.
        self.inventory.packet['binding']['host_catalog']['observed_files'] = [
            {'role': role, 'path': str(self.fixture.observed),
             'sha256': hashlib.sha256(self.fixture.observed.read_bytes()).hexdigest()}
            for role in ('config', 'auth_policy')]
        self.fixture.write_packet()
        self.assertEqual(self.old_check(self.record, self.inventory.decision)[0], 0)
        result = self.run_cli(expected=1)
        self.assertIn('semantic_observation_required', [e['code'] for e in result['missing_fields']])
        self.assertEqual((self.fixture.starts, self.fixture.refreshes), (0, 0))

    def test_unavailable_catalog_denies(self):
        self.fixture.catalog.response['result']['models'] = []
        self.fixture.catalog.save()
        self.inventory.packet['evidence']['inventory']['sha256'] = self.fixture.catalog.digest
        self.fixture.write_packet()
        self.run_cli(expected=1)
        code, output = self.launch_bundle()
        self.assertEqual((code, self.fixture.starts, self.fixture.refreshes), (1, 0, 0), output)

    def test_spec_worktree_and_synthetic_incomplete_inputs_block(self):
        original = copy.deepcopy(self.inventory.packet)
        for name in ('spec', 'worktree', 'synthetic', 'empty'):
            with self.subTest(name=name):
                self.inventory.packet = copy.deepcopy(original)
                self.bundle = self.inventory.root / name
                if name == 'spec':
                    self.inventory.packet['binding']['spec_sha256'] = '0' * 64
                elif name == 'worktree':
                    self.inventory.packet['binding']['host_catalog']['worktree'] = 'other'
                elif name == 'synthetic':
                    self.inventory.packet['label'] = 'synthetic'
                else:
                    self.inventory.packet = {}
                self.fixture.write_packet()
                result = self.run_cli(expected=1)
                self.assertEqual(result['status'], 'blocked')
                self.assertTrue(result['missing_fields'])
                self.assertNotEqual(json.loads((self.bundle / 'manifest.json').read_bytes())['status'], 'prepared')
        self.assertEqual((self.fixture.starts, self.fixture.refreshes), (0, 0))

    def test_measurement_required_never_invents_preparation(self):
        original = json.loads(self.record.read_bytes())
        for version in (1, 2):
            self.bundle = self.inventory.root / ('measurement-' + str(version))
            self.record.write_text(json.dumps({**original, 'measurement': {'mode': 'required', 'version': version}}))
            result = self.run_cli(expected=1)
            self.assertIn('measurement_lifecycle_required', [e['code'] for e in result['missing_fields']])
        self.assertEqual((self.fixture.starts, self.fixture.refreshes), (0, 0))

    def test_collision_parallel_callers_and_partial_bundle_preserved(self):
        one = subprocess.Popen(self.command(), env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        two = subprocess.Popen(self.command(), env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        a, ae = one.communicate(timeout=30)
        b, be = two.communicate(timeout=30)
        self.assertEqual(sorted([one.returncode, two.returncode]), [0, 1], (a, ae, b, be))
        snapshot = self.tree()
        self.run_cli(expected=1)
        self.assertEqual(snapshot, self.tree())
        partial = self.inventory.root / 'partial'
        partial.mkdir()
        (partial / 'retained').write_text('earlier failure')
        self.run_cli(self.command(partial), expected=1)
        self.assertEqual((partial / 'retained').read_text(), 'earlier failure')
        self.assertEqual(list(partial.iterdir()), [partial / 'retained'])

    def test_malformed_and_missing_inputs_preserve_failed_reservation(self):
        for index, raw in enumerate((b'{', b'{"label":1,"label":2}', b'{"x":NaN}')):
            self.bundle = self.inventory.root / ('bad-' + str(index))
            self.inventory.decision.write_bytes(raw)
            self.run_cli(expected=1)
            self.assertTrue(self.bundle.is_dir())
            self.assertFalse((self.bundle / 'manifest.json').exists())
        self.inventory.decision.unlink()
        self.bundle = self.inventory.root / 'missing'
        self.run_cli(expected=1)
        self.assertTrue(self.bundle.exists())

    def test_no_host_launch_option_import_or_credential_copy(self):
        import ast
        tree = ast.parse(CLI.read_text())
        modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        modules += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        self.assertFalse({'subprocess', 'routing_launch', 'measurement_lifecycle'} & set(modules))
        process = subprocess.run([sys.executable, '-B', str(CLI), 'prepare', '--help'], env=self.env,
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0)
        self.assertNotIn('--launch', process.stdout)
        self.run_cli()
        self.assertEqual(set(p.name for p in self.bundle.iterdir()), {*routing_prepare.FILES, 'manifest.json'})
        # Nothing copies the profile DB, auth file or configuration contents.
        manifest = json.loads((self.bundle / 'manifest.json').read_bytes())
        self.assertNotIn(str(self.sqlite.database), manifest['inputs'])
        self.assertFalse(any('auth.json' in name for name in manifest['artifacts']))

    def test_permissions_symlink_and_tampered_snapshot_block(self):
        self.run_cli()
        (self.bundle / 'spec.txt').chmod(0o644)
        self.check(expected=1)
        (self.bundle / 'spec.txt').chmod(0o600)
        original = self.bundle / 'original-record.json'
        original.unlink()
        original.symlink_to(self.record)
        self.check(expected=1)
        other = self.inventory.root / 'alias'
        other.symlink_to(self.bundle, target_is_directory=True)
        self.run_cli(self.command(other), expected=1)


class PreviewTests(unittest.TestCase):
    """Real CLI/checker/storage readers; supplied host observations are synthetic."""

    def setUp(self):
        from record_check import make_profile_binding
        from storage_test_support import enrollment_path, pin
        self.pin = pin
        self.fixture = self.enterContext(launch_fixture(company_config.resolve))
        self.inventory = self.fixture.inventory
        self.root = self.inventory.root
        self.sqlite = self.enterContext(semantic_database(self.root))
        self.inventory.packet['binding']['host_catalog']['observed_files'] = semantic_settings.prepare(
            self.sqlite.database, self.fixture.catalog.worktree)
        self.record = self.root / 'record.json'
        record = json.loads(self.record.read_bytes())
        record['label'] = 'real'
        record['goal'].update(status='active', known_failure=False, assessment=None)
        for row in record['evidence'].values():
            row['kind'] = 'host'
        self.save(self.record, record)
        self.profile = copy.deepcopy(self.inventory.packet['profile_binding']['profile'])
        peer = copy.deepcopy(self.profile['units'][0]); peer['id'] = 'peer'
        child = copy.deepcopy(peer); child.update(id='child', depends_on=['new'])
        self.profile['units'] += [peer, child]
        self.profile_path = self.root / 'profile.json'
        self.save(self.profile_path, self.profile)
        self.request_path = self.root / 'preview.json'
        self.context_path = self.root / 'context.json'
        evidence = self.root / 'read-only-observation.txt'
        evidence.write_text('Synthetic current no-start, free-writer and capacity observations.\n')
        self.context = dict(schema='company-routing-preview-context/v1',
            binding=dict(run='goal-1', scope='approved-scope', revision='r1', owner='B',
                         worktree=self.fixture.catalog.worktree, record_sha256=self.pin(self.record)['sha256'],
                         profile_sha256=self.pin(self.profile_path)['sha256']),
            observed_at='2020-01-01T00:00:00Z', valid_until='2100-01-01T00:00:00Z',
            units={u['id']: dict(task=None, evidence='snapshot') for u in self.profile['units']},
            writers={k: dict(task=None, evidence='snapshot') for k in ('source-a', 'source-b')},
            capacity=dict(available=2, evidence='snapshot'),
            evidence={'snapshot': dict(ref='synthetic://supplied-host-assertion', kind='host',
                                     file=str(evidence), sha256=self.pin(evidence)['sha256'])})
        self.request = dict(schema='company-routing-preview-request/v1', record=self.pin(self.record),
            profile=self.pin(self.profile_path), enrollment=self.pin(enrollment_path(self.root)),
            context=None, worktree=self.fixture.catalog.worktree, units=[])
        for unit in self.profile['units']:
            name = unit['id']
            spec = self.root / (name + '-spec.txt'); spec.write_bytes('  한글 日本語 😀\n\n'.encode())
            decision = copy.deepcopy(self.inventory.packet)
            decision['binding'].update(task=name, attempt='planned:' + name, run='goal-1',
                                       spec_sha256=self.pin(spec)['sha256'])
            decision['profile_binding'] = make_profile_binding(self.profile,
                self.inventory.packet['profile_binding']['table'], name)
            path = self.root / (name + '-decision.json'); self.save(path, decision)
            self.request['units'].append(dict(id=name, decision=self.pin(path), spec_file=self.pin(spec),
                                              writers=['source-b' if name == 'peer' else 'source-a']))
        self.env = {key: os.environ[key] for key in ('PATH', 'TMPDIR') if key in os.environ}
        self.env.update(HOME=str(self.sqlite.home), CODEX_HOME=str(self.root),
                        AGENT_COMPANY_CONFIG=str(self.root / 'user.md'), PYTHONDONTWRITEBYTECODE='1',
                        PYTHONNOUSERSITE='1', PYTHONPYCACHEPREFIX=str(self.root / 'unused-cache'),
                        UV_OFFLINE='1', UV_PYTHON_DOWNLOADS='never')
        self.write_request()

    def save(self, path, value):
        path.write_bytes(routing_prepare.encoded(value))

    def write_request(self):
        self.save(self.context_path, self.context)
        self.request['context'] = self.pin(self.context_path)
        self.save(self.request_path, self.request)

    def run_preview(self, expected=1):
        process = subprocess.run([sys.executable, '-B', str(CLI), 'preview', '--request', str(self.request_path),
            '--expect-request-sha256', self.pin(self.request_path)['sha256']], env=self.env,
            cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, expected, process.stdout + process.stderr)
        self.assertNotIn('Traceback', process.stderr)
        result = json.loads(process.stdout)
        self.assertFalse(result['launch_authorized'])
        self.assertEqual((self.fixture.starts, self.fixture.refreshes), (0, 0))
        return result

    def update_decision(self, unit, mutate):
        row = next(r for r in self.request['units'] if r['id'] == unit)
        path = Path(row['decision']['path'])
        decision = json.loads(path.read_bytes()); mutate(decision); self.save(path, decision)
        row['decision'] = self.pin(path); self.write_request()

    def refresh_profile(self):
        from record_check import make_profile_binding
        self.save(self.profile_path, self.profile)
        self.request['profile'] = self.pin(self.profile_path)
        self.context['binding']['profile_sha256'] = self.pin(self.profile_path)['sha256']
        for row in self.request['units']:
            path = Path(row['decision']['path']); decision = json.loads(path.read_bytes())
            decision['binding'].update(task=row['id'], attempt='planned:' + row['id'])
            decision['profile_binding'] = make_profile_binding(self.profile,
                self.inventory.packet['profile_binding']['table'], row['id'])
            self.save(path, decision); row['decision'] = self.pin(path)
        self.write_request()

    def test_frozen_determinism_exact_unicode_lf_and_no_writes(self):
        # The existing SQLite read-only semantic checker takes native WAL read
        # locks in -shm; configuration DB/WAL and all originals must be unchanged.
        paths = [p for p in self.root.rglob('*') if p.is_file() and not p.name.endswith('-shm')]
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
        first = self.run_preview(); second = self.run_preview()
        self.assertEqual(first, second)
        self.assertEqual(first['ready'], ['new', 'peer'])
        self.assertEqual(first['format'], 'company-routing-preview/v1')
        self.assertTrue(first['read_only'])
        self.assertEqual([p for p in self.root.rglob('*') if p.is_file() and not p.name.endswith('-shm')], paths)
        self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in paths})
        for row in first['units']:
            spec = row['spec']; raw = Path(spec['path']).read_bytes()
            self.assertEqual(spec['text'].encode(), raw)
            self.assertEqual(spec['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(row['checked_inputs']['spec_file']['sha256'], spec['sha256'])
            self.assertEqual(row['decision']['binding']['spec_sha256'], spec['sha256'])
            self.assertEqual(row['decision'], json.loads(Path(row['checked_inputs']['decision']['path']).read_bytes()))
            self.assertTrue(row['routing_check']['ok'], row['routing_check'])
        # Physical original bytes, rather than a reconstructed string, reach the
        # existing prepare/check consumer. The launcher seam is left unchanged.
        row = first['units'][1]
        output = self.root / 'from-preview'
        command = [sys.executable, '-B', str(CLI), 'prepare', '--record', str(self.record),
                   '--decision', row['checked_inputs']['decision']['path'], '--spec-file', row['spec']['path'],
                   '--worktree', self.request['worktree'], '--output', str(output), *enrollment_flags(self.root)]
        result = subprocess.run(command, env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((output / 'spec.txt').read_bytes(), Path(row['spec']['path']).read_bytes())

    def test_reorder_inputs_is_not_a_scheduler_priority(self):
        first = self.run_preview()
        self.request['units'].reverse(); self.write_request()
        second = self.run_preview()
        self.assertEqual(first['units'], second['units'])
        self.assertEqual(first['ready'], second['ready'])

    def test_preview_and_manual_current_checker_match_valid_and_denied_inputs(self):
        for denied in (False, True):
            if denied:
                self.update_decision('new', lambda d: d['binding'].update(scope='stale-scope'))
            preview = self.run_preview()
            row = next(r for r in preview['units'] if r['unit_id'] == 'new')
            manual = subprocess.run([sys.executable, '-B', str(CHECKER), 'routing-check',
                row['checked_inputs']['decision']['path'], '--record', str(self.record), '--json'],
                env=self.env, capture_output=True, text=True, timeout=30)
            result = json.loads(manual.stdout)
            self.assertEqual(manual.returncode, 1 if denied else 0, manual.stdout + manual.stderr)
            self.assertEqual(result['ok'], row['routing_check']['ok'])
            self.assertEqual(result['errors'], row['routing_check']['errors'])
            for key in ('record_sha256', 'decision_sha256'):
                result['receipt'].pop(key)
            self.assertEqual(result['receipt'], row['routing_check']['receipt'])

    def test_all_ready_exit_zero_and_profile_checker_context_no_match(self):
        self.profile['units'][2]['depends_on'] = []
        self.request['units'][2]['writers'] = []
        self.context['capacity']['available'] = 3
        self.refresh_profile()
        self.assertEqual(self.run_preview(expected=0)['ready'], ['child', 'new', 'peer'])
        self.profile['units'][0]['profile']['context_requirement'] = 999999999
        self.save(self.profile_path, self.profile)
        self.request['profile'] = self.pin(self.profile_path)
        self.context['binding']['profile_sha256'] = self.pin(self.profile_path)['sha256']
        self.write_request()
        result = self.run_preview()
        self.assertEqual(result['ready'], [])
        self.assertIn('profile_dag_mismatch', [e['code'] for e in result['missing_fields']])

    def test_dependencies_need_current_success_review_and_correct_task_mapping(self):
        # A reviewed arbitrary mapping to an unrelated successful task is not
        # enough. Direct Task IDs are supported; remapped IDs need the existing
        # validated historical profile/launch evidence path.
        self.context['units']['new']['task'] = 'task-1'; self.write_request()
        result = self.run_preview()
        child = next(r for r in result['units'] if r['unit_id'] == 'child')
        self.assertFalse(child['dependencies'][0]['accepted'])
        self.profile['units'][0]['id'] = 'task-1'
        self.profile['units'][2]['depends_on'] = ['task-1']
        self.request['units'][0]['id'] = 'task-1'
        self.context['units']['task-1'] = self.context['units'].pop('new')
        self.refresh_profile()
        self.assertEqual(self.run_preview()['ready'], ['child', 'peer'])
        record = json.loads(self.record.read_bytes())
        original = copy.deepcopy(record)
        for case in ('failed', 'unknown', 'unreviewed', 'self_review', 'parent_pending'):
            with self.subTest(case=case):
                record = copy.deepcopy(original); task = record['tasks'][0]
                if case == 'failed': task['execution']['result']['outcome'] = 'failed'
                elif case == 'unknown': task['execution'].update(state='unknown', result=None)
                elif case == 'unreviewed': task['technical'] = None
                elif case == 'self_review': task['technical']['actor'] = task['execution']['actor']
                else: task['parent_integration']['verdict'] = 'pending'
                self.save(self.record, record)
                self.request['record'] = self.pin(self.record)
                self.context['binding']['record_sha256'] = self.pin(self.record)['sha256']
                self.write_request()
                self.assertNotIn('child', self.run_preview()['ready'])

    def test_changed_whitespace_crlf_lf_remains_exact_and_invalid_utf8_denies(self):
        row = self.request['units'][0]; spec = Path(row['spec_file']['path'])
        for raw in (b'space ', '한글\r\n\n'.encode(), b'no-final-lf', b'two-final-lfs\n\n'):
            spec.write_bytes(raw); row['spec_file'] = self.pin(spec)
            self.update_decision('new', lambda d: d['binding'].update(spec_sha256=self.pin(spec)['sha256']))
            result = self.run_preview()
            actual = next(r for r in result['units'] if r['unit_id'] == 'new')
            self.assertEqual(actual['status'], 'ready')
            self.assertEqual(actual['spec']['text'].encode(), raw)
        for raw in (b'\xff', b'bad\x00spec', b''):
            spec.write_bytes(raw); row['spec_file'] = self.pin(spec)
            self.update_decision('new', lambda d: d['binding'].update(spec_sha256=self.pin(spec)['sha256']))
            self.assertFalse(self.run_preview()['ok'])

    def test_mid_preview_input_drift_blocks_every_row(self):
        original = routing_prepare.checked
        changed = False
        def drift(*args):
            nonlocal changed
            result = original(*args)
            if not changed:
                changed = True
                path = Path(self.request['units'][2]['spec_file']['path'])
                path.write_bytes(path.read_bytes() + b' ')
            return result
        with patch('routing_prepare.checked', side_effect=drift):
            result = routing_prepare.preview(self.request_path, self.pin(self.request_path)['sha256'])
        self.assertEqual(result['ready'], [])
        self.assertIn('input_drift', [e['code'] for e in result['missing_fields']])

    def test_shared_writer_busy_unknown_missing_and_capacity(self):
        self.request['units'][1]['writers'] = ['source-a']; self.write_request()
        self.assertEqual(self.run_preview()['ready'], [])
        self.request['units'][1]['writers'] = ['source-b']
        for state in ('live-task', 'unknown', None):
            self.context['writers']['source-a']['task'] = state
            if state is None:
                del self.context['writers']['source-a']
            self.write_request()
            self.assertEqual(self.run_preview()['ready'], ['peer'])
        self.context['capacity']['available'] = 0; self.write_request()
        self.assertEqual(self.run_preview()['ready'], [])

    def test_existing_or_unknown_attempt_blocks_only_affected_unit(self):
        for task in ('host-task-already-started', 'unknown'):
            self.context['units']['new']['task'] = task; self.write_request()
            self.assertEqual(self.run_preview()['ready'], ['peer'])

    def test_missing_authority_context_requirement_and_profile_provenance(self):
        self.update_decision('new', lambda d: d['binding'].update(scope='unapproved-scope'))
        result = self.run_preview()
        self.assertEqual(result['ready'], ['peer'])
        self.assertTrue(next(r for r in result['units'] if r['unit_id'] == 'new')['missing_fields'])
        self.update_decision('peer', lambda d: d['profile_binding']['profile']['units'][0]['profile'].update(context_requirement=999999999))
        result = self.run_preview()
        self.assertEqual(result['ready'], [])
        self.assertIn('profile_dag_mismatch', [e['code'] for e in result['missing_fields']])

    def test_paid_non_codex_and_unaccepted_goal_never_ready(self):
        self.update_decision('new', lambda d: d['constraints'].update(billing='paid_api'))
        result = self.run_preview()
        self.assertEqual(result['ready'], ['peer'])
        self.assertIn('subscription_required', [e['code'] for e in result['missing_fields']])
        self.update_decision('peer', lambda d: d['selected'].update(route='antigravity'))
        result = self.run_preview()
        self.assertEqual(result['ready'], [])
        self.assertIn('local_codex_required', [e['code'] for e in result['missing_fields']])
        record = json.loads(self.record.read_bytes()); record['goal']['owner_acceptance'] = 'pending'
        self.save(self.record, record); self.request['record'] = self.pin(self.record)
        self.context['binding']['record_sha256'] = self.pin(self.record)['sha256']; self.write_request()
        self.assertFalse(self.run_preview()['ok'])

    def test_context_stale_missing_or_unpinned_provenance_denies(self):
        original = copy.deepcopy(self.context)
        changes = [lambda c: c['binding'].update(revision='stale'),
                   lambda c: c['binding'].update(record_sha256='0' * 64),
                   lambda c: c.update(valid_until='2021-01-01T00:00:00Z'),
                   lambda c: c.update(observed_at='2099-01-01T00:00:00Z'),
                   lambda c: c['units']['new'].update(evidence='absent'),
                   lambda c: c['evidence']['snapshot'].update(kind='synthetic'),
                   lambda c: c['evidence']['snapshot'].pop('file'),
                   lambda c: c['evidence']['snapshot'].update(sha256='0' * 64)]
        for change in changes:
            with self.subTest(change=change):
                self.context = copy.deepcopy(original); change(self.context); self.write_request()
                self.assertFalse(self.run_preview()['ok'])

    def test_duplicate_cycle_dangling_and_profile_unknowns_deny(self):
        original = copy.deepcopy(self.profile)
        changes = [lambda p: p['units'].append(copy.deepcopy(p['units'][0])),
                   lambda p: p['units'][0].update(depends_on=['child']),
                   lambda p: p['units'][0].update(depends_on=['absent']),
                   lambda p: p['units'][0]['profile'].update(uncertainties=['unresolved provenance']),
                   lambda p: p['units'][0]['profile'].update(context_requirement=None)]
        for change in changes:
            with self.subTest(change=change):
                profile = copy.deepcopy(original); change(profile); self.save(self.profile_path, profile)
                self.request['profile'] = self.pin(self.profile_path); self.write_request()
                self.assertFalse(self.run_preview()['ok'])

    def test_input_pin_spec_bytes_and_physical_path_denials(self):
        spec = Path(self.request['units'][0]['spec_file']['path'])
        original = spec.read_bytes()
        for raw in (original.rstrip(b'\n'), original + b' ', b'\xff', b'bad\x00spec'):
            spec.write_bytes(raw)
            self.assertFalse(self.run_preview()['ok'])
        spec.write_bytes(original)
        self.request['units'][0]['spec_file'] = self.pin(spec)
        alias = self.root / 'spec-alias'; alias.symlink_to(spec)
        self.request['units'][0]['spec_file']['path'] = str(alias); self.write_request()
        self.assertFalse(self.run_preview()['ok'])

    def test_source_drift_and_duplicate_json_reject(self):
        import shutil
        staged = self.root / 'copied-package'; shutil.copytree(PACKAGE, staged)
        changed = staged / 'scripts/route_select.py'
        changed.write_bytes(changed.read_bytes() + b'\n# changed original\n')
        process = subprocess.run([sys.executable, '-B', str(staged / 'scripts/routing_prepare.py'), 'preview',
            '--request', str(self.request_path), '--expect-request-sha256', self.pin(self.request_path)['sha256']],
            env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 1)
        self.assertIn('source policy drift', process.stdout)
        self.request_path.write_bytes(b'{"schema":1,"schema":2}')
        self.assertFalse(self.run_preview()['ok'])


if __name__ == '__main__':
    unittest.main()
