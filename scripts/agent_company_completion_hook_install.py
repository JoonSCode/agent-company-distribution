#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Own one Stop command, preserving other owners' hooks during rollback too."""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import stat
import sys
import uuid
from pathlib import Path

from agent_company_install_fs import anchored_parent, entry_stat
from agent_company_install_types import InstallError, InstallPaths


REGISTRY = "agent-company/completion-hook.json"
HOOKS = "hooks.json"
SCRIPT = "skills/company-orchestration/scripts/completion_hook.py"
PREFIX = ": agent-company-completion-hook=v1; exec "
SCHEMA = "agent-company.completion-hook-install/v1"
MAX_BYTES = 2 * 1024 * 1024


def _read(paths: InstallPaths, relative: str) -> bytes | None:
    try:
        with anchored_parent(paths.codex_home, relative, create=False) as (parent, name):
            meta = entry_stat(parent, name)
            if meta is None:
                return None
            if not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.getuid() or meta.st_size > MAX_BYTES:
                raise InstallError("completion_hook_conflict", f"unsafe file: {relative}")
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            with os.fdopen(fd, "rb") as handle:
                actual = os.fstat(handle.fileno())
                if (actual.st_dev, actual.st_ino) != (meta.st_dev, meta.st_ino):
                    raise InstallError("completion_hook_conflict", f"file changed: {relative}")
                data = handle.read(MAX_BYTES + 1)
                final = os.fstat(handle.fileno())
                if len(data) > MAX_BYTES or (actual.st_size, actual.st_mtime_ns, actual.st_ctime_ns) != (final.st_size, final.st_mtime_ns, final.st_ctime_ns):
                    raise InstallError("completion_hook_conflict", f"file changed: {relative}")
                return data
    except InstallError as exc:
        if exc.code == "missing_target":
            return None
        raise


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _decode(raw: bytes | None) -> dict:
    if raw is None:
        return {}
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (ValueError, UnicodeError) as exc:
        raise InstallError("completion_hook_conflict", "invalid hook JSON") from exc
    if not isinstance(value, dict):
        raise InstallError("completion_hook_conflict", "hook JSON must be an object")
    return value


def _encode(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _atomic(paths: InstallPaths, relative: str, content: bytes, expected: bytes | None) -> None:
    # Anchored, no-follow CAS. The existing installer lock serializes Company
    # writers; unrelated editors can still conflict, so never silently rebase.
    with anchored_parent(paths.codex_home, relative, create=True) as (parent, name):
        if _read(paths, relative) != expected:
            raise InstallError("completion_hook_conflict", f"concurrent edit: {relative}")
        meta = entry_stat(parent, name)
        temp = f".{name}.company-{uuid.uuid4().hex}.tmp"
        mode = (meta.st_mode & 0o777) if meta is not None else 0o600
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            current = entry_stat(parent, name)
            identity = lambda s: None if s is None else (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if identity(meta) != identity(current) or _read(paths, relative) != expected:
                raise InstallError("completion_hook_conflict", f"concurrent edit: {relative}")
            os.replace(temp, name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:
                os.unlink(temp, dir_fd=parent)
            except FileNotFoundError:
                pass


def _registry_entry(paths: InstallPaths, raw: bytes | None) -> dict | None:
    if raw is None:
        return None
    value = _decode(raw)
    if set(value) != {"schema_version", "entry", "script_sha256"} or value["schema_version"] != SCHEMA:
        raise InstallError("completion_hook_conflict", "invalid owned hook registry")
    entry = value["entry"]
    if entry is None:
        if value["script_sha256"] is not None:
            raise InstallError("completion_hook_conflict", "inactive hook has a script digest")
        return None  # uninstall's recoverable intermediate state
    digest = value["script_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise InstallError("completion_hook_conflict", "invalid owned hook script digest")
    if not isinstance(entry, dict) or set(entry) != {"hooks"} or not isinstance(entry["hooks"], list) or len(entry["hooks"]) != 1:
        raise InstallError("completion_hook_conflict", "invalid owned hook entry")
    command = entry["hooks"][0]
    if not isinstance(command, dict) or set(command) != {"type", "command", "timeout"} or command.get("type") != "command" or command.get("timeout") != 30:
        raise InstallError("completion_hook_conflict", "invalid owned hook command")
    text = command.get("command")
    if not isinstance(text, str) or not text.startswith(PREFIX):
        raise InstallError("completion_hook_conflict", "invalid owned hook marker")
    try:
        args = shlex.split(text[len(PREFIX):])
    except ValueError as exc:
        raise InstallError("completion_hook_conflict", "invalid command quoting") from exc
    if len(args) != 4 or not Path(args[0]).is_absolute() or not Path(args[0]).name.startswith("python") or args[1:] != ["-B", str(paths.codex_home / SCRIPT), "Stop"] or text != PREFIX + shlex.join(args):
        raise InstallError("completion_hook_conflict", "owned hook command escaped its target")
    return entry


def desired_entry(paths: InstallPaths) -> dict:
    command = PREFIX + shlex.join([str(Path(sys.executable).resolve()), "-B", str(paths.codex_home / SCRIPT), "Stop"])
    return {"hooks": [{"type": "command", "command": command, "timeout": 30}]}


def _owned(document: dict) -> tuple[dict, list, list[dict]]:
    hooks = document.get("hooks", {})
    if not isinstance(hooks, dict):
        raise InstallError("completion_hook_conflict", "hooks must be an object")
    stop = hooks.get("Stop", [])
    if not isinstance(stop, list):
        raise InstallError("completion_hook_conflict", "Stop must be an array")
    found = []
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            raise InstallError("completion_hook_conflict", "hook event must be an array")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                raise InstallError("completion_hook_conflict", "invalid hook group")
            ours = any(isinstance(c, dict) and isinstance(c.get("command"), str) and c["command"].startswith(PREFIX) for c in entry["hooks"])
            if ours:
                if event != "Stop" or len(entry["hooks"]) != 1:
                    raise InstallError("completion_hook_conflict", "owned command moved or mixed with another owner")
                found.append(entry)
    if len(found) > 1:
        raise InstallError("completion_hook_conflict", "duplicate owned hook")
    return hooks, stop, found


def _plan(paths: InstallPaths, expected: dict | None, desired: dict | None, *, recovering: bool = False) -> tuple[bytes | None, bytes | None]:
    raw = _read(paths, HOOKS)
    doc = _decode(raw)
    hooks, stop, found = _owned(doc)
    actual = found[0] if found else None
    if actual != expected and not (recovering and actual == desired):
        raise InstallError("completion_hook_conflict", "owned hook changed; other hooks preserved")
    if actual == desired:
        return raw, raw
    updated = [entry for entry in stop if entry not in found]
    if desired is not None:
        updated.append(desired)
    hooks["Stop"] = updated
    doc["hooks"] = hooks
    return raw, _encode(doc)


def apply_hook(paths: InstallPaths, *, enabled: bool = True) -> None:
    before = _read(paths, REGISTRY)
    expected = _registry_entry(paths, before)
    # Keep the already reviewed command stable if the updater itself changes
    # interpreter. A different command would invalidate the host's hook trust.
    desired = (expected or desired_entry(paths)) if enabled else None
    raw, updated = _plan(paths, expected, desired)
    script = _read(paths, SCRIPT) if enabled else None
    if enabled and not script:
        raise InstallError("completion_hook_conflict", "installed completion hook is missing")
    # Persist the new entry before its external effect. Recovery accepts either
    # before or after entry and merges only our entry into the latest document.
    _atomic(paths, REGISTRY, _encode({"schema_version": SCHEMA, "entry": desired,
            "script_sha256": hashlib.sha256(script).hexdigest() if script is not None else None}), before)
    if updated != raw:
        assert updated is not None
        _atomic(paths, HOOKS, updated, raw)


def preflight_hook(paths: InstallPaths, *, enabled: bool = True) -> None:
    current = _registry_entry(paths, _read(paths, REGISTRY))
    _plan(paths, current, (current or desired_entry(paths)) if enabled else None)


def restore_hook(paths: InstallPaths, desired_registry: bytes | None) -> None:
    current_registry = _read(paths, REGISTRY)
    if current_registry is None and desired_registry is None:
        return  # no hook effect was started; foreign configuration is untouched
    current = _registry_entry(paths, current_registry)
    desired = _registry_entry(paths, desired_registry)
    raw, updated = _plan(paths, current, desired, recovering=True)
    if updated != raw:
        assert updated is not None
        _atomic(paths, HOOKS, updated, raw)


def verify_hook(paths: InstallPaths, expected_hash: str | None = None) -> dict:
    raw = _read(paths, REGISTRY)
    if expected_hash is not None and (raw is None or hashlib.sha256(raw).hexdigest() != expected_hash):
        raise InstallError("completion_hook_conflict", "owned hook registry digest changed")
    entry = _registry_entry(paths, raw)
    if entry is None:
        raise InstallError("completion_hook_conflict", "completion hook is not registered")
    _plan(paths, entry, entry)
    script = _read(paths, SCRIPT)
    if not script:
        raise InstallError("completion_hook_conflict", "installed completion hook is missing")
    if hashlib.sha256(script).hexdigest() != _decode(raw)["script_sha256"]:
        raise InstallError("completion_hook_conflict", "installed completion hook digest changed")
    return {"status": "ok", "event": "Stop", "registry_sha256": hashlib.sha256(raw).hexdigest(), "script_sha256": hashlib.sha256(script).hexdigest()}
