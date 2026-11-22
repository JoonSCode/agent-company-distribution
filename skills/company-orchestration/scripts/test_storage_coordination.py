"""Real OS-process fixtures only; fake host/consent is never real authority."""
import copy
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest

import native_storage as storage
import run_completion as rc
from catalog_test_support import routing_packet
from test_native_operations import save, pin, digest, tree

PACKAGE = Path(__file__).resolve().parents[1]


class CombinedFixture:
    def __init__(self, base, *, packet_transform=None):
        self.base = Path(base)
        self.base.mkdir(exist_ok=True)
        self.home = self.base / 'sejong'
        self.run = self.home / 'runs/fixture'
        self.run.mkdir(parents=True)
        self.cwd = self.base / 'workspace'; self.cwd.mkdir()
        self.env = {k: os.environ[k] for k in ('PATH', 'TMPDIR') if k in os.environ}
        self.env.update(HOME=str(self.base), CODEX_HOME=str(self.run), PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', UV_OFFLINE='1', UV_PYTHON_DOWNLOADS='never')
        self.config = self.base / 'user.md'
        self.config.write_text('---\nschema_version: 1\npreset: multiple\nservices: ["codex", "antigravity"]\napi_paid: false\n---\n')
        self.env['AGENT_COMPANY_CONFIG'] = str(self.config)
        identity = save(self.base / 'identity.json', dict(host='explicit_lead', session_id='synthetic-combined', cwd=str(self.cwd)))
        self.enrollment = save(self.base / 'enroll.json', dict(schema='company-native-storage-enrollment/v1', sejong_home=str(self.home), run=str(self.run), run_id='goal-1', owner='B', record='record.json', host='explicit_lead', session_id='synthetic-combined', cwd=str(self.cwd), consumers=[], expect_session_binding_sha256=None, identity_evidence=pin(identity)))
        self.observations = []
        self.cli('enroll', self.enrollment)
        rows = [self.row(p, 'recreatable' if p == 'scratch/raw' else 'preserve') for p in
                ('report.md', 'acceptance.json', 'scratch/raw', 'decision.json', 'models_cache.json', 'raw-qa.log', 'lesson.md', 'source.txt')]
        self.classify(rows)
        (self.run / 'scratch').mkdir()
        for p, data in {'scratch/raw': b'disposable only', 'report.md': b'retained original report', 'acceptance.json': b'{"synthetic_acceptance":true}', 'raw-qa.log': b'original failed QA retained', 'lesson.md': b'original decision lesson', 'source.txt': b'unique required source original'}.items():
            (self.run / p).write_bytes(data)
        self.packet = routing_packet()
        self.packet['binding'].update(task='new', attempt='planned:new', planned=True, spec_sha256=rc.sha(b'bounded test'), parent_task=None)
        from record_check import make_profile_binding
        profile = json.loads((PACKAGE / 'assets/worker-profile-example.json').read_text())
        profile['units'][0]['id'] = 'new'
        table = json.loads((PACKAGE / 'assets/worker-routing-table.json').read_text())
        self.packet['profile_binding'] = make_profile_binding(profile, table, 'new')
        self.packet['label'] = 'real'
        for item in self.packet['evidence'].values(): item['kind'] = 'host'
        cache = save(self.run / 'models_cache.json', dict(models=self.packet['evidence']['inventory']['host_models']))
        self.packet['evidence']['inventory'].update(file=str(cache), sha256=digest(cache), observed_at='2020-01-01T00:00:00Z', valid_until='2100-01-01T00:00:00Z')
        if packet_transform is not None:
            packet_transform(self)
        save(self.run / 'decision.json', self.packet)
        self.record = copy.deepcopy(json.loads((PACKAGE / 'assets/record-cases.json').read_bytes())['cases'][0]['record'])
        self.record['label'] = 'real'
        for row in self.record['evidence'].values(): row['kind'] = 'host'
        save(self.run / 'record.json', self.record)
        self.classify(rows, 'freeze')
        self.host = self.base / 'fake-orca'
        start = dict(ok=True, result=dict(taskId='task-1', dispatchId='dispatch-current', processIncarnation='fake-incarnation', launch=dict(effective=dict(agent='codex', model=self.packet['selected']['model'], effort=self.packet['selected']['effort']))))
        exit_value = dict(ok=True, result=dict(dispatch=dict(id='dispatch-current', taskId='task-1', processIncarnation='fake-incarnation', status='completed'), observation=dict(exactWorker=True, status='exited')))
        self.host.write_text('#!' + sys.executable + '\nimport json,sys\nfrom pathlib import Path\nb=Path(__file__).parent\nif "worker-start" in sys.argv:\n with (b/"starts").open("a") as f: f.write("start\\n")\n if (b/"host-ready").exists():\n  with (b/"host-ready").open("w") as f: f.write("ready\\n")\n  with (b/"host-release").open() as f: f.read(1)\n value=json.loads(' + repr(json.dumps(start)) + ')\nelse:\n value=json.loads(' + repr(json.dumps(exit_value)) + ')\n if (b/"live").exists(): value["result"]["observation"]["status"]="live"\nprint(json.dumps(value))\n')
        self.host.chmod(0o700)
        self.args = ['--enrollment-request', str(self.enrollment), '--expect-enrollment-sha256', digest(self.enrollment), '--decision', str(self.run / 'decision.json'), '--record', str(self.run / 'record.json'), '--receipt', str(self.run / 'launch-receipt.json'), '--result', str(self.run / 'result.json'), '--from', 'fixture', '--spec', 'bounded test', '--worktree', 'current', '--orca', str(self.host)]
        self.originals = {p.name: (digest(p), rc.signature(p.stat())) for p in self.run.iterdir() if p.is_file() and p.name not in (rc.MANIFEST, rc.LOCK, 'record.json')}

    def command(self, argv, expected=0):
        p = subprocess.run(list(map(str, argv)), cwd=self.cwd, env=self.env, capture_output=True, text=True, timeout=60)
        row = dict(argv=list(map(str, argv)), exit=p.returncode, stdout=p.stdout, stderr=p.stderr)
        self.observations.append(row)
        assert p.returncode == expected, row
        return json.loads(p.stdout)

    def cli(self, action, path=None, expected=0, extra=()):
        return self.command([sys.executable, '-B', PACKAGE / 'scripts/native_operations.py', 'storage', action, *(['--request', path] if path else []), *extra], expected)

    def row(self, path, kind='preserve'):
        return dict(path=path, **{'class': kind}, owner='B', consumers=[], reason='synthetic explicit original role', origin='combined fixture', regeneration=pin(self.enrollment) if kind == 'recreatable' else None, next_use_or_recheck='after exact fake consumer settlement')

    def classify(self, rows, phase='reserve', expected=0):
        request = save(self.base / 'classify.json', dict(schema='company-native-storage-classification/v1', enrollment=pin(self.enrollment), expect_manifest_sha256=digest(self.run / rc.MANIFEST), phase=phase, artifacts=rows))
        return self.cli('classify', request, expected)

    def launch(self, expected=0):
        return self.command([sys.executable, '-B', PACKAGE / 'scripts/routing_launch.py', *self.args], expected)

    def settle(self, expected=0):
        request = save(self.base / 'settle.json', dict(schema='company-native-storage-launch-settlement/v1', enrollment=pin(self.enrollment), result='result.json', expect_result_sha256=digest(self.run / 'result.json'), orca=str(self.host)))
        return self.cli('settle-launch', request, expected)

    def launch_rows(self):
        m = json.loads((self.run / rc.MANIFEST).read_bytes())
        return [{k: v for k, v in r.items() if k != 'state'} for r in m['creation_contract'].values() if r['origin'] == 'routing_launch.py']

    def complete(self):
        from test_run_completion import ordinary_routing
        record = self.record
        record.update(label='real', resource_accounting='required', routing_accounting='required')
        record['goal'].update(status='succeeded', known_failure=False)
        record['goal']['assessment'].update(verdict='succeeded')
        record['evidence']['assessment'].update(kind='independent', file='acceptance.json', sha256=digest(self.run / 'acceptance.json'))
        record['evidence']['result'].update(file='result.json', sha256=digest(self.run / 'result.json'))
        record['evidence']['route-ev'] = dict(ref='synthetic://routing-original', file='decision.json', sha256=digest(self.run / 'decision.json'), kind='host')
        record['evidence']['receipt-ev'] = dict(ref='synthetic://launch-original', file='launch-receipt.json', sha256=digest(self.run / 'launch-receipt.json'), kind='host')
        for task in record['tasks']:
            task['routing_decision'] = ordinary_routing()
            task['routing_decision']['selected'].update({k: self.packet['selected'][k] for k in ('route', 'family', 'model', 'effort')})
            task['routing_decision']['alternatives'][0].update({k: self.packet['selected'][k] for k in ('route', 'family', 'model', 'effort')})
            task['resource_preflight'] = dict(host='synthetic fake host', cpu='1', ram='fixture', disk='fixture', evidence='result')
            task['resources'] = []
        record['artifact_retention'] = dict(run_id='goal-1', manifest_sha256=digest(self.run / rc.MANIFEST), consumers=[], quiescent=True)
        save(self.run / 'record.json', record)
        request = save(self.base / 'storage.json', dict(schema='company-native-storage-request/v1', roots=[dict(path=str(self.run), kind='company-run', run_id='goal-1', owner='B')], sejong_home=str(self.home), record='record.json', expect_manifest_sha256=digest(self.run / rc.MANIFEST)))
        plan = self.cli('plan', request)
        assert plan['ready'], plan
        path = save(self.base / 'plan.json', plan)
        self.cli('apply', extra=['--plan', path, '--expect-plan-sha256', digest(path)])
        request = save(self.base / 'closeout.json', dict(schema='company-native-storage-closeout-request/v1', enrollment=pin(self.enrollment), sejong_home=str(self.home), session_id='synthetic-combined', cwd=str(self.cwd), run=str(self.run), run_id='goal-1', owner='B', record='record.json', trigger=None))
        before = tree(self.run)
        result = self.cli('closeout', request)
        assert tree(self.run) == before, 'closeout wrote state'
        assert (result['status'], result['removed_files'], result['removed_logical_bytes']) == ('removed', 1, 15), result
        for name, original in self.originals.items():
            assert (digest(self.run / name), rc.signature((self.run / name).stat())) == original, name
        assert not (self.run / 'scratch/raw').exists()
        assert not (self.run / 'result.json.lock').exists()
        save(self.base / 'observation.json', dict(evidence_class='synthetic public CLI; no real worker/model/consent', module_origins=dict(storage=storage.__file__, completion=rc.__file__), commands=self.observations, closeout=result, retained_originals=self.originals))
        (self.base / 'ordinary-final-line.txt').write_text(result['final_summary'] + '\n')
        return result


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(self.enterContext(tempfile.TemporaryDirectory(prefix='company-coordination-test-')))

    def paused_launcher(self, fixture, phase):
        """Pause a real process at a persistence boundary, never a timed sleep."""
        import select
        ready_r, ready_w = os.pipe(); release_r, release_w = os.pipe()
        script = fixture.base / 'paused-launch.py'
        script.write_text('import os,sys\nsys.path.insert(0,' + repr(str(PACKAGE / 'scripts')) + ')\nimport routing_launch as launch\nphase=sys.argv[1]; ready=int(sys.argv[2]); release=int(sys.argv[3])\noriginal=launch.atomic_state\ndef barrier():\n os.write(ready,b"ready"); os.read(release,1)\ndef atomic(path,value,*args,**kwargs):\n state=value.get("launch_state")\n if (phase=="before_pending" and state=="invocation_pending") or (phase=="after_host" and state=="observed"): barrier()\n result=original(path,value,*args,**kwargs)\n if (phase=="after_pending" and state=="invocation_pending") or (phase=="after_publication" and state=="observed"): barrier()\n return result\nlaunch.atomic_state=atomic\nif phase=="before_validation": barrier()\nsys.exit(launch.main(sys.argv[4:]))\n')
        p = subprocess.Popen([sys.executable, '-B', str(script), phase, str(ready_w), str(release_r), *fixture.args], env=fixture.env, cwd=fixture.cwd, pass_fds=(ready_w, release_r), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        os.close(ready_w); os.close(release_r)
        try:
            self.assertTrue(select.select([ready_r], [], [], 15)[0], 'barrier not reached')
            self.assertEqual(os.read(ready_r, 5), b'ready')
        except BaseException:
            os.killpg(p.pid, signal.SIGKILL); p.communicate(timeout=10)
            raise
        finally: os.close(ready_r)
        return p, release_w

    def test_R01_two_processes_held_start_and_freeze_complete_stop_contenders(self):
        import select
        import completion_hook
        f = CombinedFixture(self.base)
        os.mkfifo(f.base / 'host-ready'); os.mkfifo(f.base / 'host-release')
        ready = os.open(f.base / 'host-ready', os.O_RDONLY | os.O_NONBLOCK)
        release = os.open(f.base / 'host-release', os.O_RDWR | os.O_NONBLOCK)
        p = subprocess.Popen([sys.executable, '-B', str(PACKAGE / 'scripts/routing_launch.py'), *f.args], env=f.env, cwd=f.cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            self.assertTrue(select.select([ready], [], [], 15)[0], 'host start barrier missing')
            self.assertEqual(os.read(ready, 64), b'ready\n')
            f.launch(1)
            frozen_before = (f.run / rc.MANIFEST).read_bytes()
            f.classify(f.launch_rows(), 'freeze', 1)
            self.assertEqual((f.run / rc.MANIFEST).read_bytes(), frozen_before)
            f.command([sys.executable, '-B', PACKAGE / 'scripts/run_completion.py', 'complete', '--sejong-home', f.home, '--run', f.run, '--record', 'record.json', '--expect-manifest-sha256', digest(f.run / rc.MANIFEST)], 1)
            stopped = completion_hook.dispatch(dict(hook_event_name='Stop', session_id='synthetic-combined', cwd=str(f.cwd)), f.home)
            self.assertEqual(stopped['status'], 'blocked')
            self.assertFalse((f.run / rc.HOOK_RECEIPT).exists())
            os.write(release, b'x')
            stdout, stderr = p.communicate(timeout=15)
            self.assertEqual(p.returncode, 0, (stdout, stderr))
            self.assertEqual((f.base / 'starts').read_text().splitlines(), ['start'])
            self.assertFalse((f.run / rc.REJECTION).exists())
        finally:
            os.close(ready); os.close(release)
            if p.poll() is None: os.killpg(p.pid, signal.SIGKILL); p.communicate(timeout=10)

    def test_R02_kill_at_four_durable_boundaries_and_no_renamed_retry(self):
        for phase in ('before_pending', 'after_pending', 'after_host', 'after_publication'):
            with self.subTest(phase=phase):
                base = self.base / phase; base.mkdir()
                f = CombinedFixture(base)
                p, release = self.paused_launcher(f, phase)
                os.killpg(p.pid, signal.SIGKILL); p.communicate(timeout=10); os.close(release)
                raw = (f.run / 'result.json').read_bytes()
                receipt = (f.run / 'launch-receipt.json').read_bytes()
                starts = (f.base / 'starts').read_bytes() if (f.base / 'starts').exists() else None
                f.launch(1)
                self.assertEqual((f.run / 'result.json').read_bytes(), raw)
                self.assertEqual((f.run / 'launch-receipt.json').read_bytes(), receipt)
                self.assertEqual((f.base / 'starts').read_bytes() if (f.base / 'starts').exists() else None, starts)
                f.args[f.args.index('--result') + 1] = str(f.run / 'renamed-result.json')
                f.args[f.args.index('--receipt') + 1] = str(f.run / 'new-operation-receipt.json')
                f.launch(1)
                self.assertEqual((f.base / 'starts').read_bytes() if (f.base / 'starts').exists() else None, starts)
                f.classify(f.launch_rows(), 'freeze', 1)

    def test_R02_pre_validation_kill_has_no_start_and_explicit_retry_is_once(self):
        f = CombinedFixture(self.base)
        p, release = self.paused_launcher(f, 'before_validation')
        os.killpg(p.pid, signal.SIGKILL); p.communicate(timeout=10); os.close(release)
        self.assertFalse((f.run / 'result.json').exists())
        f.launch()
        self.assertEqual((f.base / 'starts').read_text().splitlines(), ['start'])

    def test_R03_accepted_record_cannot_be_overwritten_by_preopened_waiter(self):
        f = CombinedFixture(self.base)
        fd = os.open(f.run / rc.LOCK, os.O_RDWR | os.O_NOFOLLOW)
        self.addCleanup(os.close, fd)
        value = copy.deepcopy(f.record)
        value['goal']['status'] = 'succeeded'
        save(f.run / 'record.json', value)
        original = tree(f.run)
        f.launch(1)
        self.assertEqual(tree(f.run), original)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)

    def test_R01_measured_distinct_results_and_close_contender_share_one_lock(self):
        from test_measurement_lifecycle import LifecycleTests
        from types import SimpleNamespace
        c = LifecycleTests('test_replay_with_different_result_path_is_rejected')
        c.setUp(); self.addCleanup(c.doCleanups); c.prepare()
        fixture = SimpleNamespace(base=self.base, cwd=self.base, env=c.env, args=c.launch_args('B'))
        p, release = self.paused_launcher(fixture, 'after_pending')
        try:
            c.launch('B', 1, '-contender')
            c.lifecycle('close', ['--attempt', 'B'], 1)
            os.write(release, b'x')
            stdout, stderr = p.communicate(timeout=20)
            self.assertEqual(p.returncode, 0, (stdout, stderr))
            c.launch('B', 1, '-renamed-after-observation')
            self.assertEqual((c.base / 'starts').read_text().splitlines(), ['B'])
            self.assertFalse((c.root / '.lock').exists())
        finally:
            os.close(release)
            if p.poll() is None: os.killpg(p.pid, signal.SIGKILL); p.communicate(timeout=10)

    def test_R02_measured_pending_kill_blocks_changed_operation_and_actor(self):
        from test_measurement_lifecycle import LifecycleTests
        from types import SimpleNamespace
        c = LifecycleTests('test_unknown_start_blocks_all_new_work')
        c.setUp(); self.addCleanup(c.doCleanups); c.prepare()
        fixture = SimpleNamespace(base=self.base, cwd=self.base, env=c.env, args=c.launch_args('B'))
        p, release = self.paused_launcher(fixture, 'after_pending')
        os.killpg(p.pid, signal.SIGKILL); p.communicate(timeout=10); os.close(release)
        pending = (c.base / 'result-B').read_bytes()
        c.launch('B', 1, '-different-operation'); c.launch('worker', 1)
        self.assertFalse((c.base / 'starts').exists())
        self.assertEqual((c.base / 'result-B').read_bytes(), pending)

    def test_R07_not_started_terminal_absence_is_explicit_and_cannot_reappear(self):
        f = CombinedFixture(self.base)
        f.args[f.args.index('--orca') + 1] = str(f.base / 'nonexistent-fake-host')
        f.launch(1)
        rows = f.launch_rows()
        f.classify(rows, 'freeze', 1)
        absent = [r for r in rows if r['path'] == 'launch-receipt.json']
        f.classify(absent, 'absent')
        self.assertFalse((f.run / 'launch-receipt.json').exists())
        f.classify([r for r in rows if r['path'] == 'result.json'], 'freeze')
        manifest = json.loads((f.run / rc.MANIFEST).read_bytes())
        self.assertEqual(manifest['creation_contract']['launch-receipt.json']['state'], 'absent')
        (f.run / 'launch-receipt.json').write_bytes(b'reappeared later producer')
        with self.assertRaisesRegex(ValueError, 'terminal absence reappeared'):
            rc.validate_acceptance(f.record, f.run / 'record.json', manifest, digest(f.run / rc.MANIFEST))

    def test_R02_kill_during_actual_fake_start_keeps_pending_and_one_start(self):
        import select
        f = CombinedFixture(self.base)
        os.mkfifo(f.base / 'host-ready'); os.mkfifo(f.base / 'host-release')
        ready = os.open(f.base / 'host-ready', os.O_RDONLY | os.O_NONBLOCK)
        release = os.open(f.base / 'host-release', os.O_RDWR | os.O_NONBLOCK)
        p = subprocess.Popen([sys.executable, '-B', str(PACKAGE / 'scripts/routing_launch.py'), *f.args], env=f.env, cwd=f.cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            self.assertTrue(select.select([ready], [], [], 15)[0]); self.assertEqual(os.read(ready, 64), b'ready\n')
            os.killpg(p.pid, signal.SIGKILL); p.communicate(timeout=10)
            pending = (f.run / 'result.json').read_bytes()
            f.launch(1)
            self.assertEqual((f.run / 'result.json').read_bytes(), pending)
            self.assertEqual((f.base / 'starts').read_text().splitlines(), ['start'])
            f.classify(f.launch_rows(), 'freeze', 1)
        finally:
            os.close(ready); os.close(release)
            if p.poll() is None: os.killpg(p.pid, signal.SIGKILL); p.communicate(timeout=10)

    def test_legacy_receipt_reads_allocate_nothing_and_accepted_writes_still_deny(self):
        from test_measurement_lifecycle import LifecycleTests
        import measurement_lifecycle as measurement
        c = LifecycleTests('test_legacy_v2_receipt_remains_readable_without_rewrite')
        c.setUp(); self.addCleanup(c.doCleanups)
        result = c.finish()
        result['receipt']['value'] = {k: result['receipt']['value'][k] for k in ('prepare_sha256', 'responses', 'raw_total')}
        event = c.root / ('event-%06d.json' % result['receipt']['sequence'])
        event.write_bytes(measurement.encoded(result['receipt']))
        c.record['measurement']['settlement_sha256'] = digest(event); c.save()
        # This retained legacy resource is readable, not waived for deletion.
        (c.root / '.lock').touch(mode=0o600)
        before = {str(p.relative_to(c.base)): (digest(p), rc.signature(p.stat())) for p in c.base.rglob('*') if p.is_file()}
        self.assertEqual(c.lifecycle('finalize')['receipt'], result['receipt'])
        with self.assertRaisesRegex(ValueError, 'accepted record freezes classification'):
            measurement.append(c.root, 'halt', {'reason': 'must not mutate accepted history'})
        after = {str(p.relative_to(c.base)): (digest(p), rc.signature(p.stat())) for p in c.base.rglob('*') if p.is_file()}
        self.assertEqual(after, before)

    def test_R04_one_public_cli_chain_retains_originals(self):
        f = CombinedFixture(self.base)
        f.launch(); f.launch(1)
        self.assertEqual((f.base / 'starts').read_text().splitlines(), ['start'])
        f.classify(f.launch_rows(), 'freeze', 1)
        f.settle(); f.classify(f.launch_rows(), 'freeze')
        f.complete()

    def test_R03_existing_descriptor_contender_and_no_nested_lock(self):
        f = CombinedFixture(self.base)
        fd = os.open(f.run / rc.LOCK, os.O_RDWR | os.O_NOFOLLOW)
        self.addCleanup(os.close, fd)
        with rc.lifecycle_lock(f.home, f.run) as cap:
            self.assertEqual(os.fstat(fd).st_ino, os.fstat(cap.lock).st_ino)
            with self.assertRaises(BlockingIOError): fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            f.launch(1)
            row = f.row('nested-borrow')
            storage.classify_value(dict(enrollment=pin(f.enrollment), expect_manifest_sha256=digest(f.run / rc.MANIFEST), phase='reserve', artifacts=[row]), f.base, pin(f.enrollment), cap)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        self.assertFalse((f.base / 'starts').exists())

    def test_R05_live_exit_unknown_and_old_locks_are_not_terminal(self):
        f = CombinedFixture(self.base)
        f.launch(); (f.base / 'live').touch()
        before = (f.run / 'result.json').read_bytes()
        f.settle(1); f.classify(f.launch_rows(), 'freeze', 1)
        self.assertEqual((f.run / 'result.json').read_bytes(), before)
        (f.base / 'live').unlink()
        for index, name in enumerate(('result.json.lock', '.pin', '.keep', '.active', 'foreign.pid')):
            base = self.base / ('marker-' + str(index)); base.mkdir()
            case = CombinedFixture(base); case.launch(); case.settle()
            p = case.run / name; p.write_text('retained old owner resource')
            original = (p.read_bytes(), rc.signature(p.stat()))
            rejected = case.classify(case.launch_rows(), 'freeze', 1)
            self.assertIn('pin/activity marker', json.dumps(rejected))
            self.assertEqual((p.read_bytes(), rc.signature(p.stat())), original)
            # No product or test step settles/removes an old lock; fixture owner
            # retains it until its owned temporary namespace is torn down.

    def test_R06_lock_replacement_and_nested_same_basename_block(self):
        f = CombinedFixture(self.base)
        with rc.lifecycle_lock(f.home, f.run) as cap:
            old = f.run / 'fixture-retained-old-lock'
            (f.run / rc.LOCK).rename(old)
            (f.run / rc.LOCK).write_bytes(b'')
            (f.run / rc.LOCK).chmod(0o600)
            with self.assertRaisesRegex(ValueError, 'moved/replaced'): cap.verify()
            # Restore namespace only inside the destructive fixture for context exit.
            (f.run / rc.LOCK).unlink(); old.rename(f.run / rc.LOCK)
        nested = f.run / 'scratch' / rc.LOCK; nested.write_bytes(b'')
        fd = os.open(f.run, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with self.assertRaisesRegex(ValueError, 'pin/activity'): rc.pins(fd, 'scratch/raw')
        finally: os.close(fd)


if __name__ == '__main__':
    unittest.main()
