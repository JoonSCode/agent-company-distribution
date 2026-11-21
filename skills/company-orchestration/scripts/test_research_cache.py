#!/usr/bin/env python3
"""Behavior tests for the private research cache. No network and no live store."""
from __future__ import annotations

import json
import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import research_cache as cache

SCRIPT = Path(__file__)
TOOL = SCRIPT.with_name("research_cache.py")


def sample(**overrides):
    record = {
        "format": cache.FORMAT,
        "id": "method-note",
        "stability": "stable_concept",
        "topic": "method discovery for unfamiliar product work",
        "problem": "How should a first unfamiliar task choose a method?",
        "query": "method discovery unfamiliar work official source",
        "synthesis": ("alpha " * 80) + "zzuniquebody",
        "provenance": [{
            "url": "https://example.test/source",
            "checked_portion": "method section",
            "checked_on": "2026-10-11",
        }],
        "scope": "first unfamiliar product work",
        "version": "2026-10-11.1",
        "checked_on": "2026-10-11",
        "freshness": {
            "recheck_trigger": "official interface or skill text changes",
            "review_after": "2026-10-18",
            "live_check_still_required": "Re-read the named source if it changes.",
            "live_check_required": False,
        },
        "uncertainty": "Quality and token effect are unmeasured.",
        "counterevidence": "Extra procedure can slow a task that is already decided.",
        "disposition": "adapted",
        "disposition_reason": "Reuse the criteria without copying a quota.",
        "observed_use": None,
        "owner": "research-methods",
        "replaces": None,
    }
    record.update(overrides)
    return record


class ResearchCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp", prefix="research-cache-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "cache"
        self.store = cache.Store(self.root, create=True)

    def put(self, record):
        return self.store.put(record)

    def knowledge(self, **overrides):
        return sample(format=cache.KNOWLEDGE_FORMAT, knowledge={
            "kind": "correction", "claim": "decision", "scope_level": "project",
            "applicability": "Only this product's source changes",
            "source_authority": "User correction in a held local source",
            "verification": "Implementation observation pending", "tags": ["userinterrupt", "retiredmethod"],
        }, **overrides)

    def test_v1_bytes_hash_and_index_match_the_immutable_base(self):
        # Golden values obtained from bf468c5's original Store and sample().
        stored = self.put(sample())
        self.assertEqual(stored["content_sha256"], "79632f268b4f10b4f2fcc9d387601a9c7abc4be93cc6f3103dedbbf31e65b315")
        expected = {
            "records/method-note.json": "85efc26be8f4132c7a875919a75f7a7c44e499a1f8e6b46ed402c8c93a118050",
            "records/method-note.md": "5d0cfb7fc654e651eee03c85f95929ce1887d966f35ea290a2287a7366f94755",
            "index.json": "d63a19b2940e81ac36f5f3e06472339c01df6feae0a648d29e7e835f98ce2f04",
        }
        for path, digest in expected.items():
            self.assertEqual(hashlib.sha256((self.root / path).read_bytes()).hexdigest(), digest)

    def test_v2_metadata_retrieval_is_index_only_and_scope_does_not_expand(self):
        self.put(self.knowledge())
        self.put(sample(id="legacy"))
        with patch.object(self.store, "_read_record", side_effect=AssertionError("search loaded a body")):
            found = self.store.search("userinterrupt", 5, kind="correction", scope_level="project")
        self.assertEqual([r["id"] for r in found["matches"]], ["method-note"])
        self.assertEqual(found["matches"][0]["knowledge"]["claim"], "decision")
        self.assertEqual(found["loaded_record_bodies"], 0)
        assessed = self.store.assess("method-note", "first unfamiliar product work globally", "", "2026-10-11")
        self.assertEqual(assessed["decision"], "scope_mismatch")
        self.assertIn("evidence_only", assessed["authority"])

    def test_exact_cas_legacy_update_refuses_v2_and_retains_rejected_payload(self):
        first = self.put(self.knowledge())
        before = {p: (self.root / p).read_bytes() for p in
                  ("index.json", "records/method-note.json", "records/method-note.md")}
        payload = sample(synthesis="Old caller update")
        path = Path(self.temp.name) / "legacy.json"
        path.write_text(json.dumps(payload))
        result = self._cli("update", "--id", first["id"], "--record", str(path),
                           "--expect-sha256", first["content_sha256"])
        self.assertEqual(result.returncode, 4)
        response = json.loads(result.stdout)
        self.assertEqual(response["error"], "classification_required")
        self.assertIn("submit v2", response["detail"])
        self.assertEqual(before, {p: (self.root / p).read_bytes() for p in before})
        self.assertFalse((self.store.history / first["id"]).exists())
        rejected = list((self.store.conflicts / first["id"]).glob("*.json"))
        self.assertEqual(len(rejected), 1)
        self.assertEqual(json.loads(rejected[0].read_text())["rejected_record"], cache.semantic_of(payload))
        self.assertEqual([r["id"] for r in self.store.search("userinterrupt", 5, kind="correction")["matches"]], [first["id"]])
        legacy = self.put(sample(id="legacy"))
        updated = self.store.update("legacy", sample(id="legacy", synthesis="Legacy caller still works"), legacy["content_sha256"])
        self.assertEqual(updated["format"], cache.FORMAT)
        explicit = self.store.update(first["id"], self.knowledge(synthesis="Explicit classified correction"), first["content_sha256"])
        self.assertEqual(explicit["knowledge"], first["knowledge"])
        self.assertEqual(json.loads((self.store.history / first["id"] / "1.json").read_text()), first)

    def test_v2_use_and_supersession_keep_classification_and_originals(self):
        first = self.put(self.knowledge())
        result = self._cli("use", "--id", first["id"], "--expect-sha256", first["content_sha256"],
                           "--result", "not used: project scope differs", "--observed-on", "2026-10-11", "--limits", "No policy promotion")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        used = json.loads(result.stdout)["record"]
        self.assertEqual(used["knowledge"], first["knowledge"])
        replacement = self.knowledge(id="corrected-method", replaces=first["id"])
        self.store.supersede(first["id"], replacement, used["content_sha256"], "contradicted")
        self.assertEqual(self.store.assess(first["id"], first["scope"], "", "2026-10-11")["decision"], "not_reusable")
        self.assertEqual({r["id"] for r in self.store.search("userinterrupt", 5)["matches"]}, {first["id"], "corrected-method"})
        self.assertEqual(json.loads((self.root / "history/method-note/1.json").read_text()), first)

    def test_v2_rejects_secrets_large_notes_and_unscoped_metadata_before_write(self):
        for record in (self.knowledge(synthesis="sk-" + "A" * 24), self.knowledge(synthesis="x" * (cache.TEXT_LIMIT + 1))):
            before = self._record_bytes()
            with self.assertRaises(cache.CacheError):
                self.put(record)
            self.assertEqual(self._record_bytes(), before)
        record = self.knowledge()
        del record["knowledge"]["source_authority"]
        with self.assertRaises(cache.CacheError):
            self.put(record)

    def test_concurrent_v2_cas_updates_keep_one_winner_and_rejected_body(self):
        first = self.put(self.knowledge())
        barrier = Barrier(2)
        def writer(number):
            barrier.wait(timeout=5)
            try:
                self.store.update(first["id"], self.knowledge(synthesis=f"Result from writer {number}"), first["content_sha256"])
                return "updated"
            except cache.CacheError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(writer, (1, 2)))
        self.assertCountEqual(results, ["updated", "conflict"])
        self.assertEqual(self.store._read_record(first["id"])["revision"], 2)
        self.assertEqual(len(list((self.root / "conflicts/method-note").glob("*.json"))), 1)

    def test_relevant_query_hits_and_unrelated_query_misses(self):
        self.put(sample())
        hit = self.store.search("method discovery unfamiliar", limit=5)
        miss = self.store.search("storekit introductory price", limit=5)
        self.assertEqual(hit["loaded_record_bodies"], 0)
        self.assertEqual([item["id"] for item in hit["matches"]], ["method-note"])
        self.assertEqual(miss["matches"], [])

    def test_search_uses_the_index_excerpt_not_the_record_body(self):
        self.put(sample())
        hidden = self.store.search("zzuniquebody", limit=5)
        visible = self.store.get_record("method-note") if hasattr(self.store, "get_record") else self.store._read_record("method-note")
        self.assertEqual(hidden["matches"], [])
        self.assertIn("zzuniquebody", visible["synthesis"])
        self.assertNotIn("zzuniquebody", self.store._entry(visible)["excerpt"])

    def test_scope_mismatch_is_not_reuse(self):
        self.put(sample())
        decision = self.store.assess(
            "method-note", "cochrane intervention review execution", "2026-10-11.1", "2026-10-11",
        )
        self.assertEqual(decision["decision"], "scope_mismatch")
        self.assertTrue(decision["record_retained"])

    def test_outdated_stable_concept_stays_and_requests_partial_refresh(self):
        self.put(sample())
        decision = self.store.assess(
            "method-note", "first unfamiliar product work", "2026-10-11.1", "2026-10-19",
        )
        self.assertEqual(decision["decision"], "partial_refresh")
        self.assertFalse(decision["cached_date_bypasses_live_check"])
        self.assertEqual(self.store._read_record("method-note")["status"], "current")
        listed = self.store.search("method discovery", limit=5)
        self.assertEqual(listed["matches"][0]["id"], "method-note")

    def test_cached_date_does_not_make_a_volatile_fact_current(self):
        record = sample(
            id="skill-text",
            stability="volatile_fact",
            topic="public deep-research skill text",
            query="deep-research skill 1.0.3 text",
            scope="public deep-research skill text",
            version="1.0.3",
        )
        record["freshness"]["live_check_required"] = True
        self.put(record)
        fresh = self.store.assess("skill-text", "public deep-research skill text", "1.0.3", "2026-10-11")
        self.assertEqual(fresh["decision"], "needs_live_check")
        self.assertTrue(fresh["needs_live_check"])
        refused = sample(id="bad-volatile", stability="volatile_fact")
        refused["freshness"]["live_check_required"] = False
        with self.assertRaises(cache.CacheError) as caught:
            self.put(refused)
        self.assertEqual(caught.exception.code, "bad_record")

    def test_update_keeps_history_and_conflict_keeps_the_current_record(self):
        stored = self.put(sample())
        changed = sample()
        changed["synthesis"] = "A narrower synthesis after checking the same sources."
        rejected = self._cli(
            "update", "--id", "method-note", "--record", self._write(changed, "rejected.json"),
            "--expect-sha256", "0" * 64,
        )
        self.assertEqual(rejected.returncode, 4, rejected.stdout + rejected.stderr)
        self.assertEqual(json.loads(rejected.stdout)["error"], "conflict")
        current = self.store._read_record("method-note")
        self.assertEqual(current["revision"], 1)
        self.assertEqual(current["content_sha256"], stored["content_sha256"])
        conflicts = list((self.root / "conflicts" / "method-note").glob("*.json"))
        self.assertEqual(len(conflicts), 1)
        updated = self._cli(
            "update", "--id", "method-note", "--record", self._write(changed, "next.json"),
            "--expect-sha256", stored["content_sha256"],
        )
        self.assertEqual(updated.returncode, 0, updated.stdout + updated.stderr)
        body = json.loads(updated.stdout)["record"]
        self.assertEqual(body["revision"], 2)
        prior = json.loads((self.root / "history" / "method-note" / "1.json").read_text())
        self.assertEqual(prior["revision"], 1)
        self.assertEqual(prior["content_sha256"], stored["content_sha256"])

    def test_replace_conflict_does_not_create_the_new_record(self):
        stored = self.put(sample())
        replacement = sample(id="method-note-2", synthesis="A contradicted portion was rechecked.")
        replacement["replaces"] = "method-note"
        failed = self._cli(
            "replace", "--id", "method-note", "--relation", "contradicted",
            "--record", self._write(replacement, "replacement.json"),
            "--expect-sha256", "ab" * 32,
        )
        self.assertEqual(failed.returncode, 4, failed.stdout + failed.stderr)
        self.assertFalse((self.root / "records" / "method-note-2.json").exists())
        self.assertEqual(self.store._read_record("method-note")["status"], "current")
        applied = self._cli(
            "replace", "--id", "method-note", "--relation", "contradicted",
            "--record", self._write(replacement, "replacement.json"),
            "--expect-sha256", stored["content_sha256"],
        )
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        previous = self.store._read_record("method-note")
        created = self.store._read_record("method-note-2")
        self.assertEqual(previous["status"], "contradicted")
        self.assertEqual(previous["replaced_by"], "method-note-2")
        self.assertEqual(created["replaces"], "method-note")
        visible = self.store.search("method discovery unfamiliar", limit=5)
        self.assertEqual({item["id"] for item in visible["matches"]}, {"method-note", "method-note-2"})

    def test_ordinary_cache_rejects_held_out_storage(self):
        source = TOOL.read_text(encoding="utf-8")
        self.assertNotIn("held_out", source)
        self.assertNotIn("include_held_out", source)
        self.assertNotIn("include-held-out", source)
        rejected = sample(visibility="held_out")
        with self.assertRaises(cache.CacheError) as caught:
            self.put(rejected)
        self.assertEqual(caught.exception.code, "bad_record")

    def test_a_small_note_omits_unknown_metadata(self):
        stored = self.put({
            "format": cache.FORMAT,
            "id": "short-note",
            "stability": "stable_concept",
            "topic": "sprite pivot stays centered",
            "synthesis": "Keep the pivot centered when slicing a sheet.",
            "provenance": [{"url": "https://example.test/sheet", "checked_on": "2026-10-11"}],
            "scope": "sprite sheets",
            "checked_on": "2026-10-11",
        })
        self.assertEqual(stored["problem"], "")
        self.assertEqual(stored["disposition"], "unset")
        self.assertIsNone(stored["freshness"]["review_after"])
        self.assertFalse(stored["freshness"]["live_check_required"])
        decision = self.store.assess("short-note", "sprite sheets", "", "2026-10-11")
        self.assertEqual(decision["decision"], "reuse")

    def test_private_local_provenance_is_stored(self):
        local = "/Users/example/artifact/notes.md"
        record = sample(synthesis=f"The adopted limit is in {local}.")
        record["provenance"] = [{
            "url": local,
            "checked_portion": f"Read {local} section 2",
            "checked_on": "2026-10-11",
        }]
        stored = self.put(record)
        self.assertEqual(stored["provenance"][0]["url"], local)
        self.assertIn(local, stored["synthesis"])
        relative = sample(id="relative-note")
        relative["provenance"] = [{"url": "notes.md", "checked_on": "2026-10-11"}]
        with self.assertRaises(cache.CacheError) as caught:
            self.put(relative)
        self.assertEqual(caught.exception.code, "bad_record")

    def test_volatile_note_defaults_the_seven_day_checkpoint(self):
        stored = self.put({
            "format": cache.FORMAT,
            "id": "skill-date",
            "stability": "volatile_fact",
            "topic": "public skill text date",
            "synthesis": "The checked text can change without a local edit.",
            "provenance": [{"url": "https://example.test/skill", "checked_on": "2026-10-11"}],
            "scope": "public skill text",
            "checked_on": "2026-10-11",
        })
        self.assertTrue(stored["freshness"]["live_check_required"])
        self.assertEqual(stored["freshness"]["review_after"], "2026-10-18")
        decision = self.store.assess("skill-date", "public skill text", "", "2026-10-11")
        self.assertEqual(decision["decision"], "needs_live_check")
        self.assertFalse(decision["cached_date_bypasses_live_check"])

    def test_default_root_reuses_the_company_record_home(self):
        from run_completion import default_home
        orca = str(Path.home() / "Library/Application Support/orca/codex-runtime-home/home")
        inherited = {"HOME": os.environ.get("HOME", ""), "PATH": os.environ.get("PATH", "")}
        environments = [
            {"SEJONG_HOME": str(self.root), "CODEX_HOME": orca},
            {"CODEX_HOME": orca},
            {"CODEX_HOME": str(Path(self.temp.name) / "standalone-codex")},
        ]
        for env in environments:
            with patch.dict(os.environ, {**inherited, **env}, clear=True):
                before = cache._default_root()
                resolved = cache._default_root()
                self.assertEqual(resolved, default_home() / "knowledge" / "research")
                self.assertEqual(before.exists(), resolved.exists())

    def test_second_put_is_rejected_and_files_stay_private(self):
        stored = self.put(sample())
        with self.assertRaises(cache.CacheError) as caught:
            self.put(sample())
        self.assertEqual(caught.exception.code, "already_exists")
        record = self.root / "records" / "method-note.json"
        self.assertEqual(stat.S_IMODE(record.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        self.assertTrue((self.root / "records" / "method-note.md").is_file())
        digest = self.store.digest()
        self.assertEqual(digest["loaded_record_bodies"], 0)
        self.assertEqual(digest["records"][0]["content_sha256"], stored["content_sha256"])

    def test_opening_skips_a_trivial_task_and_does_not_create_a_cache(self):
        missing = Path(self.temp.name) / "absent"
        trivial = self._cli("opening", "--task", "trivial")
        consequential = self._cli("opening", "--task", "consequential")
        self.assertEqual(json.loads(trivial.stdout)["action"], "no_survey")
        self.assertEqual(json.loads(consequential.stdout)["action"], "search_cache")
        self.assertFalse(missing.exists())
        absent = self._cli("--root", str(missing), "search", "--query", "method")
        self.assertEqual(absent.returncode, 0, absent.stdout)
        self.assertEqual(json.loads(absent.stdout)["status"], "cache_absent")
        self.assertFalse(missing.exists())

    def test_missing_index_does_not_scan_record_bodies(self):
        self.put(sample())
        (self.root / "index.json").unlink()
        result = self._cli("search", "--query", "zzuniquebody")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["error"], "index_missing")

    def test_symlink_root_is_rejected(self):
        target = Path(self.temp.name) / "real"
        target.mkdir()
        link = Path(self.temp.name) / "linked"
        link.symlink_to(target)
        result = self._cli("--root", str(link), "init")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["error"], "unsafe_path")
        self.assertFalse((target / "index.json").exists())

    def test_tool_has_no_network_shell_or_delete_command(self):
        source = TOOL.read_text(encoding="utf-8")
        for banned in ("import subprocess", "import socket", "import urllib", "import http.client", "os.system"):
            self.assertNotIn(banned, source)
        with self.assertRaises(SystemExit):
            cache.main(["delete"])

    def test_supersede_invalidates_tokens_and_cannot_be_revived(self):
        for relation in ("stale", "contradicted"):
            old_id = f"old-{relation}"
            first = self.put(sample(id=old_id))
            replacement = sample(id=f"new-{relation}", replaces=old_id)
            created, marked = self.store.supersede(old_id, replacement, first["content_sha256"], relation)
            self.assertNotEqual(marked["content_sha256"], first["content_sha256"])
            record_before = self._record_bytes()
            for token, expected_error in ((first["content_sha256"], "conflict"), (marked["content_sha256"], "record_superseded")):
                with self.assertRaises(cache.CacheError) as caught:
                    self.store.update(old_id, sample(id=old_id, synthesis="old writer"), token)
                self.assertEqual(caught.exception.code, expected_error)
                result = self._cli("use", "--id", old_id, "--expect-sha256", token,
                                   "--result", "attempted use", "--observed-on", "2026-10-11", "--limits", "test")
                self.assertEqual(json.loads(result.stdout)["error"], expected_error)
                self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(record_before, self._record_bytes())
            self.assertEqual(self.store._read_record(old_id)["replaced_by"], created["id"])

    def test_unchanged_update_also_invalidates_previous_revision_token(self):
        first = self.put(sample())
        second = self.store.update(first["id"], sample(), first["content_sha256"])
        self.assertEqual(second["revision"], 2)
        self.assertNotEqual(first["content_sha256"], second["content_sha256"])
        with self.assertRaises(cache.CacheError) as caught:
            self.store.update(first["id"], sample(synthesis="late writer"), first["content_sha256"])
        self.assertEqual(caught.exception.code, "conflict")

    def test_corrupt_index_preserves_bytes_before_all_mutations(self):
        first = self.put(sample())
        for damaged in (b"{broken", b"[]", b'{"format":"company-research-index/v1","records":[{}]}'):
            self.store.index_path.write_bytes(damaged)
            before = self._record_bytes()
            operations = (
                lambda: self.store.update(first["id"], sample(synthesis="must not write"), first["content_sha256"]),
                lambda: self.store.put(sample(id="new-record")),
                lambda: self.store.supersede(first["id"], sample(id="replacement", replaces=first["id"]), first["content_sha256"], "stale"),
            )
            for operation in operations:
                with self.assertRaises(cache.CacheError):
                    operation()
                self.assertEqual(before, self._record_bytes())
            result = self._cli("use", "--id", first["id"], "--expect-sha256", first["content_sha256"],
                               "--result", "test", "--observed-on", "2026-10-11", "--limits", "test")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(before, self._record_bytes())
            result = self._cli("search", "--query", "method")
            self.assertEqual(result.returncode, 2)
            self.assertIn("error", json.loads(result.stdout))
            self.assertNotIn("Traceback", result.stderr)

    def test_record_integrity_and_index_binding_checked_before_write(self):
        first = self.put(sample())
        path = self.root / "records/method-note.json"
        original = path.read_bytes()
        for mutation in (lambda r: r.update(status="stale"), lambda r: r.pop("scope"), lambda r: r.update(revision="two")):
            record = json.loads(original)
            mutation(record)
            path.write_text(json.dumps(record))
            before = self._record_bytes()
            with self.assertRaises(cache.CacheError):
                self.store.put(sample(id="new-note"))
            self.assertEqual(before, self._record_bytes())
            result = self._cli("get", "--id", first["id"])
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)
        path.write_bytes(original)
        index = json.loads(self.store.index_path.read_text())
        index["records"][0]["revision"] += 1
        self.store.index_path.write_text(json.dumps(index))
        before = self._record_bytes()
        with self.assertRaises(cache.CacheError) as caught:
            self.store.update(first["id"], sample(), first["content_sha256"])
        self.assertEqual(caught.exception.code, "index_record_mismatch")
        self.assertEqual(before, self._record_bytes())

    def test_malformed_cli_json_is_structured(self):
        for value in (b"{broken", b"[]", b"\xff", b'{"format":1,"format":2}'):
            path = Path(self.temp.name) / "malformed.json"
            path.write_bytes(value)
            result = self._cli("put", "--record", str(path))
            self.assertEqual(result.returncode, 2)
            self.assertIn("error", json.loads(result.stdout))
            self.assertNotIn("Traceback", result.stderr)

    def test_initialization_and_put_are_serialized_without_lost_record(self):
        root = Path(self.temp.name) / "concurrent-initial"
        barrier = Barrier(2)
        def writer(number):
            barrier.wait(timeout=5)
            return cache.Store(root, True).put(sample(id=f"writer-{number}"))
        with ThreadPoolExecutor(max_workers=2) as pool:
            records = list(pool.map(writer, (1, 2)))
        stored = cache.Store(root, False).digest()["records"]
        self.assertEqual({r["id"] for r in stored}, {r["id"] for r in records})

    def test_short_note_use_accepts_a_null_optional_review_date(self):
        note = sample(id="short-stable", freshness={})
        first = self.put(note)
        self.assertIsNone(first["freshness"]["review_after"])
        result = self._cli("use", "--id", first["id"], "--expect-sha256", first["content_sha256"],
                           "--result", "reused", "--observed-on", "2026-10-11", "--limits", "one check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["record"]["revision"], 2)

    def _record_bytes(self):
        # Lock and conflicts may change on rejection; current evidence/history may not.
        paths = [self.root / "index.json"]
        for folder in ("records", "history"):
            paths.extend(p for p in (self.root / folder).rglob("*") if p.is_file())
        return {str(p.relative_to(self.root)): p.read_bytes() for p in paths}

    def _write(self, record, name):
        path = Path(self.temp.name) / name
        path.write_text(json.dumps(record), encoding="utf-8")
        return str(path)

    def _cli(self, *args):
        if args and args[0] == "--root":
            command = [sys.executable, str(TOOL), *args]
        elif args and args[0] == "opening":
            command = [sys.executable, str(TOOL), *args]
        else:
            command = [sys.executable, str(TOOL), "--root", str(self.root), *args]
        return subprocess.run(command, capture_output=True, text=True, timeout=15)


if __name__ == "__main__":
    unittest.main()
