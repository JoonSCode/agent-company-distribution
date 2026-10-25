#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from agent_company_install_fs import safe_relative, sha256_file, sha256_tree
from agent_company_install_io import read_json, write_json
from agent_company_install_types import BackupEntry, InstallError, InstallPaths, JsonValue, ManagedIndex, TransactionSpec


INDEX_VERSION: Final[str] = "agent-company.managed-install/v0.2"
SAFE_NAME: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$|^agent-company-[a-z0-9]+(?:-[a-z0-9]+)*\.toml$")
SAFE_HASH: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


def text_map(value: JsonValue, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise InstallError("malformed_index", f"{field} must be an object")
    result: dict[str, str] = {}
    for name, digest in value.items():
        if SAFE_NAME.fullmatch(name) is None or not isinstance(digest, str) or SAFE_HASH.fullmatch(digest) is None:
            raise InstallError("malformed_index", f"unsafe {field} entry: {name}")
        result[name] = digest
    return result


def load_index(paths: InstallPaths) -> ManagedIndex | None:
    path = paths.root / "managed-index.json"
    if not path.exists():
        return None
    payload = read_json(path, "malformed_index")
    if set(payload) != {"schema_version", "snapshot_id", "skills", "agents"} or payload.get("schema_version") != INDEX_VERSION:
        raise InstallError("malformed_index", "unsupported managed index version")
    snapshot_id = payload.get("snapshot_id")
    if not isinstance(snapshot_id, str) or SAFE_NAME.fullmatch(snapshot_id) is None:
        raise InstallError("malformed_index", "managed index snapshot_id is invalid")
    return ManagedIndex(snapshot_id, text_map(payload.get("skills"), "skills"), text_map(payload.get("agents"), "agents"))


def write_index(paths: InstallPaths, index: ManagedIndex) -> None:
    write_json(
        paths.root / "managed-index.json",
        {
            "schema_version": INDEX_VERSION,
            "snapshot_id": index.snapshot_id,
            "skills": index.skills,
            "agents": index.agents,
        },
    )


def entries_json(entries: tuple[BackupEntry, ...]) -> list[JsonValue]:
    return [
        {"relative": entry.relative, "kind": entry.kind, "backup": entry.backup, "mode": entry.mode, "content_sha256": entry.content_sha256}
        for entry in entries
    ]


def allowed_backup_target(relative: str) -> bool:
    parts = safe_relative(relative).parts
    if relative in {"agent-company/active.json", "agent-company/installed-hashes.json", "agent-company/managed-index.json", "agent-company/completion-hook.json", "agent-company/claude-entry.json", "agent-company/claude-entry"}:
        return True
    if len(parts) == 3 and parts[:2] == ("agent-company", "snapshots") and SAFE_NAME.fullmatch(parts[2]) is not None:
        return True
    if len(parts) == 2 and parts[0] == "skills" and SAFE_NAME.fullmatch(parts[1]) is not None:
        return True
    return len(parts) == 2 and parts[0] == "agents" and parts[1].startswith("agent-company-") and parts[1].endswith(".toml") and SAFE_NAME.fullmatch(parts[1]) is not None


def parse_entries(path: Path, expected: TransactionSpec | None = None) -> tuple[BackupEntry, ...]:
    payload = read_json(path, "corrupt_recovery")
    if set(payload) != {"schema_version", "transaction_id", "action", "snapshot_id", "entries"} or payload.get("schema_version") != "agent-company.install-backup/v0.2":
        raise InstallError("corrupt_recovery", "backup manifest shape or version is invalid")
    transaction_id = payload.get("transaction_id")
    action = payload.get("action")
    snapshot_id = payload.get("snapshot_id")
    if not isinstance(transaction_id, str) or not isinstance(action, str) or not isinstance(snapshot_id, str):
        raise InstallError("corrupt_recovery", "backup transaction metadata is invalid")
    if expected is not None and (transaction_id, action, snapshot_id) != (expected.transaction_id, expected.action, expected.snapshot_id):
        raise InstallError("corrupt_recovery", "backup transaction id does not match journal")
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        raise InstallError("corrupt_recovery", "backup entries must be a list")
    entries: list[BackupEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise InstallError("corrupt_recovery", "malformed backup entry")
        relative = raw.get("relative")
        kind = raw.get("kind")
        backup = raw.get("backup")
        mode = raw.get("mode")
        content_sha256 = raw.get("content_sha256")
        if not isinstance(relative, str) or not isinstance(kind, str) or not isinstance(backup, str) or not isinstance(mode, int) or not isinstance(content_sha256, str):
            raise InstallError("corrupt_recovery", "malformed backup entry")
        if kind not in {"absent", "file", "dir"} or not allowed_backup_target(relative):
            raise InstallError("corrupt_recovery", f"unsupported backup kind: {kind}")
        if kind == "absent":
            if backup or content_sha256 or mode != 0:
                raise InstallError("corrupt_recovery", "absent backup entry carries content")
        else:
            if not backup.startswith("payload/") or SAFE_HASH.fullmatch(content_sha256) is None or not 0 <= mode <= 0o777:
                raise InstallError("corrupt_recovery", "backup metadata is unsafe")
            source = path.parent / safe_relative(backup)
            actual = sha256_tree(source) if kind == "dir" else sha256_file(source)
            if actual != content_sha256:
                raise InstallError("corrupt_recovery", f"backup payload digest mismatch: {relative}")
        entries.append(BackupEntry(relative, kind, backup, mode, content_sha256))
    if len({entry.relative for entry in entries}) != len(entries):
        raise InstallError("corrupt_recovery", "backup contains duplicate targets")
    if expected is not None and expected.action in {"install", "update"}:
        snapshots = [Path(entry.relative).name for entry in entries if entry.relative.startswith("agent-company/snapshots/")]
        if snapshots != [expected.snapshot_id]:
            raise InstallError("corrupt_recovery", "backup snapshot target does not match journal")
    return tuple(entries)
