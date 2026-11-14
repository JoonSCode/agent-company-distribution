"""Synthetic prelaunch checks; no actual Orca worker is launched."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import routing_launch
import test_route_select


class LaunchTests(unittest.TestCase):
    def setUp(self):
        # Timeout diagnostics intentionally reject *any* writable/symlinked ancestor.
        # Linux /tmp (1777) is therefore not a positive diagnostic fixture, even
        # below a private child. Keep the production descriptor walk unchanged.
        fixtures = tempfile.TemporaryDirectory(prefix='.launch-tests-', dir=Path(__file__).resolve().parent)
        self.addCleanup(fixtures.cleanup)
        temporary_root = patch.object(tempfile, 'tempdir', fixtures.name)
        temporary_root.start()
        self.addCleanup(temporary_root.stop)
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
        executable = patch('routing_launch.shutil.which', side_effect=lambda value: value)
        executable.start()
        self.addCleanup(executable.stop)

    def test_manifest_and_capacity_before_any_probe(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            decision = {'binding': {'task': 'task', 'planned': True, 'parent_task': None, 'run': 'run', 'spec_sha256': hashlib.sha256(b'x').hexdigest()}}
            record = {'run': 'run', 'tasks': [{'id': 'task', 'current_dispatch': 'planned:task'}]}
            (root / 'decision').write_text(json.dumps(decision))
            (root / 'record').write_text(json.dumps(record))
            now = datetime.now(timezone.utc)
            stamp = lambda dt: dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            resource = {'service': 'codex', 'approval_ref': 'approval', 'auth': 'authenticated',
                        'hosts': ['host'], 'models': ['model'], 'efforts': ['high'], 'tools': ['read'],
                        'billing': 'subscription', 'quota': 'available', 'spending_ceiling': 0,
                        'observed_at': stamp(now - timedelta(days=1)), 'valid_until': stamp(now + timedelta(days=1))}
            manifest = root / 'manifest.json'
            def write(): manifest.write_text(json.dumps({'format': 'company-resource-manifest/v1', 'resources': [resource]}))
            write()
            args = ['--decision', str(root/'decision'), '--record', str(root/'record'), '--receipt', str(root/'receipt'),
                    '--result', str(root/'result'), '--from', 's', '--task', 'task', '--run', 'run', '--worktree', 'current']
            flags = ['--require-resource-manifest', '--resource-manifest', str(manifest), '--declared-host', 'host',
                     '--declared-tool', 'read', '--declared-billing', 'subscription', '--declared-spend', '0']
            checked = {'ok': True, 'label': 'real', 'errors': [], 'receipt': {'selected': {'route': 'codex', 'model': 'model', 'effort': 'high'}}}
            with patch('routing_launch.check_routing', side_effect=lambda *a, **k: copy.deepcopy(checked)), patch('routing_launch.subprocess.run') as host:
                for extra in (['--require-resource-manifest'], flags + ['--require-trusted-capacity'],
                              flags + ['--declared-host', 'wrong']):
                    self.assertEqual(routing_launch.main(args + extra), 1); host.assert_not_called()
                for key, value in [('auth', 'unknown'), ('quota', 'unknown'), ('billing', 'unknown'),
                                   ('valid_until', stamp(now - timedelta(hours=1)))]:
                    old = resource[key]; resource[key] = value; write()
                    self.assertEqual(routing_launch.main(args + flags), 1); host.assert_not_called()
                    resource[key] = old
                write()
                listed = {'ok': True, 'result': {'runId': 'run', 'tasks': [{'id': 'task', 'run_id': 'run', 'parent_id': None, 'spec': 'x', 'status': 'ready'}]}}
                launched = {'ok': True, 'result': {'runId': 'run', 'taskId': 'task', 'dispatchId': 'new', 'launch': {'effective': {'agent': 'codex', 'model': 'model', 'effort': 'high'}}}}
                host.side_effect = [SimpleNamespace(returncode=0, stdout=json.dumps(x), stderr='') for x in (listed, launched)]
                self.assertEqual(routing_launch.main(args + flags), 0)
                self.assertEqual(host.call_count, 2)
                self.assertEqual(json.loads((root/'receipt').read_text())['receipt']['resource_manifest']['status'], 'declared_ready')

    def test_fake_binaries_precedence_concurrency_and_crash(self):
        import multiprocessing
        import time
        import orca_contract
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bindir = root / 'bin'
            bindir.mkdir()
            log = root / 'calls'
            # The executables are local fakes, never the real Orca binary.
            fake = "#!" + __import__('sys').executable + "\n" + """import json, os, sys, time
with open(os.environ['FAKE_LOG'], 'a') as f:
    f.write(os.path.basename(sys.argv[0]) + ':' + ' '.join(sys.argv[1:3]) + '\\n')
time.sleep(float(os.environ.get('FAKE_DELAY', '0')))
name = sys.argv[2]
if name == 'task-list':
    result = {'runId': 'run', 'tasks': [{'id': 'task', 'run_id': 'run', 'parent_id': None, 'spec': 'original', 'status': 'failed'}]}
elif name == 'dispatch-show':
    result = {'dispatch': {'id': 'old'}}
elif name == 'worker-show':
    result = {'dispatch': {'id': 'old', 'taskId': 'task', 'runId': 'run', 'status': 'failed'}}
else:
    result = {'runId': 'run', 'taskId': 'task', 'dispatchId':'d', 'launch': {'effective': {'agent':'codex','model':'model','effort':'high'}}}
print(json.dumps({'ok': True, 'result': result}))
"""
            for name in ('explicit', 'env-cli', 'orca-dev', 'orca-ide', 'orca'):
                path = bindir / name
                path.write_text(fake)
                path.chmod(0o755)
            decision = {'binding': {'planned': True, 'parent_task': None,
                                    'spec_sha256': hashlib.sha256(b'x').hexdigest()}}
            (root / 'decision').write_text(json.dumps(decision))
            (root / 'record').write_text('{}')
            args = ['--decision', str(root / 'decision'), '--record', str(root / 'record'),
                    '--receipt', str(root / 'receipt'), '--result', str(root / 'result'),
                    '--from', 's', '--spec', 'x', '--worktree', 'current']
            check = {'ok': True, 'label': 'real', 'errors': [], 'receipt': {'selected': {'route': 'codex', 'model': 'model', 'effort': 'high'}}}
            env = {'PATH': str(bindir), 'FAKE_LOG': str(log)}
            # setUp mocks which; remove that patch for executable resolution.
            with patch('routing_launch.shutil.which', side_effect=lambda name: str(bindir / name) if (bindir / name).is_file() else None), patch('routing_launch.check_routing', return_value=check), patch.dict(os.environ, env, clear=True), patch.object(orca_contract.sys, 'platform', 'linux'):
                cases = [({'ORCA_CLI_COMMAND': 'env-cli', 'ORCA_DEV_REPO_ROOT': 'dev'}, ['--orca', 'explicit'], 'explicit'),
                         ({'ORCA_CLI_COMMAND': 'env-cli', 'ORCA_DEV_REPO_ROOT': 'dev'}, [], 'env-cli'),
                         ({'ORCA_DEV_REPO_ROOT': 'dev'}, [], 'orca-dev'),
                         ({}, [], 'orca-ide'), ({'ORCA_TERMINAL_HANDLE': 'managed'}, [], 'orca')]
                for n, (variables, override, expected) in enumerate(cases):
                    local = args.copy()
                    local[local.index('--receipt') + 1] = str(root / f'r{n}')
                    local[local.index('--result') + 1] = str(root / f's{n}')
                    with patch.dict(os.environ, variables), patch('routing_launch.resolve_orca', wraps=orca_contract.resolve_orca) as resolver:
                        self.assertEqual(routing_launch.main(local + override), 0)
                        self.assertEqual(resolver.call_count, 1)
                    self.assertTrue(log.read_text().splitlines()[-1].startswith(expected + ':'))
                retry_decision = {'binding': {'task': 'task', 'attempt': 'old', 'planned': False, 'parent_task': None, 'run': 'run', 'spec_sha256': hashlib.sha256(b'original').hexdigest()}}
                retry_record = {'run': 'run', 'tasks': [{'id': 'task', 'current_dispatch': 'old', 'execution': {'state': 'settled', 'result': {'outcome': 'failed'}}}]}
                (root / 'retry-decision').write_text(json.dumps(retry_decision))
                (root / 'retry-record').write_text(json.dumps(retry_record))
                retry_args = ['--decision', str(root / 'retry-decision'), '--record', str(root / 'retry-record'), '--receipt', str(root / 'retry-receipt'), '--result', str(root / 'retry-result'), '--from', 's', '--task', 'task', '--retry-of', 'old', '--run', 'run', '--worktree', 'current', '--orca', 'explicit']
                self.assertEqual(routing_launch.main(retry_args), 0)
                self.assertEqual(log.read_text().splitlines()[-4:], [
                    'explicit:orchestration task-list', 'explicit:orchestration dispatch-show',
                    'explicit:orchestration worker-show', 'explicit:orchestration worker-start'])
                # Two independent processes contest exactly the same state path.
                ctx = multiprocessing.get_context('fork')
                def launch():
                    os._exit(routing_launch.main(args + ['--orca', 'explicit']))
                with patch.dict(os.environ, {'FAKE_DELAY': '2'}):
                    first = ctx.Process(target=launch); first.start()
                    deadline = time.monotonic() + 10
                    while not (root / 'result').exists() or json.loads((root / 'result').read_text()).get('launch_state') != 'invocation_pending':
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(.01)
                    while len(log.read_text().splitlines()) < 10:
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(.01)
                    second = ctx.Process(target=launch); second.start(); second.join(10)
                    self.assertEqual(second.exitcode, 1)
                    first.terminate(); first.join(10)
                    self.assertEqual(json.loads((root / 'result').read_text())['launch_state'], 'invocation_pending')
                    before = len(log.read_text().splitlines())
                    self.assertEqual(routing_launch.main(args + ['--orca', 'explicit']), 1)
                    self.assertEqual(len(log.read_text().splitlines()), before)

    def test_real_sleep_timeout_and_no_second_start(self):
        import sys
        import time
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = root / 'fake'
            log = root / 'calls'
            fake.write_text('#!' + sys.executable + "\nimport sys,time\nfrom pathlib import Path\nPath(" + repr(str(log)) + ").write_text('started')\nprint('OFFLINE_STDOUT_MARKER',flush=True)\nprint('OFFLINE_STDERR_MARKER',file=sys.stderr,flush=True)\ntime.sleep(5)\n")
            fake.chmod(0o755)
            (root / 'decision').write_text(json.dumps({'binding': {'planned': True, 'parent_task': None, 'spec_sha256': hashlib.sha256(b'x').hexdigest()}}))
            (root / 'record').write_text('{}')
            args = ['--orca', str(fake), '--decision', str(root / 'decision'), '--record', str(root / 'record'), '--receipt', str(root / 'receipt'), '--result', str(root / 'result'), '--from', 's', '--spec', 'x', '--worktree', 'current', '--start-timeout', '0.8']
            check = {'ok': True, 'label': 'real', 'errors': [], 'receipt': {'selected': {'route': 'codex', 'model': 'model', 'effort': 'high'}}}
            with patch('routing_launch.check_routing', side_effect=lambda *a, **k: copy.deepcopy(check)):
                started = time.monotonic()
                self.assertEqual(routing_launch.main(args), 1)
                self.assertLess(time.monotonic() - started, 4)
                saved = json.loads((root / 'result').read_text())
                self.assertEqual(saved['launch_state'], 'unknown')
                self.assertEqual(saved['error_code'], 'host_start_timeout')
                self.assertEqual(saved['diagnostic_reference'], 'self')
                for stream, marker in [('stdout', b'OFFLINE_STDOUT_MARKER\n'), ('stderr', b'OFFLINE_STDERR_MARKER\n')]:
                    self.assertEqual(saved['partial_output'][stream]['type'], 'bytes')
                    self.assertEqual(saved['partial_output'][stream]['available_bytes'], len(marker))
                    self.assertEqual(saved['partial_output'][stream]['available_sha256'], hashlib.sha256(marker).hexdigest())
                    self.assertNotIn(marker.decode().strip(), (root / 'result').read_text())
                receipt = (root / 'receipt').read_bytes()
                self.assertEqual(log.read_text(), 'started')
                log.unlink()
                self.assertEqual(routing_launch.main(args), 1)
                self.assertFalse(log.exists())
                self.assertEqual((root / 'receipt').read_bytes(), receipt)

    def test_timeout_metadata_types_privacy_and_full_available_buffer(self):
        import contextlib
        import io
        import routing_explain

        class Unsupported:
            def __str__(self):
                raise AssertionError('must not stringify unsupported output')
            __repr__ = __str__

        sentinel = '«redacted:sk-timeout-secret»'
        values = [None, b'', '', b'\xff\xfe\x00', 'line\r\n\ud800',
                  sentinel.encode(), sentinel, b'A' * (5 * 1024 * 1024) + b'END', Unsupported()]
        for index, value in enumerate(values):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root/'decision').write_text(json.dumps({'binding': {'planned': True,
                    'parent_task': None, 'spec_sha256': hashlib.sha256(b'x').hexdigest()}}))
                (root/'record').write_text('{}')
                args = ['--decision', str(root/'decision'), '--record', str(root/'record'),
                        '--receipt', str(root/'receipt'), '--result', str(root/'result'),
                        '--from', 's', '--spec', 'x', '--worktree', 'current']
                check = {'ok': True, 'label': 'real', 'errors': [], 'receipt': {
                    'selected': {'route': 'codex', 'model': 'model', 'effort': 'high'}}}
                output, errors = io.StringIO(), io.StringIO()
                with patch('routing_launch.check_routing', side_effect=lambda *a, **k: copy.deepcopy(check)), \
                        patch('routing_launch.subprocess.run', side_effect=subprocess.TimeoutExpired(
                            [sentinel], 1, output=value, stderr=value)) as host, \
                        contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    self.assertEqual(routing_launch.main(args), 1)
                    receipt = (root/'receipt').read_bytes()
                    before = (root/'result').read_bytes()
                    self.assertEqual(routing_launch.main(args), 1)
                    self.assertEqual(host.call_count, 1)
                self.assertEqual((root/'receipt').read_bytes(), receipt)
                self.assertEqual((root/'result').read_bytes(), before)
                self.assertLessEqual(len(before), 4096)
                self.assertEqual((root/'result').stat().st_mode & 0o777, 0o600)
                state = json.loads(before)
                self.assertEqual(state['launch_state'], 'unknown')
                self.assertEqual(state['error_code'], 'host_start_timeout')
                data = value if isinstance(value, bytes) else value.encode('utf-8', 'surrogatepass') if isinstance(value, str) else None
                for stream in ('stdout', 'stderr'):
                    meta = state['partial_output'][stream]
                    self.assertEqual(meta['type'], 'none' if value is None else 'bytes' if isinstance(value, bytes) else 'str' if isinstance(value, str) else 'unsupported')
                    self.assertEqual(meta['present'], value is not None)
                    self.assertEqual(meta['available_bytes'], len(data) if data is not None else None)
                    self.assertEqual(meta['available_sha256'], hashlib.sha256(data).hexdigest() if data is not None else None)
                    self.assertEqual(meta['hash_scope'], 'available_buffer' if data is not None else 'none')
                    self.assertEqual(meta['encoding'], 'raw' if isinstance(value, bytes) else 'utf-8/surrogatepass' if isinstance(value, str) else None)
                    self.assertIs(meta['raw_retained'], False)
                    if data and len(data) > 4096:
                        self.assertNotEqual(meta['available_sha256'], hashlib.sha256(data[:4096]).hexdigest())
                report = routing_explain.explain(root/'result', root/'receipt')
                self.assertTrue(report['read_only'])
                self.assertFalse(report['same_attempt_retry_allowed'])
                self.assertEqual(report['local_state'], 'unknown')
                self.assertEqual((root/'result').read_bytes(), before)
                public = output.getvalue() + errors.getvalue() + json.dumps(report)
                self.assertNotIn(sentinel, public + before.decode())
                self.assertNotIn('sk-timeout-secret', public + before.decode())
                self.assertNotIn('available_sha256', json.dumps(report))
                if data is not None:
                    digest = hashlib.sha256(data).hexdigest()
                    self.assertNotIn(digest, output.getvalue() + errors.getvalue())
                    # The unchanged reader hashes the empty lock artifact too.
                    # That pre-existing empty-file digest is not a stream projection.
                    if data:
                        self.assertNotIn(digest, json.dumps(report))
                self.assertEqual(errors.getvalue(), '')

    def test_timeout_unsafe_diagnostics_and_write_errors_preserve_pending(self):
        import contextlib
        import io
        import stat
        import routing_explain
        cases = ('file_mode', 'parent_mode', 'symlink', 'parent_symlink', 'hardlink', 'fifo',
                 'directory', 'foreign_owner', 'device', 'temp_open', 'write', 'file_sync',
                 'replace', 'directory_sync', 'cleanup')
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
                root = Path(temp)
                parent = root/'private'
                parent.mkdir(mode=0o700)
                result = parent/'result'
                decision, record, receipt = root/'decision', root/'record', root/'receipt'
                decision.write_text(json.dumps({'binding': {'planned': True, 'parent_task': None,
                    'spec_sha256': hashlib.sha256(b'x').hexdigest()}}))
                record.write_text('{}')
                args = ['--decision', str(decision), '--record', str(record), '--receipt', str(receipt),
                        '--result', str(result), '--from', 's', '--spec', 'x', '--worktree', 'current']
                check = {'ok': True, 'label': 'real', 'errors': [], 'receipt': {
                    'selected': {'route': 'codex', 'model': 'model', 'effort': 'high'}}}
                original_open, original_sync = os.open, os.fsync
                original_replace, original_fstat = os.replace, os.fstat
                pending, immutable = [], []
                def fail_host(*a, **k):
                    pending.append(result.read_bytes())
                    immutable.append(receipt.read_bytes())
                    if case == 'file_mode': result.chmod(0o644)
                    if case == 'parent_mode': parent.chmod(0o777)
                    if case in ('symlink', 'fifo', 'directory'):
                        result.rename(parent/'pending')
                        if case == 'symlink': result.symlink_to(parent/'pending')
                        elif case == 'fifo': os.mkfifo(result)
                        else: result.mkdir()
                    if case == 'parent_symlink':
                        parent.rename(root/'actual')
                        parent.symlink_to(root/'actual', target_is_directory=True)
                    if case == 'hardlink': os.link(result, parent/'linked')
                    if case in ('foreign_owner', 'device'):
                        def fstat(fd):
                            info = original_fstat(fd)
                            if stat.S_ISREG(info.st_mode):
                                fields = list(info)
                                fields[4 if case == 'foreign_owner' else 0] = os.getuid() + 1 if case == 'foreign_owner' else stat.S_IFCHR | 0o600
                                return os.stat_result(fields)
                            return info
                        stack.enter_context(patch('routing_launch.os.fstat', side_effect=fstat))
                    if case == 'temp_open':
                        def open_failure(path, *a, **k):
                            if str(path).startswith('.timeout-'): raise OSError('sk-write-error-secret')
                            return original_open(path, *a, **k)
                        stack.enter_context(patch('routing_launch.os.open', side_effect=open_failure))
                    if case == 'write':
                        fdopen = os.fdopen
                        @contextlib.contextmanager
                        def bad_stream(fd, *a, **k):
                            with fdopen(fd, *a, **k):
                                class Broken:
                                    def write(self, value):
                                        raise OSError('sk-write-error-secret')
                                yield Broken()
                        stack.enter_context(patch('routing_launch.os.fdopen', side_effect=bad_stream))
                    if case == 'cleanup':
                        unlink = os.unlink
                        failed = []
                        def unlink_failure(path, *a, **k):
                            if str(path).startswith('.timeout-') and not failed:
                                failed.append(True)
                                raise OSError('sk-cleanup-error-secret')
                            return unlink(path, *a, **k)
                        stack.enter_context(patch('routing_launch.os.unlink', side_effect=unlink_failure))
                    if case in ('file_sync', 'directory_sync'):
                        def sync_failure(fd):
                            directory = stat.S_ISDIR(original_fstat(fd).st_mode)
                            if directory == (case == 'directory_sync'): raise OSError('sk-sync-error-secret')
                            return original_sync(fd)
                        stack.enter_context(patch('routing_launch.os.fsync', side_effect=sync_failure))
                    if case == 'replace':
                        def replace_failure(*a, **k):
                            if 'src_dir_fd' in k: raise OSError('sk-replace-error-secret')
                            return original_replace(*a, **k)
                        stack.enter_context(patch('routing_launch.os.replace', side_effect=replace_failure))
                    raise subprocess.TimeoutExpired(['sk-command-secret'], 1, output=b'sk-output-secret', stderr=b'sk-error-secret')
                out, err = io.StringIO(), io.StringIO()
                with patch('routing_launch.check_routing', side_effect=lambda *a, **k: copy.deepcopy(check)), \
                        patch('routing_launch.subprocess.run', side_effect=fail_host) as host, \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    self.assertEqual(routing_launch.main(args), 1)
                    self.assertEqual(host.call_count, 1)
                stack.close()  # Faults affect diagnostic persistence, not the read-only verifier.
                response = json.loads(out.getvalue())
                self.assertEqual((response['launch_state'], response['error_code'], response['diagnostic']),
                                 ('unknown', 'host_start_timeout', 'unavailable'))
                self.assertNotIn('sk-', out.getvalue() + err.getvalue())
                self.assertEqual(receipt.read_bytes(), immutable[0])
                saved = parent/'pending' if case in ('symlink', 'fifo', 'directory') else result
                self.assertEqual(saved.read_bytes(), pending[0])
                if case == 'file_mode': self.assertEqual(result.stat().st_mode & 0o777, 0o644)
                if case == 'parent_mode': self.assertEqual(parent.stat().st_mode & 0o777, 0o777)
                # Reader refuses unsafe fixtures or sees pending; it never grants retry.
                report = routing_explain.explain(result, receipt)
                self.assertFalse(report['same_attempt_retry_allowed'])
                self.assertTrue(report['read_only'])
                if case not in ('fifo', 'directory'):
                    with patch('routing_launch.subprocess.run') as host, contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(routing_launch.main(args), 1)
                        host.assert_not_called()
                parent.chmod(0o700)

    def test_timeout_writable_ancestor_preserves_pending_and_blocks_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ancestor = root / 'shared'
            ancestor.mkdir()
            ancestor.chmod(0o1777)
            private = ancestor / 'private'
            private.mkdir(mode=0o700)
            result = private / 'result'
            routing_launch.atomic_state(result, {'launch_state_version': 1, 'launch_state': 'invocation_pending'})
            before = result.read_bytes()
            with self.assertRaisesRegex(ValueError, 'unsafe diagnostic directory'):
                routing_launch.write_timeout_state(result, {'launch_state': 'unknown'})
            self.assertEqual(result.read_bytes(), before)
            self.assertEqual(ancestor.stat().st_mode & 0o7777, 0o1777)
            self.assertEqual(sorted(p.name for p in private.iterdir()), ['result'])
            args = ['--decision', str(root/'decision'), '--record', str(root/'record'),
                    '--receipt', str(root/'receipt'), '--result', str(result),
                    '--from', 's', '--spec', 'x', '--worktree', 'current']
            with patch('routing_launch.subprocess.run') as host:
                self.assertEqual(routing_launch.main(args), 1)
                host.assert_not_called()
            self.assertEqual(result.read_bytes(), before)

    def test_start_oserror_stays_unknown_and_never_retries(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'decision').write_text(json.dumps({'binding': {'planned': True, 'parent_task': None,
                'spec_sha256': hashlib.sha256(b'x').hexdigest()}}))
            (root/'record').write_text('{}')
            args = ['--decision', str(root/'decision'), '--record', str(root/'record'),
                    '--receipt', str(root/'receipt'), '--result', str(root/'result'),
                    '--from', 's', '--spec', 'x', '--worktree', 'current']
            checked = {'ok': True, 'label': 'real', 'errors': [], 'receipt': {
                'selected': {'route': 'codex', 'model': 'model', 'effort': 'high'}}}
            with patch('routing_launch.check_routing', return_value=checked), \
                    patch('routing_launch.subprocess.run', side_effect=OSError('offline start failed')) as host, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(routing_launch.main(args), 1)
                receipt = (root/'receipt').read_bytes()
                self.assertEqual(json.loads((root/'result').read_bytes())['launch_state'], 'unknown')
                self.assertEqual(routing_launch.main(args), 1)
                self.assertEqual(host.call_count, 1)
                self.assertEqual((root/'receipt').read_bytes(), receipt)

    def test_help_and_invalid_timeout_do_not_create_state(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = ['--decision', 'd', '--record', 'r', '--receipt', str(root / 'receipt'), '--result', str(root / 'result'), '--from', 's', '--spec', 'x', '--worktree', 'current']
            for extra, code in [(['--help'], 0), (['--start-timeout', 'nan'], 2), (['--probe-timeout', 'inf'], 2), (['--probe-timeout', '0'], 2)]:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                    routing_launch.main(args + extra)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(list(root.iterdir()), [])

    def test_atomic_replace_failure_preserves_previous_state(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / 'state'
            routing_launch.atomic_state(state, {'launch_state': 'invocation_pending'})
            with patch('routing_launch.os.replace', side_effect=OSError('injected')):
                with self.assertRaises(OSError):
                    routing_launch.atomic_state(state, {'launch_state': 'observed'})
            self.assertEqual(json.loads(state.read_text())['launch_state'], 'invocation_pending')
            self.assertEqual([p.name for p in state.parent.iterdir()], ['state'])

    def test_durable_rejection_restart_and_lock(self):
        import fcntl
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = root / 'state'
            args = ['--decision', str(root / 'missing'), '--record', str(root / 'record'),
                    '--receipt', str(root / 'receipt'), '--result', str(result), '--from', 's',
                    '--spec', 'x', '--worktree', 'current']
            with patch('routing_launch.shutil.which', return_value=None), patch('routing_launch.subprocess.run') as run:
                self.assertEqual(routing_launch.main(args), 1)
                run.assert_not_called()
            self.assertEqual(json.loads(result.read_text())['launch_state'], 'not_started')
            routing_launch.atomic_state(result, {'launch_state_version': 1, 'launch_state': 'invocation_pending'})
            with patch('routing_launch.subprocess.run') as run:
                self.assertEqual(routing_launch.main(args), 1)
                run.assert_not_called()
            self.assertFalse((root / 'receipt').exists())
            routing_launch.atomic_state(result, {'launch_state_version': 1, 'launch_state': 'not_started'})
            with (root / 'state.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch('routing_launch.subprocess.run') as run:
                    self.assertEqual(routing_launch.main(args), 1)
                    run.assert_not_called()
            self.assertFalse((root / 'receipt').exists())

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
            args.extend(['--orca', '/synthetic/orca'])
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
                self.assertTrue(all(call.args[0][0] == '/synthetic/orca' for call in host.call_args_list))
                self.assertEqual([call.kwargs['timeout'] for call in host.call_args_list], [30.0, 30.0, 30.0, 300.0])
                self.assertEqual(json.loads((root / 'result').read_text())['launch_state'], 'observed')
                self.assertEqual(command[command.index('--task') + 1], 'task')
                self.assertEqual(command[command.index('--retry-of') + 1], 'old')
                self.assertEqual(command[command.index('--run') + 1], 'run')
                self.assertNotIn('--spec', command)
            timeout_args = args.copy()
            timeout_args[timeout_args.index('--receipt') + 1] = str(root / 'timeout-pre')
            timeout_args[timeout_args.index('--result') + 1] = str(root / 'timeout-result')
            with patch('routing_launch.check_routing', return_value=copy.deepcopy(check)), patch('routing_launch.subprocess.run', side_effect=[response(listed), response(latest), response(failed), subprocess.TimeoutExpired('orca', 1)]):
                self.assertEqual(routing_launch.main(timeout_args), 1)
            self.assertEqual(json.loads((root / 'timeout-result').read_text())['launch_state'], 'unknown')
            timeout_args[timeout_args.index('--receipt') + 1] = str(root / 'timeout-pre-2')
            with patch('routing_launch.check_routing', return_value=copy.deepcopy(check)), patch('routing_launch.subprocess.run', side_effect=[response(listed), response(latest), response(failed)]) as host:
                self.assertEqual(routing_launch.main(timeout_args), 1)
                self.assertEqual(host.call_count, 0)  # rejected before probes or receipt
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
            for index, mutation in enumerate(('missing_run', 'wrong_run', 'wrong_task', 'same_dispatch', 'missing_settings', 'nonzero', 'empty', 'corrupt', 'signal')):
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
                if mutation == 'signal': final.returncode = -9
                if mutation == 'empty': final.stdout = ''
                if mutation == 'corrupt': final.stdout = '{invalid'
                with patch('routing_launch.check_routing', return_value=copy.deepcopy(check)), patch('routing_launch.subprocess.run', side_effect=[response(listed), response(latest), response(failed), final]) as host:
                    self.assertEqual(routing_launch.main(args), 1)
                    self.assertEqual(host.call_count, 4)
                    saved = json.loads(result_path.read_text())
                    self.assertEqual(saved['stdout'], final.stdout)
                    self.assertNotEqual(saved['readback_status'], 'observed')
                    self.assertEqual(saved['launch_state'], 'unknown')
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

    def test_profile_binding_fake_host_and_tampering(self):
        import record_check
        fixture = test_route_select.SelectionCLITests(); fixture.setUp()
        packet = fixture.packet()
        packet['binding'].update(task='one', attempt='planned:one', planned=True,
                                 spec_sha256=hashlib.sha256(b'bounded test').hexdigest())
        record = copy.deepcopy(json.loads((test_route_select.PACKAGE / 'assets/record-cases.json').read_text())['cases'][0]['record'])
        profile = json.loads((test_route_select.PACKAGE / 'assets/worker-profile-example.json').read_text())
        table = json.loads((test_route_select.PACKAGE / 'assets/worker-routing-table.json').read_text())
        for row in table['entries']:
            row['candidates'][0].update(input_modalities=['text'], output_modalities=['text'],
                capabilities=['general.execute'], evidence=['synthetic assertion'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'profile.json').write_text(json.dumps(profile)); (root/'external-table.json').write_text(json.dumps(table))
            cli = [__import__('sys').executable, '-B', str(test_route_select.CLI), 'profile-prepare', str(root/'profile.json'), '--unit', 'one', '--table', str(root/'external-table.json')]
            prepared = subprocess.run(cli, text=True, capture_output=True, check=True)
            packet['profile_binding'] = json.loads(prepared.stdout)['profile_binding']
            packet['label'] = 'real'
            for item in packet['evidence'].values():
                if item['kind'] == 'synthetic': item['kind'] = 'host'
            inventory = root/'models_cache.json'
            inventory.write_text(json.dumps({'models': packet['evidence']['inventory']['host_models']}))
            packet['evidence']['inventory'].update(file=inventory.name, sha256=hashlib.sha256(inventory.read_bytes()).hexdigest(), observed_at='2020-01-01T00:00:00Z', valid_until='2100-01-01T00:00:00Z')
            decision=root/'decision'; current=root/'record'; current.write_text(json.dumps(record))
            args=['--decision',str(decision),'--record',str(current),'--receipt',str(root/'receipt'), '--result',str(root/'result'), '--from','sender','--spec','bounded test','--worktree','current']
            with patch('record_check.canonical_home', return_value=root):
                for field in ('profile', 'table', 'selected', 'eligible_chain', 'fallback_index', 'selection_reasons', 'selected_source', 'default_provenance'):
                    altered=copy.deepcopy(packet)
                    if field == 'profile': altered['profile_binding']['profile']['units'][0]['objective']='tampered'
                    elif field == 'table': altered['profile_binding']['table']['source']='tampered'
                    elif field == 'selected': altered['profile_binding']['selected']['effort']='high'
                    elif field == 'fallback_index': altered['profile_binding'][field]=3
                    else: altered['profile_binding'][field]=[{'tampered': True}]
                    decision.write_text(json.dumps(altered))
                    with patch('routing_launch.subprocess.run') as host:
                        self.assertEqual(routing_launch.main(args),1); host.assert_not_called()
                decision.write_text(json.dumps(packet))
                result={'ok':True,'result':{'taskId':'task-host','dispatchId':'dispatch-host','launch':{'effective':{'agent':'codex','model':packet['selected']['model'],'effort':packet['selected']['effort']}}}}
                with patch('routing_launch.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(result),stderr='')) as host:
                    self.assertEqual(routing_launch.main(args),0)
                    command=host.call_args.args[0]
                    self.assertEqual(command[command.index('--model')+1],packet['selected']['model'])
                    self.assertEqual(command[command.index('--effort')+1],packet['selected']['effort'])

    def test_profile_three_levels_fake_host(self):
        for level, family, effort in [('easy','terra','low'), ('medium','terra','medium'), ('hard','sol','high'), ('shared','terra','medium')]:
            with self.subTest(level=level), tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                fixture=test_route_select.SelectionCLITests(); fixture.setUp()
                fixture.selection['candidates']=[test_route_select.candidate(family,effort)]
                packet=fixture.packet()
                packet['binding'].update(task='one',attempt='planned:one',planned=True,spec_sha256=hashlib.sha256(b'bounded test').hexdigest())
                packet['label']='real'
                for item in packet['evidence'].values():
                    if item['kind']=='synthetic': item['kind']='host'
                inv=root/'models_cache.json'; inv.write_text(json.dumps({'models':packet['evidence']['inventory']['host_models']}))
                packet['evidence']['inventory'].update(file=inv.name,sha256=hashlib.sha256(inv.read_bytes()).hexdigest(),observed_at='2020-01-01T00:00:00Z',valid_until='2100-01-01T00:00:00Z')
                profile=json.loads((test_route_select.PACKAGE/'assets/worker-profile-example.json').read_text());profile['units'][0]['profile']['difficulty']='easy' if level == 'shared' else level
                table=json.loads((test_route_select.PACKAGE/'assets/worker-routing-table.json').read_text())
                for row in table['entries']:
                    row['candidates'][0].update(input_modalities=['text'],output_modalities=['text'],capabilities=['general.execute'],evidence=['synthetic assertion'])
                if level == 'shared':
                    for candidate, model in zip(table['entries'][0]['candidates'], ['gpt-6-luna', 'gpt-6.1-sol', 'gpt-6-astra']):
                        candidate['identity']['model'] = model
                        candidate['enabled'] = False
                (root/'profile').write_text(json.dumps(profile));(root/'table').write_text(json.dumps(table))
                cli=[__import__('sys').executable,'-B',str(test_route_select.CLI),'profile-prepare',str(root/'profile'),'--table',str(root/'table'),'--unit','one']
                packet['profile_binding']=json.loads(subprocess.run(cli,capture_output=True,text=True,check=True).stdout)['profile_binding']
                decision=root/'decision';decision.write_text(json.dumps(packet))
                record=json.loads((test_route_select.PACKAGE/'assets/record-cases.json').read_text())['cases'][0]['record'];(root/'record').write_text(json.dumps(record))
                args=['--decision',str(decision),'--record',str(root/'record'),'--receipt',str(root/'receipt'),'--result',str(root/'result'),'--from','sender','--spec','bounded test','--worktree','current']
                result={'ok':True,'result':{'taskId':'task-host','dispatchId':'dispatch-host','launch':{'effective':{'agent':'codex','model':packet['selected']['model'],'effort':effort}}}}
                with patch('record_check.canonical_home',return_value=root), patch('routing_launch.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(result),stderr='')) as host:
                    self.assertEqual(routing_launch.main(args),0)
                    command=host.call_args.args[0];self.assertEqual(command[command.index('--effort')+1],effort);self.assertEqual(command[command.index('--model')+1],packet['selected']['model'])

    def test_multimodal_cli_checker_and_launch_reject_missing_requirements(self):
        import record_check
        import worker_route

        fixture = test_route_select.SelectionCLITests(); fixture.setUp()
        packet = fixture.packet()
        packet['binding'].update(task='one', attempt='planned:one', planned=True,
                                 spec_sha256=hashlib.sha256(b'bounded test').hexdigest())
        packet['label'] = 'real'
        for item in packet['evidence'].values():
            if item['kind'] == 'synthetic': item['kind'] = 'host'
        profile = json.loads((test_route_select.PACKAGE / 'assets/worker-profile-example.json').read_text())
        profile['units'][0]['profile'].update(family='code', input_modalities=['text', 'image'],
            output_modalities=['code'], required_capabilities=['vision.read', 'frontend.code'])
        table = json.loads((test_route_select.PACKAGE / 'assets/worker-routing-table.json').read_text())
        candidate = copy.deepcopy(table['entries'][0]['candidates'][0])
        candidate.update(input_modalities=['text', 'image'], output_modalities=['code'],
                         capabilities=['vision.read', 'frontend.code'], evidence=['synthetic assertion'])
        # Replace the configured row; do not manufacture a duplicate table key.
        table['entries'] = [r for r in table['entries'] if (r['family'], r['difficulty']) != ('code', 'easy')]
        table['entries'].append({'family': 'code', 'difficulty': 'easy', 'candidates': [candidate]})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = root / 'models_cache.json'
            inventory.write_text(json.dumps({'models': packet['evidence']['inventory']['host_models']}))
            packet['evidence']['inventory'].update(file=inventory.name, sha256=hashlib.sha256(inventory.read_bytes()).hexdigest(), observed_at='2020-01-01T00:00:00Z', valid_until='2100-01-01T00:00:00Z')
            profile_path, table_path = root / 'profile.json', root / 'table.json'
            profile_path.write_text(json.dumps(profile)); table_path.write_text(json.dumps(table))
            cli = [__import__('sys').executable, '-B', str(test_route_select.CLI), 'profile-prepare', str(profile_path), '--unit', 'one', '--table', str(table_path)]
            good = subprocess.run(cli, capture_output=True, text=True, check=True)
            binding = json.loads(good.stdout)['profile_binding']
            record = json.loads((test_route_select.PACKAGE / 'assets/record-cases.json').read_text())['cases'][0]['record']
            (root / 'record').write_text(json.dumps(record))
            args = ['--decision', str(root / 'decision'), '--record', str(root / 'record'), '--receipt', str(root / 'receipt'), '--result', str(root / 'result'), '--from', 'sender', '--spec', 'bounded test', '--worktree', 'current']
            fake = {'ok': True, 'result': {'taskId': 'task-host', 'dispatchId': 'dispatch-host', 'launch': {'effective': {'agent': 'codex', 'model': packet['selected']['model'], 'effort': packet['selected']['effort']}}}}
            packet['profile_binding'] = binding
            (root / 'decision').write_text(json.dumps(packet))
            with patch('record_check.canonical_home', return_value=root), patch('routing_launch.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps(fake), stderr='')) as host:
                self.assertEqual(routing_launch.main(args), 0); self.assertEqual(host.call_count, 1)
            for name in ('missing_input', 'missing_capability', 'wrong_output_direction'):
                with self.subTest(name=name):
                    bad = copy.deepcopy(table)
                    c = bad['entries'][-1]['candidates'][0]
                    if name == 'missing_input': c['input_modalities'] = ['text']
                    elif name == 'missing_capability': c['capabilities'] = ['vision.read']
                    else: c['input_modalities'] = ['text', 'image', 'code']; c['output_modalities'] = ['image']
                    table_path.write_text(json.dumps(bad))
                    rejected = subprocess.run(cli, capture_output=True, text=True)
                    self.assertNotEqual(rejected.returncode, 0)
                    self.assertEqual(json.loads(rejected.stdout)['errors'][0]['code'], 'NO_MATCH')
                    forged = copy.deepcopy(binding)
                    forged['table'] = bad
                    forged['table_sha256'] = worker_route.digest(bad)
                    packet['profile_binding'] = forged
                    (root / 'decision').write_text(json.dumps(packet))
                    with patch('record_check.canonical_home', return_value=root):
                        checked = record_check.check_routing(packet, test_route_select.PACKAGE, prelaunch=True)
                        self.assertIn('profile_binding_invalid', [e['code'] for e in checked['errors']])
                        self.assertTrue(any('NO_MATCH' in e.get('message', '') for e in checked['errors']), checked['errors'])
                        import contextlib
                        import io
                        args[args.index('--result') + 1] = str(root / ('result-' + name))
                        args[args.index('--receipt') + 1] = str(root / ('receipt-' + name))
                        output = io.StringIO()
                        with patch('routing_launch.subprocess.run') as host, contextlib.redirect_stdout(output):
                            self.assertEqual(routing_launch.main(args), 1); host.assert_not_called()
                        self.assertIn('profile_binding_invalid', output.getvalue())
                        self.assertIn('NO_MATCH', output.getvalue())

    def test_profile_bound_user_pin(self):
        import record_check
        fixture=test_route_select.SelectionCLITests();fixture.setUp();packet=fixture.packet()
        profile=json.loads((test_route_select.PACKAGE/'assets/worker-profile-example.json').read_text())
        profile['units'][0]['id']=packet['binding']['task']
        table=json.loads((test_route_select.PACKAGE/'assets/worker-routing-table.json').read_text())
        for row in table['entries']:
            row['candidates'][0].update(input_modalities=['text'],output_modalities=['text'],capabilities=['general.execute'],evidence=['synthetic assertion'])
        ident={k:packet['selected'][k] for k in ('route','model','effort')}
        del packet['price_selection'];packet['selected_reason']='user_pin';packet['alternatives'][0]['reason']='user_pin'
        packet['evidence']['quality']['binds']={k:packet['selected'][k] for k in ('route','family','model','effort')}
        packet['evidence']['quality']['task_binding']={k:packet['binding'][k] for k in ('task','scope','revision','attempt')}
        packet['profile_binding']=record_check.make_profile_binding(profile,table,packet['binding']['task'],{packet['binding']['task']:ident})
        result=record_check.check_routing(packet,test_route_select.PACKAGE,prelaunch=True);self.assertTrue(result['ok'],result['errors'])
        packet['evidence']['quality']['task_binding']['task']='other'
        self.assertIn('unbound_pin',[e['code'] for e in record_check.check_routing(packet,test_route_select.PACKAGE,prelaunch=True)['errors']])

    def test_measurement_gate_blocks_before_worker_start(self):
        import contextlib
        import io
        from test_measurement_gate import MeasurementGateTests

        fixture = MeasurementGateTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        root = fixture.base
        select = test_route_select.SelectionCLITests()
        select.setUp()
        self.addCleanup(select.doCleanups)
        packet = select.packet()
        packet['binding'].update(task='new', attempt='planned:new', planned=True,
                                 spec_sha256=hashlib.sha256(b'bounded test').hexdigest(), parent_task='parent-task')
        packet['label'] = 'real'
        for item in packet['evidence'].values():
            if item['kind'] == 'synthetic':
                item['kind'] = 'host'
        inventory = root / 'models_cache.json'
        inventory.write_text(json.dumps({'models': packet['evidence']['inventory']['host_models']}))
        packet['evidence']['inventory'].update(file=inventory.name, sha256=hashlib.sha256(inventory.read_bytes()).hexdigest(),
                                               observed_at='2020-01-01T00:00:00Z', valid_until='2100-01-01T00:00:00Z')
        decision, record = root / 'decision.json', root / 'record.json'
        decision.write_text(json.dumps(packet))
        args = ['--decision', str(decision), '--record', str(record), '--receipt', str(root / 'receipt.json'),
                '--result', str(root / 'host.json'), '--from', 'term-example', '--spec', 'bounded test',
                '--worktree', 'current', '--parent', 'parent-task']
        for missing in (False, True):
            candidate = copy.deepcopy(fixture.record)
            if missing:
                candidate['measurement']['participants'][0]['source'] = '/missing/provider-source'
            record.write_text(json.dumps(candidate))
            output = io.StringIO()
            with patch('record_check.canonical_home', return_value=root), patch('routing_launch.subprocess.run') as host, contextlib.redirect_stdout(output):
                self.assertEqual(routing_launch.main(args), 1)
                host.assert_not_called()
            errors = {item['code'] for item in json.loads(output.getvalue())['errors']}
            self.assertIn('measurement_future_unbound', errors)
            if missing:
                self.assertIn('measurement_source', errors)
            self.assertFalse((root / 'receipt.json').exists())


if __name__ == '__main__':
    unittest.main()
