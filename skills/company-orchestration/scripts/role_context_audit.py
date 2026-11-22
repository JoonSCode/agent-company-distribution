#!/usr/bin/env python3
"""Check frozen role context and bounded saved session evidence. Stdout only."""

import sys

if __name__ == "__main__":
    sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path
import re

from native_operations import (
    Invalid, absolute, decode, regular, request, require, sha, shape, text, valid_hash,
)


REQUEST = "company-role-context-audit-request/v1"
CONTEXT = "company-role-context/v1"
CAPTURE = "company-role-context-capture/v1"
RESULT = "company-role-context-audit/v1"
SCOPE_KEYS = ("candidate", "role", "session_id", "turn_id")
PIN_KEYS = ("path", "sha256")


def read_pinned(path, expected, label):
    try:
        raw = regular(path)
    except FileNotFoundError as exc:
        raise Invalid(f"{label} missing") from exc
    except (OSError, Invalid) as exc:
        raise Invalid(f"{label} unreadable") from exc
    require(sha(raw) == expected, f"{label} stale (SHA-256 mismatch)")
    return raw


def load_pinned(pin, base, label):
    shape(pin, PIN_KEYS, label)
    path = absolute(pin["path"], base)
    return path, read_pinned(path, valid_hash(pin["sha256"]), label)


def source_key(pin):
    shape(pin, PIN_KEYS, "context source")
    path = text(pin["path"], "context source path")
    require("\\" not in path and all(part not in ("", ".", "..") for part in path.split("/")),
            "context source path must be canonical and relative")
    return path, valid_hash(pin["sha256"])


def audit(request_path):
    value, base, request_source = request(request_path, REQUEST, ("schema", "scope", "context", "capture"))
    scope = shape(value["scope"], SCOPE_KEYS, "scope")
    for field in SCOPE_KEYS:
        text(scope[field], field)
    require(re.fullmatch(r"[0-9a-f]{40}", scope["candidate"]) is not None, "full Git candidate required")

    context_path, context_raw = load_pinned(value["context"], base, "frozen context")
    context = shape(decode(context_raw), ("schema", "candidate", "role", "pack", "references"), "frozen context")
    require(context["schema"] == CONTEXT, "unsupported frozen context schema")
    require(context["candidate"] == scope["candidate"] and context["role"] == scope["role"],
            "frozen context candidate or role mismatch")
    references = context["references"]
    require(isinstance(references, list) and references, "frozen references required")
    sources = {}
    for kind, pins in (("pack", [context["pack"]]), ("reference", references)):
        for pin in pins:
            path, digest = source_key(pin)
            require(path not in sources, "duplicate context source path")
            read_pinned(context_path.parent / path, digest, f"{kind} {path}")
            sources[path] = {**pin, "kind": kind, "readable": True, "delivered_events": [],
                             "read_events": [], "citation_events": []}

    capture_source = None
    if value["capture"] is not None:
        capture_path, capture_raw = load_pinned(value["capture"], base, "saved capture")
        capture_source = {"path": str(capture_path), "sha256": value["capture"]["sha256"]}
        capture = shape(decode(capture_raw), ("schema", "scope", "context_sha256", "events"), "saved capture")
        require(capture["schema"] == CAPTURE, "unsupported saved capture schema")
        require(capture["scope"] == scope, "saved capture candidate, role, session or turn mismatch")
        require(capture["context_sha256"] == value["context"]["sha256"], "saved capture frozen context mismatch")
        require(isinstance(capture["events"], list), "saved capture events must be a list")
        witnessed = {}
        for index, event in enumerate(capture["events"], 1):
            shape(event, ("kind", "source", "text"), f"event {index}")
            kind = event["kind"]
            require(kind in ("delivered", "read", "citation"), f"event {index} kind unsupported")
            path, digest = source_key(event["source"])
            require(path in sources and sources[path]["sha256"] == digest,
                    f"event {index} source is outside the frozen context")
            require(isinstance(event["text"], str), f"event {index} text required")
            content = event["text"].encode("utf-8")
            if kind == "citation":
                require(bool(content.strip()), f"event {index} citation quote required")
                require(path in witnessed, f"event {index} citation has no prior delivery or read")
                require(content in witnessed[path], f"event {index} citation quote is unsupported")
            else:
                require(sha(content) == digest, f"event {index} delivery or read bytes differ from source")
                witnessed[path] = content
            sources[path][f"{kind}_events"].append(index)

    for source in sources.values():
        observed = source["delivered_events"] or source["read_events"]
        source["exposure"] = "observed_in_saved_capture" if observed else "unobserved"
    return {
        "schema": RESULT,
        "status": "checked",
        "request": request_source,
        "context": {"path": str(context_path), "sha256": value["context"]["sha256"]},
        "capture": capture_source,
        "scope": scope,
        "sources": list(sources.values()),
        "independent_judgment": None,
        "authority_granted": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.request)
    except (OSError, ValueError) as exc:
        print(json.dumps({"schema": RESULT, "status": "rejected", "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
