#!/usr/bin/env python3
"""Check or explicitly refresh the existing policy bindings, never enroll files."""
from __future__ import annotations

import argparse
import difflib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from unittest.mock import patch

import orca_contract as contract

BASELINE = "references/upstream/baseline.json"


def prepare(root, selected):
    contract.require(not root.is_symlink(), "package directory is a symlink")
    raw = contract.read(root, BASELINE)
    manifest = contract.decode(raw, "baseline")
    entries = manifest.get("policy_files")
    contract.require(isinstance(entries, list) and entries, "policy_files must be a nonempty list")
    seen = set()
    changes = []
    for item in entries:
        contract.require(isinstance(item, dict) and set(item) == {"path", "sha256"}, "invalid policy binding")
        path = contract.string(item["path"], "path")
        contract.require(path not in seen, f"duplicate policy path: {path}")
        seen.add(path)
        old = contract.sha(item["sha256"])
        new = contract.digest(contract.read(root, path))
        if old != new:
            changes.append((path, old, new))
    for path in sorted(set(selected)):
        contract.require(path in seen, f"unlisted policy path: {path}")
    # Preserve all bytes outside the hash values; refuse ambiguous representations.
    text = contract.utf8(raw, "baseline")
    for path, old, new in changes:
        pattern = r'("path"\s*:\s*' + re.escape(json.dumps(path, ensure_ascii=False)) + r'\s*,\s*"sha256"\s*:\s*")' + old + r'(")'
        text, count = re.subn(pattern, lambda m: m.group(1) + new + m.group(2), text)
        contract.require(count == 1, f"ambiguous policy binding representation: {path}")
    updated = text.encode("utf-8")
    candidate = contract.decode(updated, "candidate baseline")
    # Ensure no upstream or other metadata changed, even with duplicate paths elsewhere.
    expected = json.loads(json.dumps(manifest))
    for item in expected["policy_files"]:
        for path, _, new in changes:
            if item["path"] == path:
                item["sha256"] = new
    contract.require(candidate == expected, "unexpected baseline change")
    original_read = contract.read
    def candidate_read(package, relative):
        return updated if relative == BASELINE else original_read(package, relative)
    with patch.object(contract, "read", side_effect=candidate_read):
        contract.load_package(root)
    return raw, updated


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=("check", "sync"), default="check")
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--path", action="append", default=[], help="assert a path is already listed (never enroll it)")
    args = parser.parse_args(argv)
    try:
        before, after = prepare(args.package, args.path)
        if before == after:
            print("policy manifest: unchanged")
            return 0
        print("".join(difflib.unified_diff(before.decode().splitlines(keepends=True), after.decode().splitlines(keepends=True), fromfile="baseline", tofile="baseline (computed)")), end="")
        if args.action == "check":
            return 1
        target = args.package / BASELINE
        mode = stat.S_IMODE(target.stat().st_mode)
        fd, name = tempfile.mkstemp(prefix=".baseline-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                os.fchmod(stream.fileno(), mode)
                stream.write(after)
                stream.flush()
                os.fsync(stream.fileno())
            contract.require(contract.read(args.package, BASELINE) == before, "baseline changed during sync")
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        print("policy manifest: synced")
        return 0
    except (contract.Invalid, OSError, ValueError) as exc:
        print(f"policy manifest: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
