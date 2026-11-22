from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class PolicyManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "package"
        shutil.copytree(SOURCE, self.root, ignore=shutil.ignore_patterns("__pycache__"))
        self.baseline = self.root / "references/upstream/baseline.json"
        self.script = self.root / "scripts/policy_manifest.py"

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(self.script), *args, "--package", str(self.root)], capture_output=True, text=True)

    def tree(self):
        return {str(p.relative_to(self.root)): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()}

    def manifest(self):
        return json.loads(self.baseline.read_text())

    def save(self, data):
        self.baseline.write_text(json.dumps(data, indent=2) + "\n")

    def test_default_check_no_writes(self):
        before = self.tree()
        self.assertEqual(self.run_cli().returncode, 0)
        self.assertEqual(before, self.tree())

    def test_drift_diff_check_sync_idempotent_and_consumer(self):
        data = self.manifest()
        item = data['policy_files'][0]
        path = self.root / item['path']
        path.write_bytes(path.read_bytes() + b'\n')
        before = self.tree()
        one, two = self.run_cli(), self.run_cli('check')
        self.assertEqual(one.returncode, 1, one.stderr)
        self.assertEqual(one.stdout, two.stdout)
        self.assertEqual(before, self.tree())
        result = self.run_cli('sync')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split('policy manifest: synced')[0], one.stdout)
        after = self.tree()
        self.assertEqual(self.run_cli('sync').returncode, 0)
        self.assertEqual(after, self.tree())
        consumer = subprocess.run([sys.executable, '-B', str(self.root / 'scripts/orca_contract.py'), 'check', '--package', str(self.root), '--json'], capture_output=True, text=True)
        self.assertEqual(consumer.returncode, 0, consumer.stdout + consumer.stderr)
        self.assertEqual(data['upstream'], self.manifest()['upstream'])

    def test_missing_duplicate_unlisted_and_malformed_deny_without_writes(self):
        data = self.manifest()
        item = next(item for item in data['policy_files'] if item['path'] == 'references/getting-started.md')
        path = self.root / item['path']
        path.unlink()
        before = self.tree()
        result = self.run_cli('sync')
        self.assertEqual(result.returncode, 2)
        self.assertIn('missing', result.stderr)
        self.assertEqual(before, self.tree())
        # Recreate the fixture before exercising independent invalid cases.
        shutil.copy2(SOURCE / item['path'], path)
        data['policy_files'].append(data['policy_files'][0])
        self.save(data)
        self.assertIn('duplicate', self.run_cli('sync').stderr)
        data['policy_files'].pop()
        self.save(data)
        self.assertIn('unlisted', self.run_cli('sync', '--path', 'unlisted.py').stderr)
        self.baseline.write_text('{"policy_files": [], "policy_files": []}')
        self.assertEqual(self.run_cli('sync').returncode, 2)

    def test_symlink_and_outside_deny(self):
        data = self.manifest()
        item = data['policy_files'][0]
        path = self.root / item['path']
        path.unlink()
        path.symlink_to(SOURCE / item['path'])
        self.assertIn('symlink', self.run_cli('sync').stderr)
        item['path'] = '../outside'
        self.save(data)
        self.assertIn('unsafe path', self.run_cli('sync').stderr)

    def test_unbound_markdown_link_denied(self):
        data = self.manifest()
        target = self.root / 'unlisted.md'
        target.write_text('not bound\n')
        skill = self.root / 'SKILL.md'
        skill.write_text(skill.read_text() + '\n[unlisted](unlisted.md)\n')
        result = self.run_cli('sync')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('unbound policy dependency', result.stderr)


if __name__ == '__main__':
    unittest.main()
