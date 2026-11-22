"""Maintenance safety probes: only owned synthetic historical roots/authority."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import native_maintenance as maintenance
import run_completion as rc
from native_operations import Blocked
from test_native_operations import pin, digest, save, tree
from test_storage_lifecycle import MaintenanceStorageTests

PACKAGE = Path(__file__).resolve().parents[1]


class MaintenanceSafetyTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(self.enterContext(tempfile.TemporaryDirectory(prefix='company-maintenance-safety-')))

    def fixture(self, name='fixture', second=False):
        base = self.base / name; base.mkdir()
        c = MaintenanceStorageTests('test_apply_uses_common_engine_and_verifies_external_receipts')
        c.root = base
        c.env = {k: os.environ[k] for k in ('PATH', 'TMPDIR') if k in os.environ}
        c.env.update(HOME=str(base), CODEX_HOME=str(base / 'codex'), PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', UV_OFFLINE='1', UV_PYTHON_DOWNLOADS='never')
        root, request, plan, auth, review, av, rv = c.legacy_fixture()
        if second:
            extra = root / 'generated-two'; extra.write_bytes(b'other disposable fixture')
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try: binding = rc.snapshot_file(fd, extra.name)
            finally: os.close(fd)
            value = json.loads(request.read_bytes())
            first = value['targets'][0]
            value['targets'].append({**first, **binding})
            save(request, value)
            save(plan, maintenance.plan(request))
            av.update(plan_sha256=digest(plan), scope=[x['path'] for x in value['targets']])
            rv['plan_sha256'] = digest(plan)
            save(auth, av); save(review, rv)
        return c, root, request, plan, auth, review, av, rv

    def reauthorize_new_id(self, request, plan, auth, review, av, rv):
        value = json.loads(request.read_bytes()); value['operation_id'] = 'synthetic-different-operation'
        save(request, value); save(plan, maintenance.plan(request))
        self.assertTrue(json.loads(plan.read_bytes())['ready'])
        for path, doc in ((auth, av), (review, rv)):
            doc.update(operation_id=value['operation_id'], plan_sha256=digest(plan)); save(path, doc)

    def test_missing_stable_root_coordination_does_not_create_old_metadata(self):
        c, root, request, plan, auth, review, av, rv = self.fixture()
        (root / rc.LOCK).unlink()  # fixture models a genuinely absent historical lock
        save(plan, maintenance.plan(request))
        av['plan_sha256'] = rv['plan_sha256'] = digest(plan)
        save(auth, av); save(review, rv)
        before = tree(root)
        with self.assertRaisesRegex(Blocked, 'No such file'):
            maintenance.apply(plan, digest(plan), auth, review)
        self.assertEqual(tree(root), before)
        self.assertFalse((root / rc.LOCK).exists())

    def test_reopened_root_compares_saved_identity_before_actions(self):
        c, root, request, plan, auth, review, av, rv = self.fixture()
        original = tree(root); moved = root.with_name('old-retained-namespace')
        lock_context = rc.lifecycle_lock
        def replaced(home, path, **kwargs):
            root.rename(moved); root.mkdir(); (root / rc.LOCK).touch(mode=0o600)
            (root / 'outside-sentinel').write_bytes(b'not authorized')
            return lock_context(home, path, **kwargs)
        with patch.object(rc, 'lifecycle_lock', side_effect=replaced):
            with self.assertRaisesRegex(Blocked, 'reopened maintenance root differs'):
                maintenance.apply(plan, digest(plan), auth, review)
        self.assertEqual(tree(moved), original)
        self.assertEqual((root / 'outside-sentinel').read_bytes(), b'not authorized')
        self.assertFalse((root / rc.RECEIPT).exists())

    def test_sink_replacement_after_intent_is_not_a_successful_path_receipt(self):
        c, root, request, plan, auth, review, av, rv = self.fixture()
        before = tree(root)
        saved = json.loads(plan.read_bytes())
        bundle = maintenance.operation_bundle(saved['request'], saved['root_identity'])
        detached = bundle.with_name(bundle.name + '-retained-original')
        original_write = rc.write_metadata
        fired = []
        def write(fd, name, value):
            result = original_write(fd, name, value)
            if name == rc.RECEIPT and not fired:
                fired.append(True); bundle.rename(detached); bundle.mkdir(mode=0o700)
                (bundle / 'unrelated').write_bytes(b'replacement namespace')
            return result
        with patch.object(rc, 'write_metadata', side_effect=write):
            result = maintenance.apply(plan, digest(plan), auth, review)
        self.assertEqual(result['status'], 'blocked', result)
        self.assertIsNone(result['receipt'])
        self.assertEqual(tree(root), before)
        self.assertEqual(set(p.name for p in bundle.iterdir()), {'unrelated'})
        self.assertTrue((detached / rc.RECEIPT).exists())

    def crash(self, c, root, plan, auth, review, phase):
        script = c.root / 'maintenance-crash.py'
        script.write_text('import os,sys\nsys.path.insert(0,' + repr(str(PACKAGE / 'scripts')) + ')\nimport native_maintenance as m,run_completion as r\nphase=sys.argv[1]\nwrite=r.write_metadata; rename=os.rename; unlink=os.unlink\ndef interrupted(fd,name,value):\n if name==r.RECEIPT and phase=="before_intent": os._exit(71)\n answer=write(fd,name,value)\n if name==r.RECEIPT and ((phase=="after_pending" and "pending" in value) or (phase=="after_final_sync" and value.get("status")=="completed") or (phase=="after_first_prefix" and len(value.get("removed",[]))==1 and "pending" not in value)): os._exit(71)\n return answer\ndef renamed(src,dst,*args,**kwargs):\n answer=rename(src,dst,*args,**kwargs)\n if phase=="after_rename" and src=="generated": os._exit(71)\n return answer\ndef unlinked(path,*args,**kwargs):\n answer=unlink(path,*args,**kwargs)\n if phase=="after_unlink" and str(path).startswith(".completion-quarantine-"): os._exit(71)\n return answer\nr.write_metadata=interrupted;os.rename=renamed;os.unlink=unlinked\nm.apply(sys.argv[2],sys.argv[3],sys.argv[4],sys.argv[5])\n')
        p = subprocess.run([sys.executable, '-B', str(script), phase, str(plan), digest(plan), str(auth), str(review)], cwd=c.root, env=c.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 71, (phase, p.stdout, p.stderr))

    def test_real_process_crash_pending_prefix_and_no_new_operation_retry(self):
        for phase in ('before_intent', 'after_rename', 'after_pending', 'after_unlink', 'after_first_prefix', 'after_final_sync'):
            with self.subTest(phase=phase):
                c, root, request, plan, auth, review, av, rv = self.fixture(phase, second=True)
                historical = ((root / 'old-status.json').read_bytes(), rc.signature((root / 'old-status.json').stat()))
                saved = json.loads(plan.read_bytes())
                bundle = maintenance.operation_bundle(saved['request'], saved['root_identity'])
                self.crash(c, root, plan, auth, review, phase)
                self.assertEqual(((root / 'old-status.json').read_bytes(), rc.signature((root / 'old-status.json').stat())), historical)
                receipt = bundle / rc.RECEIPT
                if phase != 'before_intent':
                    data = json.loads(receipt.read_bytes())
                    if phase in ('after_pending', 'after_unlink'): self.assertIn('pending', data)
                    if phase == 'after_first_prefix': self.assertEqual([x['path'] for x in data['removed']], ['generated'])
                    if phase == 'after_final_sync': self.assertEqual(len(data['removed']), 2)
                before = tree(root); sink_before = tree(bundle)
                with self.assertRaises(Blocked): maintenance.apply(plan, digest(plan), auth, review)
                self.assertEqual(tree(root), before); self.assertEqual(tree(bundle), sink_before)
                if phase == 'before_intent':
                    self.reauthorize_new_id(request, plan, auth, review, av, rv)
                    with self.assertRaises(Blocked): maintenance.apply(plan, digest(plan), auth, review)
                    self.assertEqual(tree(root), before); self.assertEqual(tree(bundle), sink_before)

    def test_partial_prefix_reappearance_new_id_and_authority_revocation(self):
        c, root, request, plan, auth, review, av, rv = self.fixture(second=True)
        original = rc.write_metadata
        def revoke(fd, name, value):
            result = original(fd, name, value)
            if name == rc.RECEIPT and len(value.get('removed', [])) == 1:
                av['valid_until'] = '2001-01-01T00:00:00+00:00'; save(auth, av)
            return result
        with patch.object(rc, 'write_metadata', side_effect=revoke):
            result = maintenance.apply(plan, digest(plan), auth, review)
        self.assertEqual(result['status'], 'blocked', result)
        self.assertEqual([x['path'] for x in result['removed']], ['generated'])
        self.assertTrue((root / 'generated-two').exists())
        (root / 'generated').write_bytes(b'reappeared new owner bytes')
        before = tree(root)
        with self.assertRaises(Blocked): maintenance.apply(plan, digest(plan), auth, review)
        self.assertEqual(tree(root), before)

    def test_real_holder_blocks_normal_and_maintenance_without_receipt_writes(self):
        import select
        c, root, request, plan, auth, review, av, rv = self.fixture()
        ready_r, ready_w = os.pipe(); release_r, release_w = os.pipe()
        code = 'import os,sys;sys.path.insert(0,' + repr(str(PACKAGE / 'scripts')) + ');import run_completion as r;from pathlib import Path\nwith r.lifecycle_lock(Path(sys.argv[1]),Path(sys.argv[2])):\n os.write(int(sys.argv[3]),b"held");os.read(int(sys.argv[4]),1)'
        p = subprocess.Popen([sys.executable, '-B', '-c', code, str(root.parents[1]), str(root), str(ready_w), str(release_r)], env=c.env, pass_fds=(ready_w, release_r), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.close(ready_w); os.close(release_r)
        try:
            self.assertTrue(select.select([ready_r], [], [], 10)[0]); self.assertEqual(os.read(ready_r, 4), b'held')
            before = tree(root)
            with self.assertRaises(Blocked): maintenance.apply(plan, digest(plan), auth, review)
            for action in ('init', 'register', 'complete'):
                args = [sys.executable, '-B', str(PACKAGE / 'scripts/run_completion.py'), action, '--run', str(root), '--sejong-home', str(root.parents[1])]
                r = subprocess.run(args, env=c.env, capture_output=True, text=True, timeout=10)
                self.assertEqual(r.returncode, 1, (r.stdout, r.stderr))
            self.assertEqual(tree(root), before)
            os.write(release_w, b'x'); p.communicate(timeout=10)
            self.assertEqual(p.returncode, 0)
        finally:
            os.close(ready_r); os.close(release_w)
            if p.poll() is None: p.kill(); p.communicate(timeout=10)


if __name__ == '__main__':
    unittest.main()
