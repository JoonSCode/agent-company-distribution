#!/usr/bin/env python3
"""Behavioral continuity fixtures; never control a real Orca Dispatch."""
from __future__ import annotations

import copy
import hashlib
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

import continuity
import research_cache as cache


class ContinuityTests(unittest.TestCase):
    def test_note_serializes_once_and_preserves_input(self):
        before = copy.deepcopy(self.note)
        with patch.object(cache, "_canonical", wraps=cache._canonical) as canonical, patch.object(
            cache, "safe_note", wraps=cache.safe_note,
        ) as safe:
            note = continuity._note(self.note, self.record)
        self.assertEqual(canonical.call_count, 1)
        self.assertEqual(safe.call_args.args[0], cache._canonical(note))
        self.assertEqual(self.note, before)
        self.assertEqual(note, self.note)

    def test_note_secret_before_size_and_utf8_byte_boundary(self):
        note = copy.deepcopy(self.note)
        note["known"] = ["한글🙂"]
        size = len(cache._canonical(continuity._note(note, self.record)))
        with patch.object(cache, "MAX_BYTES", size * 2):
            self.assertEqual(continuity._note(note, self.record), note)
        with patch.object(cache, "MAX_BYTES", size * 2 - 1):
            with self.assertRaises(cache.CacheError) as caught:
                continuity._note(note, self.record)
        self.assertEqual(caught.exception.code, "too_large")
        note["known"] = ["Authorization: Bearer fixture-only"]
        # Leave source refs readable while the canonical note exceeds half-limit.
        with patch.object(cache, "MAX_BYTES", 500):
            with self.assertRaises(cache.CacheError) as caught:
                continuity._note(note, self.record)
        self.assertEqual(caught.exception.code, "secret_detected")

    def test_note_encoding_and_serialization_fail_before_secret_check(self):
        note = copy.deepcopy(self.note)
        note["known"] = ["\ud800"]
        with patch.object(cache, "safe_note") as safe:
            with self.assertRaises(UnicodeEncodeError):
                continuity._note(note, self.record)
            safe.assert_not_called()
        failure = TypeError("serialization fixture")
        with patch.object(cache, "_canonical", side_effect=failure) as canonical, patch.object(cache, "safe_note") as safe:
            with self.assertRaises(TypeError) as caught:
                continuity._note(self.note, self.record)
            self.assertIs(caught.exception, failure)
            self.assertEqual(canonical.call_count, 1)
            safe.assert_not_called()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp", prefix="company-continuity-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.store = continuity.Continuity(self.base / "work-note")
        cases = json.loads(Path(__file__).parents[1].joinpath("assets/record-cases.json").read_text())
        self.record = copy.deepcopy(cases["cases"][0]["record"])
        self.record["label"] = "real"  # Real-shaped fixture, not observed runtime authority.
        self.record["goal"].update(status="active", known_failure=False, assessment=None)
        self.record["ownership"] = [self.record["ownership"][1]]
        self.record["ownership"][0]["from"] = None
        for key in self.record["evidence"]:
            path = self.base / (key + ".txt")
            path.write_text("Fixture source for " + key)
            self.record["evidence"][key] = {"ref": str(path), "file": path.name,
                                           "sha256": continuity.reference(path)["sha256"],
                                           "kind": "host" if key == "result" else "source"}
        self.record["evidence"]["lease-settlement"] = dict(self.record["evidence"]["result"])
        run = self.base / "run-observation.json"
        run.write_text(json.dumps({"ok": True, "result": {"runId": "run_fixture"}}))
        self.record["evidence"]["run-observation"] = {"ref": str(run), "file": run.name,
                                                      "sha256": continuity.reference(run)["sha256"], "kind": "host"}
        original = self.base / "original-intent.md"
        original.write_text("Original intent and correction source; fixture only.")
        self.original = continuity.reference(original)
        self.record_ref = self.save_record(self.record, "initial-record.json")
        self.note = {
            "intent": "Preserve the actual intended result", "authorized_scope": "approved-scope",
            "corrections": ["Do not replace observed results with descriptions"],
            "decisions": ["Keep original evidence; retire stale interpretation"],
            "known": ["Fixture source exists"], "inferred": [], "unknown": ["Quality effect unmeasured"],
            "questions": ["Unanswered material question remains visible"], "next_actions": ["Owner reads sources and accepts scoped handoff"],
            "sources": [self.original],
            "run": {"id": "run_fixture", "evidence": "run-observation"},
            "work": [{"task": "task-1", "dispatch": "dispatch-current", "side_effects": [], "leases": []}],
        }

    def save_record(self, record, name):
        path = self.base / name
        path.write_text(json.dumps(record, ensure_ascii=False))
        return continuity.reference(path)

    def write(self, note=None, record_ref=None, actor="B", expect=None):
        return self.store.write(note or self.note, record_ref or self.record_ref, actor, expect)

    def successor(self, actor="C"):
        record = copy.deepcopy(self.record)
        record["goal"]["current_owner"] = actor
        record["ownership"].append({"revision": "r1", "scope": "approved-scope", "from": "B", "to": actor,
                                     "status": "accepted", "accepted_by": actor, "evidence": "accept-b"})
        return self.save_record(record, actor + "-record.json")

    def reads(self, state, record_ref):
        result = [continuity.reference(self.store.state_path), state["record"], record_ref, self.original]
        for ref in (state["record"], record_ref):
            record = json.loads(Path(ref["path"]).read_text())
            for item in record["evidence"].values():
                if item["kind"] == "host":
                    result.append({"path": str(self.base / item["file"]), "sha256": item["sha256"]})
        return result

    def prepare(self, state, actor="C", session="next-session"):
        return self.store.prepare(state["content_sha256"], actor, session, "Repeated stale decisions; new scoped session")

    def test_readback_needs_existing_ownership_and_does_not_mutate_company_record(self):
        state = self.write()
        handoff = self.prepare(state)
        successor = self.successor()
        original = Path(successor["path"]).read_bytes()
        receipt = self.store.accept(handoff["ref"], successor, "C", "next-session", self.reads(state, successor))
        self.assertEqual(receipt["state_sha256"], state["content_sha256"])
        self.assertEqual(Path(successor["path"]).read_bytes(), original)
        self.assertEqual(self.store._state(), state)
        next_state = self.write(actor="C", record_ref=successor, expect=state["content_sha256"])
        self.assertEqual(next_state["revision"], 2)
        self.assertEqual(next_state["note"]["corrections"], self.note["corrections"])
        self.assertTrue((self.store.root / "history" / (state["content_sha256"] + ".json")).exists())

    def test_missing_handoff_and_missing_readback_do_not_accept_successor(self):
        state = self.write()
        successor = self.successor()
        with self.assertRaises(cache.CacheError) as caught:
            self.write(actor="C", record_ref=successor, expect=state["content_sha256"])
        self.assertEqual(caught.exception.code, "missing_handoff")
        handoff = self.prepare(state)
        with self.assertRaises(cache.CacheError) as caught:
            self.store.accept(handoff["ref"], successor, "C", "next-session", [])
        self.assertEqual(caught.exception.code, "missing_readback")
        self.assertEqual(self.store._state(), state)

    def test_stale_handoff_retains_new_user_correction(self):
        state = self.write()
        handoff = self.prepare(state)
        updated = copy.deepcopy(self.note)
        updated["corrections"].append("Latest interrupt changes the next action")
        current = self.write(updated, expect=state["content_sha256"])
        successor = self.successor()
        with self.assertRaises(cache.CacheError) as caught:
            self.store.accept(handoff["ref"], successor, "C", "next-session", self.reads(current, successor))
        self.assertEqual(caught.exception.code, "stale_handoff")
        self.assertEqual(self.store._state()["note"]["corrections"], updated["corrections"])

    def test_omitted_corrections_effects_or_dispatch_and_scope_mismatch_are_rejected(self):
        for field in ("corrections", "authorized_scope", "questions", "work"):
            note = copy.deepcopy(self.note)
            del note[field]
            with self.assertRaises(cache.CacheError):
                self.write(note)
        bad = copy.deepcopy(self.note)
        del bad["work"][0]["side_effects"]
        with self.assertRaises(cache.CacheError):
            self.write(bad)
        bad = copy.deepcopy(self.note)
        bad["work"][0]["dispatch"] = "stale-dispatch"
        with self.assertRaises(cache.CacheError) as caught:
            self.write(bad)
        self.assertEqual(caught.exception.code, "stale_dispatch")
        state = self.write()
        changed = copy.deepcopy(self.record)
        changed["goal"]["scope"] = "other-scope"
        ref = self.save_record(changed, "bad-scope.json")
        with self.assertRaises(cache.CacheError):
            self.write(record_ref=ref, expect=state["content_sha256"])
        self.assertEqual(self.store._state(), state)

    def test_live_unknown_dispatch_or_unsettled_lease_blocks_acceptance(self):
        for status in ("live", "unknown"):
            record = copy.deepcopy(self.record)
            record["tasks"][0]["execution"].update(state=status, result=None)
            ref = self.save_record(record, status + "-record.json")
            root = continuity.Continuity(self.base / status)
            state = root.write(self.note, ref, "B")
            handoff = root.prepare(state["content_sha256"], "B", "next", "Context pressure")
            with self.assertRaises(cache.CacheError) as caught:
                root.accept(handoff["ref"], ref, "B", "next", [continuity.reference(root.state_path), ref, self.original])
            self.assertEqual(caught.exception.code, "active_dispatch")
        note = copy.deepcopy(self.note)
        note["work"][0]["leases"] = [{"id": "exclusive-writer", "status": "active", "evidence": "lease-settlement"}]
        state = self.write(note)
        handoff = self.prepare(state, "B")
        with self.assertRaises(cache.CacheError) as caught:
            self.store.accept(handoff["ref"], self.record_ref, "B", "next-session", self.reads(state, self.record_ref))
        self.assertEqual(caught.exception.code, "active_effect")
        with self.assertRaises(cache.CacheError) as caught:
            self.write(expect=state["content_sha256"])
        self.assertEqual(caught.exception.code, "active_effect")

    def test_active_dispatch_cannot_be_replaced_in_work_note(self):
        record = copy.deepcopy(self.record)
        record["tasks"][0]["execution"].update(state="unknown", result=None)
        old = self.save_record(record, "unknown-record.json")
        state = self.write(record_ref=old)
        record["tasks"] = []
        new = self.save_record(record, "omitted-dispatch.json")
        note = copy.deepcopy(self.note)
        note["work"] = []
        with self.assertRaises(cache.CacheError) as caught:
            self.write(note, new, expect=state["content_sha256"])
        self.assertEqual(caught.exception.code, "active_dispatch")

    def test_exited_dispatch_needs_positive_host_observation_and_run_cannot_change(self):
        record = copy.deepcopy(self.record)
        record["tasks"][0]["execution"].update(state="exited", result=None)
        ref = self.save_record(record, "exited-no-observation.json")
        state = self.write(record_ref=ref)
        handoff = self.prepare(state, "B")
        with self.assertRaises(cache.CacheError) as caught:
            self.store.accept(handoff["ref"], ref, "B", "next-session", self.reads(state, ref))
        self.assertEqual(caught.exception.code, "missing_evidence")
        note = copy.deepcopy(self.note)
        note["run"]["id"] = "run_unrelated"
        with self.assertRaises(cache.CacheError) as caught:
            self.write(note, ref, expect=state["content_sha256"])
        self.assertEqual(caught.exception.code, "scope_conflict")

    def test_source_or_acceptance_scope_change_preserves_current_note(self):
        state = self.write()
        handoff = self.prepare(state)
        successor = self.successor()
        Path(self.original["path"]).write_text("Changed original after handoff")
        with self.assertRaises(cache.CacheError) as caught:
            self.store.accept(handoff["ref"], successor, "C", "next-session", self.reads(state, successor))
        self.assertEqual(caught.exception.code, "stale_source")
        self.assertEqual(self.store._state(), state)

    def test_concurrent_successor_sessions_and_state_writers_have_one_winner(self):
        state = self.write()
        one = self.prepare(state, "B", "session-one")
        two = self.prepare(state, "B", "session-two")
        barrier = Barrier(2)
        def accept(pair):
            barrier.wait(timeout=5)
            ref, session = pair
            try:
                self.store.accept(ref, self.record_ref, "B", session, self.reads(state, self.record_ref))
                return "accepted"
            except cache.CacheError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(accept, [(one["ref"], "session-one"), (two["ref"], "session-two")]))
        self.assertCountEqual(results, ["accepted", "acceptance_conflict"])
        barrier = Barrier(2)
        def write(number):
            barrier.wait(timeout=5)
            note = copy.deepcopy(self.note)
            note["known"].append(f"Writer {number}")
            try:
                self.write(note, expect=state["content_sha256"])
                return "updated"
            except cache.CacheError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, (1, 2)))
        self.assertCountEqual(results, ["updated", "state_conflict"])

    def test_cli_missing_state_is_structured_and_synthetic_authority_is_rejected(self):
        result = subprocess.run([sys.executable, str(Path(continuity.__file__)), "--root", str(self.base / "empty"),
                                 "prepare", "--expect-state-sha256", "0" * 64, "--successor", "B", "--session", "next", "--reason", "pressure"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["error"], "missing_state")
        record = copy.deepcopy(self.record)
        record["label"] = "synthetic"
        with self.assertRaises(cache.CacheError):
            self.write(record_ref=self.save_record(record, "synthetic.json"))

    def test_receipt_only_preserves_exact_full_state_and_guards(self):
        receipt = self.store.write(self.note, self.record_ref, "B", receipt_only=True)
        raw = self.store.state_path.read_bytes()
        state = json.loads(raw)
        self.assertEqual(state["note"], self.note)
        self.assertEqual(receipt["state_ref"], {"path": str(self.store.state_path),
                                              "sha256": hashlib.sha256(raw).hexdigest()})
        for key in ("format", "goal", "record", "revision", "content_sha256"):
            self.assertEqual(receipt[key], state[key])
        self.assertEqual(receipt["run"], self.note["run"])
        self.assertNotIn("note", receipt)
        with self.assertRaises(cache.CacheError) as conflict:
            self.store.write(self.note, self.record_ref, "B", receipt_only=True)
        self.assertEqual(conflict.exception.code, "state_conflict")
        self.assertEqual(self.store.state_path.read_bytes(), raw)
        Path(self.original["path"]).write_text("Changed source")
        with self.assertRaises(cache.CacheError) as stale:
            self.store.write(self.note, self.record_ref, "B", state["content_sha256"], receipt_only=True)
        self.assertEqual(stale.exception.code, "stale_source")
        self.assertEqual(self.store.state_path.read_bytes(), raw)

    def test_receipt_reference_does_not_claim_later_state_bytes(self):
        receipt = self.store.write(self.note, self.record_ref, "B", receipt_only=True)
        saved = self.store.state_path.read_bytes()
        updated = copy.deepcopy(self.note)
        updated["corrections"].append("Later correction")
        state = self.write(updated, expect=receipt["content_sha256"])
        self.assertEqual(state["note"], updated)
        self.assertEqual(receipt["state_ref"]["sha256"], hashlib.sha256(saved).hexdigest())
        with self.assertRaises(cache.CacheError) as stale:
            continuity.read_ref(receipt["state_ref"])
        self.assertEqual(stale.exception.code, "stale_source")

    def test_cli_receipt_only_and_default_output(self):
        note = self.base / "note.json"
        note.write_text(json.dumps(self.note))
        command = [sys.executable, "-B", str(Path(continuity.__file__)), "--root", str(self.store.root),
                   "write", "--note", str(note), "--record", self.record_ref["path"],
                   "--expect-record-sha256", self.record_ref["sha256"], "--actor", "B"]
        output = subprocess.run([*command, "--receipt-only"], capture_output=True, text=True)
        self.assertEqual(output.returncode, 0, output.stderr + output.stdout)
        receipt = json.loads(output.stdout)["result"]
        self.assertEqual(continuity.read_ref(receipt["state_ref"]), self.store.state_path.read_bytes())
        output = subprocess.run([*command, "--expect-state-sha256", receipt["content_sha256"]],
                                capture_output=True, text=True)
        self.assertEqual(output.returncode, 0, output.stderr + output.stdout)
        self.assertEqual(json.loads(output.stdout)["result"], self.store._state())


if __name__ == "__main__":
    unittest.main()
