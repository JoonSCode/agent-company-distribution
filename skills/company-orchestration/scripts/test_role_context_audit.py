"""CLI coverage with generic synthetic files and saved events."""

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CLI = Path(__file__).with_name("role_context_audit.py")


class RoleContextAuditTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="role-context-audit-"))).resolve()
        self.scope = {"candidate": "a" * 40, "role": "development",
                      "session_id": "synthetic-session", "turn_id": "synthetic-turn"}
        self.pack = self.save("pack.md", b"Review every proposed change.\n")
        self.reference = self.save("guide.md", "Check café setup.\r\nKeep the previous revision.".encode())
        self.other = self.save("other.md", (self.root / "guide.md").read_bytes())
        self.context = {"schema": "company-role-context/v1", "candidate": self.scope["candidate"],
                        "role": self.scope["role"], "pack": self.pack, "references": [self.reference, self.other]}
        self.context_pin = self.save("context.json", self.context)
        self.capture = {"schema": "company-role-context-capture/v1", "scope": self.scope.copy(),
                        "context_sha256": self.context_pin["sha256"],
                        "events": [
                            {"kind": "delivered", "source": self.pack, "text": "Review every proposed change.\n"},
                            {"kind": "read", "source": self.reference,
                             "text": "Check café setup.\r\nKeep the previous revision."},
                            {"kind": "citation", "source": self.reference, "text": "Keep the previous revision."},
                        ]}
        self.request = {"schema": "company-role-context-audit-request/v1", "scope": self.scope,
                        "context": self.context_pin, "capture": None}

    def save(self, name, contents):
        raw = contents if isinstance(contents, bytes) else json.dumps(contents).encode()
        (self.root / name).write_bytes(raw)
        return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}

    def invoke(self, error=None):
        self.save("request.json", self.request)
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir()}
        proc = subprocess.run([sys.executable, "-B", str(CLI), "--request", "request.json"],
                              cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(proc.returncode, 2 if error else 0, proc.stdout)
        self.assertEqual({p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir()}, before)
        result = json.loads(proc.stdout)
        if error:
            self.assertEqual(result["status"], "rejected")
            self.assertIn(error, result["error"])
            self.assertNotIn("sources", result)
        else:
            self.assertEqual(result["status"], "checked")
            self.assertIsNone(result["independent_judgment"])
            self.assertIs(result["authority_granted"], False)
        return result

    def with_capture(self):
        self.request["capture"] = self.save("capture.json", self.capture)

    def test_valid_observations_and_exact_citation_are_separate(self):
        self.with_capture()
        result = self.invoke()
        self.assertEqual(result["scope"], self.scope)
        self.assertEqual(result["context"]["sha256"], self.context_pin["sha256"])
        self.assertEqual(result["capture"]["sha256"], self.request["capture"]["sha256"])
        pack, cited, identical = result["sources"]
        self.assertEqual([p["kind"] for p in result["sources"]], ["pack", "reference", "reference"])
        self.assertTrue(all(p["readable"] for p in result["sources"]))
        self.assertEqual(pack["delivered_events"], [1])
        self.assertEqual(pack["read_events"], [])
        self.assertEqual(cited["read_events"], [2])
        self.assertEqual(cited["delivered_events"], [])
        self.assertEqual(cited["citation_events"], [3])
        self.assertEqual(cited["exposure"], "observed_in_saved_capture")
        self.assertEqual(identical["exposure"], "unobserved")
        self.assertEqual(identical["citation_events"], [])

    def test_readable_inputs_without_capture_or_events_are_unobserved(self):
        self.capture["events"] = []
        for have_capture in (False, True):
            with self.subTest(have_capture=have_capture):
                if have_capture:
                    self.with_capture()
                result = self.invoke()
                self.assertEqual(result["capture"] is not None, have_capture)
                for source in result["sources"]:
                    self.assertIs(source["readable"], True)
                    self.assertEqual(source["exposure"], "unobserved")
                    self.assertEqual(source["citation_events"], [])

    def test_full_delivery_can_support_a_citation(self):
        self.capture["events"].append({"kind": "citation", "source": self.pack, "text": "Review every"})
        self.with_capture()
        first = self.invoke()
        self.assertEqual(self.invoke(), first)
        self.assertEqual(first["sources"][0]["citation_events"], [4])
        self.assertEqual(first["sources"][0]["read_events"], [])

    def test_missing_or_stale_frozen_inputs_are_rejected(self):
        for name, label in (("context.json", "frozen context"), ("pack.md", "pack pack.md"),
                            ("guide.md", "reference guide.md")):
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                path.unlink()
                self.invoke(f"{label} missing")
                self.save(name, original + b" ")
                self.invoke(f"{label} stale")
                self.save(name, original)

    def test_context_must_have_references_and_match_candidate_and_role(self):
        for field, mismatch, reason in (("references", [], "frozen references required"),
                                        ("candidate", "b" * 40, "candidate or role mismatch"),
                                        ("role", "qa", "candidate or role mismatch")):
            with self.subTest(field=field):
                self.request["context"] = self.save("context.json", {**self.context, field: mismatch})
                self.invoke(reason)

    def test_capture_cannot_mix_candidate_role_session_turn_or_context(self):
        for field in self.scope:
            with self.subTest(field=field):
                self.capture["scope"] = {**self.scope, field: "b" * 40 if field == "candidate" else "other"}
                self.with_capture()
                self.invoke("saved capture candidate, role, session or turn mismatch")
        self.capture["scope"] = self.scope.copy()
        self.capture["context_sha256"] = "b" * 64
        self.with_capture()
        self.invoke("saved capture frozen context mismatch")

    def test_unmatched_bytes_or_unsupported_citations_are_rejected(self):
        delivered, read, citation = self.capture["events"]
        for events, reason in (
            ([delivered, {**read, "text": "Check café setup."}, citation], "bytes differ"),
            ([delivered, citation, read], "no prior delivery or read"),
            ([delivered, read, {**citation, "source": self.other}], "no prior delivery or read"),
            ([delivered, read, {**citation, "source": {**self.reference, "sha256": self.pack["sha256"]}}],
             "outside the frozen context"),
            ([delivered, read, {**citation, "source": {**self.reference, "path": "unlisted.md"}}],
             "outside the frozen context"),
            ([delivered, read, {**citation, "text": "Delete the previous revision."}], "quote is unsupported"),
        ):
            with self.subTest(reason=reason, events=events):
                self.capture["events"] = events
                self.with_capture()
                self.invoke(reason)

    def test_stale_capture_does_not_fall_back_to_unobserved(self):
        self.with_capture()
        self.save("capture.json", {**self.capture, "events": []})
        self.invoke("saved capture stale")
        (self.root / "capture.json").unlink()
        self.invoke("saved capture missing")

    def test_ledger_shape_cannot_be_used_as_saved_capture(self):
        ledger = {"format": "agent-company.reference-read-ledger/v0.1", "used_required": ["guide"]}
        self.request["capture"] = self.save("ledger.json", ledger)
        self.invoke("invalid saved capture fields")

    def test_alias_paths_cannot_change_context_source_identity(self):
        for path in ("./guide.md", "sub/../guide.md", "/guide.md"):
            with self.subTest(path=path):
                context = copy.deepcopy(self.context)
                context["references"][0]["path"] = path
                self.request["context"] = self.save("context.json", context)
                self.invoke("canonical and relative")


if __name__ == "__main__":
    unittest.main()
