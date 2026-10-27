#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from agent_company_install_fs import (
    anchored_parent,
    ensure_regular_tree,
    hash_at,
    safe_relative,
)
from agent_company_install_faults import midpoint
from agent_company_install_managed_fs import atomic_write_path, copy_managed, read_path_bytes, remove_managed
from agent_company_install_types import BackupEntry, InstallError, InstallPaths, JsonValue


def install_paths(codex_home: Path | None = None) -> InstallPaths:
    home = codex_home or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    root = home / "agent-company"
    state = root / "state"
    return InstallPaths(home, root, state, root / "staging", root / "snapshots", root / "rollback", state / "install-transaction.json", state / "transactions")


def atomic_write(path: Path, content: bytes, mode: int = 0o600) -> None:
    if atomic_write_path(path, content, mode):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_regular_tree(path.parent)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(content)
    temporary.chmod(mode)
    os.replace(temporary, path)


def write_json(path: Path, value: dict[str, JsonValue]) -> None:
    atomic_write(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def read_json(path: Path, code: str = "malformed_input") -> dict[str, JsonValue]:
    try:
        parsed: JsonValue = json.loads(read_path_bytes(path).decode())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstallError(code, f"could not parse {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise InstallError(code, f"JSON root must be an object: {path}")
    return parsed


def backup_targets(paths: InstallPaths, transaction: Path, relatives: tuple[str, ...]) -> tuple[BackupEntry, ...]:
    entries: list[BackupEntry] = []
    payload = transaction / "payload"
    transaction_relative = str(transaction.relative_to(paths.codex_home))
    for index, relative in enumerate(dict.fromkeys(relatives)):
        backup = payload / str(index)
        backup_relative = f"{transaction_relative}/payload/{index}"
        try:
            with anchored_parent(paths.codex_home, relative, create=False) as (parent_fd, name):
                metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                kind = "dir" if stat.S_ISDIR(metadata.st_mode) else "file"
                mode = metadata.st_mode & 0o777
                digest = hash_at(parent_fd, name, kind)
                copy_managed(paths, relative, backup_relative)
                entries.append(BackupEntry(relative, kind, str(backup.relative_to(transaction)), mode, digest))
        except FileNotFoundError:
            entries.append(BackupEntry(relative, "absent", "", 0, ""))
        except InstallError as exc:
            if exc.code == "missing_target":
                entries.append(BackupEntry(relative, "absent", "", 0, ""))
            else:
                raise
        if index == 0:
            midpoint("backup_entries")
    return tuple(entries)


def restore_entries(paths: InstallPaths, base: Path, entries: tuple[BackupEntry, ...]) -> None:
    from agent_company_claude_entry import preflight_restore
    preflight_restore(paths, base, entries)
    for entry in reversed(entries):
        if entry.relative == "agent-company/claude-entry.json":
            from agent_company_claude_entry import restore_link
            before = None if entry.kind == 'absent' else read_path_bytes(base / safe_relative(entry.backup))
            restore_link(paths.codex_home, before)
        if entry.relative == "agent-company/completion-hook.json":
            from agent_company_completion_hook_install import restore_hook
            before = None if entry.kind == "absent" else read_path_bytes(base / safe_relative(entry.backup))
            restore_hook(paths, before)
        if entry.relative == "agent-company/routing-hook.json":
            from agent_company_routing_hook_install import restore_hook
            before = None if entry.kind == "absent" else read_path_bytes(base / safe_relative(entry.backup))
            restore_hook(paths, before)
        if entry.kind == "absent":
            try:
                remove_managed(paths, entry.relative)
            except InstallError as exc:
                if exc.code != "missing_target":
                    raise
            continue
        source = base / safe_relative(entry.backup)
        source_relative = str(source.relative_to(paths.codex_home))
        copy_managed(paths, source_relative, entry.relative)
        with anchored_parent(paths.codex_home, entry.relative, create=False) as (parent_fd, name):
            os.chmod(name, entry.mode, dir_fd=parent_fd, follow_symlinks=False)
