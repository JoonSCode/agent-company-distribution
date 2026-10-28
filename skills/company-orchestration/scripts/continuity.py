#!/usr/bin/env python3
"""Hash-bound work notes and successor readback, not an Orca ownership ledger."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

sys.dont_write_bytecode = True
import research_cache as cache
import record_check

FORMAT = "company-work-continuity/v1"
HANDOFF = "company-session-handoff/v1"
ACCEPTANCE = "company-session-readback/v1"
SECTIONS = ("intent", "authorized_scope", "corrections", "decisions", "known", "inferred", "unknown", "questions", "next_actions")


def reference(path):
    path = Path(path).absolute()
    return {"path": str(path), "sha256": cache._digest(cache._read_file(path, cache.MAX_BYTES))}


def read_ref(ref):
    cache._require(isinstance(ref, dict) and set(ref) == {"path", "sha256"}, "bad_ref", "path/hash reference required")
    cache._require(isinstance(ref["path"], str) and Path(ref["path"]).is_absolute(), "bad_ref", "absolute evidence path")
    path = Path(ref["path"])
    for ancestor in (path, *path.parents):
        cache._reject_symlink(ancestor, "continuity evidence")
    data = cache._read_file(path, cache.MAX_BYTES)
    cache._require(cache._digest(data) == ref["sha256"], "stale_source", "source hash changed")
    return data


def authority(ref):
    record = cache._json(read_ref(ref), "Company record")
    cache._require(isinstance(record, dict), "bad_authority", "Company record object")
    cache._require(isinstance(record.get("evidence"), dict), "bad_authority", "Company evidence map")
    # Check supplied local evidence with bounded, no-follow reads before the
    # existing non-authoritative Company record checker interprets its fields.
    for item in record.get("evidence", {}).values():
        if isinstance(item, dict) and "file" in item:
            path = Path(ref["path"]).parent / item["file"]
            read_ref({"path": str(path.absolute()), "sha256": item.get("sha256")})
    result = record_check.check_record(record, Path(ref["path"]).parent)
    cache._require(result["ok"], "bad_authority", "Company record check failed")
    cache._require(record.get("label") == "real", "bad_authority", "handoff needs a real Company record, not synthetic authority")
    cache._require(record["goal"]["owner_acceptance"] == "accepted", "owner_pending", "existing ownership acceptance is pending")
    return record


def _goal(record):
    return {key: record["goal"][key] for key in ("id", "scope", "revision")}


def _evidence(record, key, host=False):
    item = record["evidence"].get(key)
    cache._require(isinstance(item, dict) and "file" in item and item.get("sha256"), "missing_evidence", "readable hash-bound evidence required")
    if host:
        cache._require(item["kind"] == "host", "missing_evidence", "settlement must reference a host observation")


def _note(payload, record):
    cache._require(isinstance(payload, dict) and set(payload) == set(SECTIONS) | {"sources", "work", "run"}, "bad_note", "explicit intent/corrections/decisions/work/questions/uncertainty/Run fields required")
    note = {}
    run = payload["run"]
    cache._require(isinstance(run, dict) and set(run) == {"id", "evidence"}, "bad_note", "exact Orca Run and host evidence reference required")
    cache._line(run["id"], "Run id", 200)
    cache._require(run["id"].startswith("run_"), "bad_note", "Orca Run id")
    _evidence(record, run["evidence"], host=True)
    note["run"] = run
    for key in SECTIONS:
        if key in ("intent", "authorized_scope"):
            note[key] = cache._text(payload[key], key, cache.TEXT_LIMIT)
        else:
            cache._require(isinstance(payload[key], list) and len(payload[key]) <= 100, "bad_note", key)
            note[key] = [cache._line(item, key, cache.LINE_LIMIT) for item in payload[key]]
    sources = payload["sources"]
    cache._require(isinstance(sources, list) and 1 <= len(sources) <= 30, "bad_note", "original intent and actual state source refs required")
    for ref in sources:
        read_ref(ref)
    note["sources"] = sources
    tasks = {task["id"]: task for task in record["tasks"]}
    work = payload["work"]
    cache._require(isinstance(work, list) and len(work) == len(tasks), "missing_work", "every current Company Task/Dispatch must remain visible")
    seen = set()
    for item in work:
        cache._require(isinstance(item, dict) and set(item) == {"task", "dispatch", "side_effects", "leases"}, "bad_work", "Task/Dispatch, side_effects and leases must be explicit")
        task = tasks.get(item["task"])
        cache._require(task is not None and item["task"] not in seen and item["dispatch"] == task["current_dispatch"], "stale_dispatch", "work must bind exact current Task/Dispatch")
        seen.add(item["task"])
        for field in ("side_effects", "leases"):
            effects = item[field]
            cache._require(isinstance(effects, list), "bad_work", "effects/leases must be explicit arrays")
            ids = set()
            for effect in effects:
                cache._require(isinstance(effect, dict) and set(effect) == {"id", "status", "evidence"}, "bad_work", "effect id/status/evidence")
                cache._line(effect["id"], "effect id", 200)
                cache._require(effect["id"] not in ids, "bad_work", "duplicate effect")
                ids.add(effect["id"])
                cache._require(effect["status"] in ("active", "uncertain", "settled"), "bad_work", "effect status")
                _evidence(record, effect["evidence"], host=effect["status"] == "settled")
                if effect["status"] == "settled":
                    cache._require(task["execution"]["state"] in ("exited", "settled"), "active_effect", "a note cannot settle a live/unknown Orca Dispatch")
    note["work"] = work
    canonical_note = cache._canonical(note)
    cache.safe_note(canonical_note)
    cache._require(len(canonical_note) <= cache.MAX_BYTES // 2, "too_large", "compact work-note boundary")
    return note


def _settled(note, record):
    # Exit permits a handoff, not a product-success or independent-acceptance claim.
    for task in record["tasks"]:
        cache._require(task["execution"]["state"] in ("exited", "settled"), "active_dispatch", "live/unknown Dispatch remains with existing authority")
        if task["execution"]["state"] == "settled":
            _evidence(record, task["execution"]["result"]["evidence"], host=True)
        else:
            _evidence(record, task["execution"].get("observation"), host=True)
    for work in note["work"]:
        for effect in work["side_effects"] + work["leases"]:
            cache._require(effect["status"] == "settled", "active_effect", "active/uncertain side effect or lease cannot be transferred")


class Continuity:
    def __init__(self, root):
        self.root = Path(root).absolute()
        for path in (self.root, *self.root.parents):
            cache._reject_symlink(path, "continuity root")
        cache._mkdir(self.root)
        self.state_path = self.root / "state.json"

    def _exclusive(self):
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        return cache._Lock(os.open(self.root / "lock", flags, 0o600), True)

    def _state(self):
        cache._require(self.state_path.exists(), "missing_state", "write the durable work note first")
        state = cache._json(cache._read_file(self.state_path, cache.MAX_BYTES), "continuity state")
        cache._require(isinstance(state, dict) and state.get("format") == FORMAT, "bad_state", "continuity format")
        cache._require(cache.content_sha256(state) == state.get("content_sha256"), "bad_state", "state integrity")
        return state

    def _save(self, path, value):
        data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
        cache._require(len(data) <= cache.MAX_BYTES, "too_large", "continuity artifact")
        cache._atomic_write(path, data, 0o600)
        return {"path": str(path), "sha256": cache._digest(data)}

    def write(self, payload, record_ref, actor, expect=None, *, receipt_only=False):
        with self._exclusive():
            record = authority(record_ref)
            cache._require(actor == record["goal"]["current_owner"], "wrong_actor", "writer must be the accepted owner in the existing Company record")
            note = _note(payload, record)
            previous = self._state() if self.state_path.exists() else None
            cache._require((previous["content_sha256"] if previous else None) == expect, "state_conflict", "durable work note changed; preserve and merge before writing")
            if previous:
                cache._require(previous["goal"] == _goal(record), "scope_conflict", "changed scope/revision needs a separately accepted work note")
                cache._require(previous["note"]["run"]["id"] == note["run"]["id"], "scope_conflict", "Run cannot change inside an existing work note")
                old_record = authority(previous["record"])
                if old_record["goal"]["current_owner"] != actor:
                    _settled(previous["note"], old_record)
                    accepted_path = self.root / "accepted" / (expect + ".json")
                    cache._require(accepted_path.is_file(), "missing_handoff", "new owner must read back the existing state first")
                    accepted = cache._json(cache._read_file(accepted_path, cache.MAX_BYTES), "accepted readback")
                    cache._require(accepted.get("format") == ACCEPTANCE and accepted.get("actor") == actor
                                   and accepted.get("state_sha256") == expect and accepted.get("record") == record_ref,
                                   "acceptance_conflict", "readback must bind this successor and Company record")
                new_tasks = {task["id"]: task for task in record["tasks"]}
                for prior_task in old_record["tasks"]:
                    if prior_task["execution"]["state"] in ("live", "unknown"):
                        updated = new_tasks.get(prior_task["id"])
                        cache._require(updated is not None and updated["current_dispatch"] == prior_task["current_dispatch"],
                                       "active_dispatch", "unsettled Dispatch cannot disappear or become another attempt")
                # Unsettled effects cannot disappear or become settled through text alone.
                current_work = {item["task"]: item for item in note["work"]}
                for prior in previous["note"]["work"]:
                    for field in ("side_effects", "leases"):
                        for effect in prior[field]:
                            if effect["status"] != "settled":
                                new = next((item for item in current_work.get(prior["task"], {}).get(field, []) if item["id"] == effect["id"]), None)
                                cache._require(new is not None, "active_effect", "unsettled effect/lease cannot be omitted")
            state = {"format": FORMAT, "goal": _goal(record), "record": record_ref, "note": note,
                     "revision": previous["revision"] + 1 if previous else 1, "content_sha256": None}
            state["content_sha256"] = cache.content_sha256(state)
            if previous:
                folder = self.root / "history"
                cache._mkdir(folder)
                self._save(folder / (previous["content_sha256"] + ".json"), previous)
            saved = self._save(self.state_path, state)
            if receipt_only:
                return {"format": FORMAT, "goal": state["goal"], "record": state["record"],
                        "run": note["run"], "revision": state["revision"],
                        "content_sha256": state["content_sha256"], "state_ref": saved}
            return state

    def prepare(self, expect, successor, session, reason):
        with self._exclusive():
            state = self._state()
            cache._require(state["content_sha256"] == expect, "state_conflict", "state changed before handoff")
            record = authority(state["record"])
            _note(state["note"], record)
            handoff = {"format": HANDOFF, "state_sha256": expect, "goal": state["goal"],
                       "record": state["record"], "successor": cache._line(successor, "successor", 200),
                       "session": cache._line(session, "session", 200), "reason": cache._line(reason, "reason", 2000)}
            digest = cache._digest(cache._canonical(handoff))
            folder = self.root / "handoffs"
            cache._mkdir(folder)
            self._save(folder / (digest + ".json"), handoff)
            return {"handoff": handoff, "ref": reference(folder / (digest + ".json"))}

    def accept(self, handoff_ref, successor_record, actor, session, reads):
        with self._exclusive():
            state = self._state()
            handoff = cache._json(read_ref(handoff_ref), "handoff")
            cache._require(isinstance(handoff, dict) and handoff.get("format") == HANDOFF, "missing_handoff", "prepared handoff required")
            path = self.root / "handoffs" / (cache._digest(cache._canonical(handoff)) + ".json")
            cache._require(reference(path) == handoff_ref, "missing_handoff", "handoff is not from this work note")
            cache._require(handoff["state_sha256"] == state["content_sha256"] and handoff["record"] == state["record"], "stale_handoff", "handoff omitted a newer correction or source")
            cache._require(handoff["successor"] == actor and handoff["session"] == session, "wrong_actor", "exact successor/session must accept")
            old_record = authority(state["record"])
            new_record = authority(successor_record)
            cache._require(_goal(new_record) == state["goal"] == handoff["goal"], "scope_conflict", "successor acceptance must match goal/scope/revision")
            cache._require(new_record["goal"]["current_owner"] == actor, "owner_pending", "existing Company ownership must explicitly accept the successor")
            if actor != old_record["goal"]["current_owner"]:
                old_chain = [item for item in old_record["ownership"] if item["status"] == "accepted"]
                new_chain = [item for item in new_record["ownership"] if item["status"] == "accepted"]
                cache._require(new_chain[:-1] == old_chain and new_chain[-1]["from"] == old_record["goal"]["current_owner"], "owner_conflict", "existing ownership chain must preserve its prior accepted owner")
            _note(state["note"], old_record)
            _settled(state["note"], old_record)
            _settled(state["note"], new_record)
            old_tasks = {(t["id"], t["current_dispatch"]) for t in old_record["tasks"]}
            cache._require(old_tasks == {(t["id"], t["current_dispatch"]) for t in new_record["tasks"]}, "stale_dispatch", "handoff must preserve exact observed Task/Dispatch")
            required = [reference(self.state_path), state["record"], successor_record, *state["note"]["sources"]]
            for ref, record in ((state["record"], old_record), (successor_record, new_record)):
                for item in record["evidence"].values():
                    if item.get("kind") == "host" and "file" in item:
                        required.append({"path": str((Path(ref["path"]).parent / item["file"]).absolute()), "sha256": item["sha256"]})
            cache._require(isinstance(reads, list), "missing_readback", "successor read ledger required")
            for ref in reads:
                read_ref(ref)
            cache._require(all(ref in reads for ref in required), "missing_readback", "read original sources, work note and current authority before accepting")
            receipt = {"format": ACCEPTANCE, "state_sha256": state["content_sha256"], "handoff": handoff_ref,
                       "record": successor_record, "actor": actor, "session": session, "reads": reads,
                       "authority": "existing Company record and Orca; this is only a readback attestation"}
            folder = self.root / "accepted"
            cache._mkdir(folder)
            path = folder / (state["content_sha256"] + ".json")
            if path.exists():
                prior = cache._json(cache._read_file(path, cache.MAX_BYTES), "prior acceptance")
                cache._require(prior == receipt, "acceptance_conflict", "another successor readback is retained")
            else:
                self._save(path, receipt)
            return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    write = sub.add_parser("write")
    write.add_argument("--note", type=Path, required=True)
    write.add_argument("--record", type=Path, required=True)
    write.add_argument("--expect-record-sha256", required=True)
    write.add_argument("--actor", required=True)
    write.add_argument("--expect-state-sha256")
    write.add_argument("--receipt-only", action="store_true",
                       help="Return saved state identity/reference without echoing the input note; all checks still run")
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--expect-state-sha256", required=True)
    prepare.add_argument("--successor", required=True)
    prepare.add_argument("--session", required=True)
    prepare.add_argument("--reason", required=True)
    accept = sub.add_parser("accept")
    accept.add_argument("--handoff", type=Path, required=True)
    accept.add_argument("--expect-handoff-sha256", required=True)
    accept.add_argument("--record", type=Path, required=True)
    accept.add_argument("--expect-record-sha256", required=True)
    accept.add_argument("--actor", required=True)
    accept.add_argument("--session", required=True)
    accept.add_argument("--reads", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        store = Continuity(args.root)
        if args.command == "write":
            result = store.write(cache._load_input(args.note), {"path": str(args.record.absolute()), "sha256": args.expect_record_sha256}, args.actor, args.expect_state_sha256,
                                 receipt_only=args.receipt_only)
        elif args.command == "prepare":
            result = store.prepare(args.expect_state_sha256, args.successor, args.session, args.reason)
        else:
            result = store.accept({"path": str(args.handoff.absolute()), "sha256": args.expect_handoff_sha256},
                                  {"path": str(args.record.absolute()), "sha256": args.expect_record_sha256},
                                  args.actor, args.session, cache._load_input(args.reads))
        return cache._emit({"status": "ok", "result": result}, 0)
    except cache.CacheError as exc:
        return cache._emit({"status": "error", "error": exc.code, "detail": exc.detail}, 2)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return cache._emit({"status": "error", "error": "invalid_or_unavailable", "detail": type(exc).__name__}, 2)


if __name__ == "__main__":
    sys.exit(main())
