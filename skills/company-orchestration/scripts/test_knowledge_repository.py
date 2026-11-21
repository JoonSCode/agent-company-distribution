#!/usr/bin/env python3
"""Local fixtures only; preserve the live private knowledge repository."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import sys

import knowledge_repository as repository
import research_cache as cache
from test_research_cache import sample


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp", prefix="knowledge-repository-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "research"
        self.store = cache.Store(self.root, True)
        self.original = self.store.put(sample())

    def inventory_bytes(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*")
                if p.is_file() and not set(p.parts) & {".git", repository.SEED_JOURNALS, repository.GIT_STAGE}
                and p.name not in ("lock", repository.RECEIPT, repository.INIT_RECEIPT)}

    def test_migration_is_in_place_idempotent_and_preserves_originals(self):
        original = self.inventory_bytes()
        planned = repository.plan(self.store)
        self.assertFalse((self.root / ".git").exists())
        applied = repository.apply(self.store, planned, planned["plan_sha256"])
        self.assertEqual(applied["files_rewritten"], 0)
        self.assertEqual(self.inventory_bytes(), original)
        self.assertEqual(repository.apply(self.store, planned, planned["plan_sha256"])["status"], "already_applied")
        result = repository.snapshot(self.store, planned, planned["plan_sha256"], "fixture owner", "First curated snapshot")
        self.assertEqual(result["status"], "committed")
        self.assertEqual(repository.snapshot(self.store, planned, planned["plan_sha256"], "fixture owner", "Repeat")["status"], "unchanged")
        self.assertEqual(repository._git(self.root, "remote"), "")
        self.assertEqual(self.inventory_bytes(), original)

    def test_conflicts_and_history_are_preserved_and_committed(self):
        self.store.update("method-note", sample(synthesis="New verified result"), self.original["content_sha256"])
        try:
            self.store.update("method-note", sample(synthesis="Divergent peer result"), self.original["content_sha256"])
        except cache.CacheError:
            pass
        original = self.inventory_bytes()
        plan = repository.plan(self.store)
        repository.apply(self.store, plan, plan["plan_sha256"])
        repository.snapshot(self.store, plan, plan["plan_sha256"], "fixture", "Keep both sides")
        tracked = repository._git(self.root, "ls-files").splitlines()
        self.assertTrue(any(name.startswith("conflicts/") for name in tracked))
        self.assertTrue(any(name.startswith("history/") for name in tracked))
        self.assertEqual(original, self.inventory_bytes())

    def test_stale_or_tampered_plan_cannot_initialize_git(self):
        planned = repository.plan(self.store)
        self.store.put(sample(id="peer-note"))
        with self.assertRaises(cache.CacheError) as caught:
            repository.apply(self.store, planned, planned["plan_sha256"])
        self.assertEqual(caught.exception.code, "migration_conflict")
        self.assertFalse((self.root / ".git").exists())
        planned["excluded"].append("tampered")
        with self.assertRaises(cache.CacheError) as caught:
            repository.apply(self.store, planned, planned["plan_sha256"])
        self.assertEqual(caught.exception.code, "plan_conflict")

    def test_unknown_large_artifacts_and_symlinks_are_never_loaded_or_staged(self):
        (self.root / "video.mp4").write_bytes(b"x" * (cache.MAX_BYTES + 1))
        (self.root / "transcript.jsonl").write_text("private raw transcript")
        (self.root / "unrelated-link").symlink_to(Path(self.temp.name) / "absent")
        planned = repository.plan(self.store)
        self.assertEqual(planned["excluded"], ["transcript.jsonl", "unrelated-link", "video.mp4"])
        repository.apply(self.store, planned, planned["plan_sha256"])
        repository.snapshot(self.store, planned, planned["plan_sha256"], "fixture", "Curated only")
        self.assertFalse(set(planned["excluded"]) & set(repository._git(self.root, "ls-files").splitlines()))
        self.assertNotIn("lock", repository._git(self.root, "ls-files").splitlines())

    def test_secret_shaped_legacy_notes_block_git_without_changing_evidence(self):
        self.store.put(sample(id="credential-note", synthesis="sk-" + "A" * 24))
        original = self.inventory_bytes()
        with self.assertRaises(cache.CacheError) as caught:
            repository.plan(self.store)
        self.assertEqual(caught.exception.code, "secret_detected")
        self.assertFalse((self.root / ".git").exists())
        self.assertEqual(original, self.inventory_bytes())

    def test_oversized_curated_record_and_git_attributes_are_rejected(self):
        planned = repository.plan(self.store)
        record_path = self.root / "records/method-note.json"
        record_path.write_bytes(b"x" * (cache.MAX_BYTES + 1))
        with self.assertRaises(cache.CacheError):
            repository.apply(self.store, planned, planned["plan_sha256"])
        self.assertFalse((self.root / ".git").exists())
        # New isolated fixture for attributes, without restoring arbitrary bytes.
        root = Path(self.temp.name) / "attributes-cache"
        store = cache.Store(root, True)
        (root / ".gitattributes").write_text("* filter=unreviewed\n")
        with self.assertRaises(cache.CacheError) as caught:
            repository.plan(store)
        self.assertEqual(caught.exception.code, "git_boundary")

    def test_prestaged_transaction_and_unknown_tracked_file_remain_with_owner(self):
        planned = repository.plan(self.store)
        repository.apply(self.store, planned, planned["plan_sha256"])
        repository._git(self.root, "add", "index.json")
        with self.assertRaises(cache.CacheError) as caught:
            repository.snapshot(self.store, planned, planned["plan_sha256"], "fixture", "Must not absorb another commit")
        self.assertEqual(caught.exception.code, "git_busy")
        self.assertEqual(repository._git(self.root, "diff", "--cached", "--name-only"), "index.json")
        unknown = self.root / "private.txt"
        unknown.write_text("unreviewed")
        repository._git(self.root, "add", "private.txt")
        planned = repository.plan(self.store)
        with self.assertRaises(cache.CacheError) as caught:
            repository.snapshot(self.store, planned, planned["plan_sha256"], "fixture", "No add all")
        self.assertEqual(caught.exception.code, "git_boundary")

    def test_snapshot_and_cache_writer_share_lock_without_lost_index(self):
        planned = repository.plan(self.store)
        repository.apply(self.store, planned, planned["plan_sha256"])
        def commit():
            try:
                return repository.snapshot(self.store, planned, planned["plan_sha256"], "fixture", "Concurrent snapshot")["status"]
            except cache.CacheError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            snapshot = pool.submit(commit)
            update = pool.submit(self.store.put, sample(id="concurrent-peer"))
            result, written = snapshot.result(), update.result()
        self.assertIn(result, ("committed", "migration_conflict"))
        self.assertEqual(written["id"], "concurrent-peer")
        self.assertEqual(len(self.store.digest()["records"]), 2)

    def test_git_hook_is_not_executed(self):
        planned = repository.plan(self.store)
        repository.apply(self.store, planned, planned["plan_sha256"])
        marker = Path(self.temp.name) / "hook-ran"
        hook = self.root / ".git/hooks/pre-commit"
        hook.parent.mkdir()
        hook.write_text("#!/bin/sh\ntouch '" + str(marker) + "'\n")
        hook.chmod(0o700)
        repository.snapshot(self.store, planned, planned["plan_sha256"], "fixture", "No hook")
        self.assertFalse(marker.exists())

    def seed_manifest(self):
        source = Path(self.temp.name) / "dated-research.md"
        source.write_text("Original dated research with counterevidence; fixture only.\n")
        record = sample(id="dated-source", format=cache.KNOWLEDGE_FORMAT, synthesis="Curated reference; check date and limits before reuse.",
                        knowledge={"kind": "reference", "claim": "observation", "scope_level": "role",
                                   "applicability": "Task-fit routing evidence", "source_authority": "Dated source record",
                                   "verification": "Not a new benchmark or current model catalog", "tags": ["sourceimport"]})
        return {"format": repository.SEED_FORMAT, "entries": [{"source": {"path": str(source), "sha256": cache._digest(source.read_bytes())}, "record": record}]}

    def test_source_seed_preserves_originals_is_idempotent_and_is_searchable(self):
        manifest = self.seed_manifest()
        planned = repository.seed_plan(self.store, manifest)
        original = Path(manifest["entries"][0]["source"]["path"]).read_bytes()
        result = repository.seed_apply(self.store, planned, planned["plan_sha256"])
        self.assertEqual(result["status"], "seeded")
        self.assertEqual(repository.seed_apply(self.store, planned, planned["plan_sha256"])["status"], "already_seeded")
        archive = self.root / planned["entries"][0]["archive_path"]
        self.assertEqual(archive.read_bytes(), original)
        self.assertEqual(Path(manifest["entries"][0]["source"]["path"]).read_bytes(), original)
        self.assertEqual([row["id"] for row in self.store.search("sourceimport", 5)["matches"]], ["dated-source"])
        migration = repository.plan(self.store)
        self.assertIn(archive.relative_to(self.root).as_posix(), [item["path"] for item in migration["files"]])
        repository.apply(self.store, migration, migration["plan_sha256"])
        repository.snapshot(self.store, migration, migration["plan_sha256"], "fixture", "Research and reference originals")
        self.assertIn(archive.relative_to(self.root).as_posix(), repository._git(self.root, "ls-files").splitlines())

    def test_source_seed_changed_source_and_peer_index_block_before_record_write(self):
        manifest = self.seed_manifest()
        planned = repository.seed_plan(self.store, manifest)
        Path(manifest["entries"][0]["source"]["path"]).write_text("Changed source")
        with self.assertRaises(cache.CacheError) as caught:
            repository.seed_apply(self.store, planned, planned["plan_sha256"])
        self.assertEqual(caught.exception.code, "seed_conflict")
        self.assertFalse((self.root / "origins").exists())
        manifest = self.seed_manifest()
        planned = repository.seed_plan(self.store, manifest)
        self.store.put(sample(id="peer-write"))
        with self.assertRaises(cache.CacheError) as caught:
            repository.seed_apply(self.store, planned, planned["plan_sha256"])
        self.assertEqual(caught.exception.code, "seed_conflict")
        self.assertFalse((self.root / "records/dated-source.json").exists())

    def test_source_seed_retains_divergent_existing_record_and_conflict(self):
        manifest = self.seed_manifest()
        planned = repository.seed_plan(self.store, manifest)
        repository.seed_apply(self.store, planned, planned["plan_sha256"])
        before = self.store._read_record("dated-source")
        semantic = {key: before[key] for key in cache.semantic_fields(before)}
        semantic["synthesis"] = "Local correction to imported reference"
        changed = self.store.update("dated-source", semantic, before["content_sha256"])
        with self.assertRaises(cache.CacheError) as caught:
            repository.seed_apply(self.store, planned, planned["plan_sha256"])
        self.assertEqual(caught.exception.code, "conflict")
        self.assertEqual(self.store._read_record("dated-source"), changed)
        self.assertTrue(list((self.root / "conflicts/dated-source").glob("*.json")))

    def two_entry_seed(self, store):
        manifest = self.seed_manifest()
        second = self.seed_manifest()["entries"][0]
        second["record"]["id"] = "second-source"
        manifest["entries"].append(second)
        return repository.seed_plan(store, manifest)

    def assert_rejected_unchanged(self, store, planned):
        before = {p.relative_to(store.root).as_posix(): p.read_bytes()
                  for p in store.root.rglob("*") if p.is_file() and p.name != "lock"}
        with self.assertRaises(cache.CacheError):
            repository.seed_apply(store, planned, planned["plan_sha256"])
        after = {p.relative_to(store.root).as_posix(): p.read_bytes()
                 for p in store.root.rglob("*") if p.is_file() and p.name != "lock"}
        self.assertEqual(before, after)

    def interrupt_seed(self, store, planned, phase):
        real_write = cache._atomic_write
        def crash(path, data, mode):
            real_write(path, data, mode)
            selected = ((phase == "journal" and path.parent.name == repository.SEED_JOURNALS)
                        or (phase == "archive" and path.parent.name == "origins")
                        or (phase == "json" and path.name == "dated-source.json")
                        or (phase == "markdown" and path.name == "dated-source.md")
                        or (phase == "index" and path.name == "index.json"))
            if selected:
                raise OSError("injected interruption after " + phase)
        with patch.object(cache, "_atomic_write", side_effect=crash), self.assertRaises(OSError):
            repository.seed_apply(store, planned, planned["plan_sha256"])

    def test_seed_replays_owned_missing_outputs_at_each_write_boundary(self):
        for phase in ("journal", "archive", "json", "markdown", "index"):
            with self.subTest(phase=phase):
                store = cache.Store(Path(self.temp.name) / phase, True)
                planned = self.two_entry_seed(store)
                original = Path(planned["entries"][0]["source"]["path"]).read_bytes()
                self.interrupt_seed(store, planned, phase)
                result = repository.seed_apply(store, planned, planned["plan_sha256"])
                self.assertEqual(result["status"], "seeded")
                self.assertEqual(repository.seed_apply(store, planned, planned["plan_sha256"])["status"], "already_seeded")
                self.assertEqual({r["id"] for r in store.search("sourceimport", 5)["matches"]}, {"dated-source", "second-source"})
                for entry in planned["entries"]:
                    self.assertEqual((store.root / entry["archive_path"]).read_bytes(), original)
                    self.assertEqual(Path(entry["source"]["path"]).read_bytes(), original)
                    self.assertEqual(store._read_record(entry["record"]["id"])["revision"], 1)

    def test_seed_before_index_and_between_entries_resume_with_unchanged_plan(self):
        for phase in ("before-index", "between-entries"):
            with self.subTest(phase=phase):
                store = cache.Store(Path(self.temp.name) / phase, True)
                planned = self.two_entry_seed(store)
                insert = store._insert_locked
                def after_insert(record, index):
                    insert(record, index)
                    raise OSError("after complete first insertion")
                target = "_write_index" if phase == "before-index" else "_insert_locked"
                effect = OSError("before index") if phase == "before-index" else after_insert
                with patch.object(store, target, side_effect=effect), self.assertRaises(OSError):
                    repository.seed_apply(store, planned, planned["plan_sha256"])
                repository.seed_apply(store, planned, planned["plan_sha256"])
                self.assertEqual(len(store._mutation_index()), 2)

    def test_seed_recovery_refuses_changed_original_peer_index_and_partial_bytes(self):
        for phase in ("original", "peer-index", "partial", "baseline", "unknown-file", "missing-archive"):
            with self.subTest(phase=phase):
                store = cache.Store(Path(self.temp.name) / phase, True)
                baseline = store.put(sample(id="baseline"))
                planned = self.two_entry_seed(store)
                self.interrupt_seed(store, planned, "index" if phase == "missing-archive" else "json")
                if phase == "original":
                    Path(planned["entries"][0]["source"]["path"]).write_text("Changed reviewed source")
                elif phase == "peer-index":
                    store.put(sample(id="peer-write"))
                elif phase == "partial":
                    (store.root / "records/dated-source.json").write_text("Different writer output")
                elif phase == "baseline":
                    store.update("baseline", sample(id="baseline", synthesis="Peer correction"), baseline["content_sha256"])
                elif phase == "unknown-file":
                    (store.root / "records/unknown.json").write_text("Unowned record")
                else:
                    (store.root / planned["entries"][0]["archive_path"]).unlink()
                self.assert_rejected_unchanged(store, planned)

    def test_seed_without_ownership_journal_cannot_adopt_unindexed_record(self):
        planned = self.two_entry_seed(self.store)
        self.interrupt_seed(self.store, planned, "json")
        (self.root / repository.SEED_JOURNALS / (planned["plan_sha256"] + ".json")).unlink()
        self.assert_rejected_unchanged(self.store, planned)
        fresh = repository.seed_plan(self.store, self.seed_manifest())
        self.assert_rejected_unchanged(self.store, fresh)

    def test_seed_recovery_cli_reuses_exact_reviewed_plan(self):
        planned = self.two_entry_seed(self.store)
        self.interrupt_seed(self.store, planned, "markdown")
        path = Path(self.temp.name) / "seed-plan.json"
        path.write_text(json.dumps(planned))
        result = subprocess.run([sys.executable, "-B", str(Path(repository.__file__)), "--root", str(self.root),
                                 "seed-apply", "--plan", str(path), "--expect-plan-sha256", planned["plan_sha256"]],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "seeded")

    def interrupted_git(self, planned, before_move=False):
        write = cache._atomic_write
        def crash(path, data, mode):
            if path.name == repository.RECEIPT:
                raise OSError("after owned init before receipt")
            write(path, data, mode)
        if before_move:
            with patch.object(repository.os, "rename", side_effect=OSError("before exposing Git")), self.assertRaises(OSError):
                repository.apply(self.store, planned, planned["plan_sha256"])
        else:
            with patch.object(cache, "_atomic_write", side_effect=crash), self.assertRaises(OSError):
                repository.apply(self.store, planned, planned["plan_sha256"])

    def test_git_init_receipt_and_staged_move_interruptions_resume(self):
        planned = repository.plan(self.store)
        originals = self.inventory_bytes()
        self.interrupted_git(planned, before_move=True)
        self.assertFalse((self.root / ".git").exists())
        self.assertEqual(repository.apply(self.store, planned, planned["plan_sha256"])["status"], "applied")
        self.assertEqual(originals, self.inventory_bytes())
        second = cache.Store(Path(self.temp.name) / "second-git", True)
        plan = repository.plan(second)
        write = cache._atomic_write
        def crash(path, data, mode):
            if path.name == repository.RECEIPT:
                raise OSError("before receipt")
            write(path, data, mode)
        with patch.object(cache, "_atomic_write", side_effect=crash), self.assertRaises(OSError):
            repository.apply(second, plan, plan["plan_sha256"])
        before = repository._file_manifest(second.root / ".git")
        self.assertEqual(repository.apply(second, plan, plan["plan_sha256"])["status"], "recovered")
        self.assertEqual(before, repository._file_manifest(second.root / ".git"))
        self.assertEqual(repository._git(second.root, "remote"), "")
        self.assertEqual(repository._git(second.root, "ls-files"), "")

    def test_git_init_recovery_refuses_peer_metadata_and_stale_inventory(self):
        planned = repository.plan(self.store)
        self.interrupted_git(planned)
        (self.root / ".git/config").write_text("[core]\nrepositoryformatversion = 0\nbare = false\n[remote \"peer\"]\nurl = example.test\n")
        before = repository._file_manifest(self.root / ".git")
        with self.assertRaises(cache.CacheError) as caught:
            repository.apply(self.store, planned, planned["plan_sha256"])
        self.assertEqual(caught.exception.code, "recovery_conflict")
        self.assertEqual(before, repository._file_manifest(self.root / ".git"))
        self.assertFalse((self.root / repository.RECEIPT).exists())
        self.store.put(sample(id="peer"))
        with self.assertRaises(cache.CacheError) as caught:
            repository.apply(self.store, planned, planned["plan_sha256"])
        self.assertEqual(caught.exception.code, "migration_conflict")

    def test_git_init_call_before_and_after_interruption_has_prior_owned_evidence(self):
        for phase in ("before", "after"):
            with self.subTest(phase=phase):
                store = cache.Store(Path(self.temp.name) / ("git-call-" + phase), True)
                planned = repository.plan(store)
                git = repository._git
                def interrupt(root, *args):
                    if Path(root).name == repository.GIT_STAGE and args[0] == "init":
                        self.assertTrue((store.root / repository.INIT_RECEIPT).exists())
                        if phase == "after":
                            git(root, *args)
                        raise OSError("interrupted Git init " + phase)
                    return git(root, *args)
                with patch.object(repository, "_git", side_effect=interrupt), self.assertRaises(OSError):
                    repository.apply(store, planned, planned["plan_sha256"])
                self.assertFalse((store.root / ".git").exists())
                self.assertEqual(repository.apply(store, planned, planned["plan_sha256"])["status"], "applied")
                self.assertEqual(repository._git(store.root, "remote"), "")

    def test_unrelated_git_and_unverified_staging_are_preserved_and_refused(self):
        planned = repository.plan(self.store)
        repository._git(self.root, "init", "--initial-branch=knowledge-local", ".")
        before = repository._file_manifest(self.root / ".git")
        with self.assertRaises(cache.CacheError) as caught:
            repository.apply(self.store, planned, planned["plan_sha256"])
        self.assertEqual(caught.exception.code, "recovery_conflict")
        self.assertEqual(before, repository._file_manifest(self.root / ".git"))
        other = cache.Store(Path(self.temp.name) / "unverified", True)
        plan = repository.plan(other)
        stage = other.root / repository.GIT_STAGE
        stage.mkdir()
        repository._git(stage, "init", "--initial-branch=knowledge-local", ".")
        before = repository._file_manifest(stage / ".git")
        with self.assertRaises(cache.CacheError) as caught:
            repository.apply(other, plan, plan["plan_sha256"])
        self.assertEqual(caught.exception.code, "recovery_conflict")
        self.assertEqual(before, repository._file_manifest(stage / ".git"))
        self.assertFalse((other.root / ".git").exists())


if __name__ == "__main__":
    unittest.main()
