#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import json
import math
import os
import secrets
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from agent_company_install_fs import OPEN_DIR, anchored_parent, entry_stat, remove_at
from agent_company_install_types import InstallError, InstallPaths, JsonValue


LOCK_RELATIVE: Final[str] = "agent-company/state/install.lock"
DEFAULT_STALE_SECONDS: Final[float] = 3600.0
MAX_STALE_SECONDS: Final[float] = 604800.0
OWNER_FIELDS: Final[frozenset[str]] = frozenset({"pid", "token", "device", "inode"})


@dataclass(frozen=True, slots=True)
class InstallLock:
    path: Path
    token: str
    device: int
    inode: int


@dataclass(frozen=True, slots=True)
class BoundOwner:
    pid: int
    token: str
    device: int
    inode: int


@dataclass(frozen=True, slots=True)
class LegacyOwner:
    pid: int


type OwnerRecord = BoundOwner | LegacyOwner | None


def _stale_seconds() -> float:
    raw = os.environ.get("AGENT_COMPANY_LOCK_STALE_SECONDS", str(DEFAULT_STALE_SECONDS))
    try:
        value = float(raw)
    except ValueError as exc:
        raise InstallError("malformed_input", f"invalid stale lock seconds: {raw}") from exc
    if not math.isfinite(value) or value <= 0 or value > MAX_STALE_SECONDS:
        raise InstallError("malformed_input", f"invalid stale lock seconds: {raw}")
    return value


def _open_directory(parent_fd: int, name: str) -> int:
    try:
        return os.open(name, OPEN_DIR, dir_fd=parent_fd)
    except OSError as exc:
        raise InstallError("unsafe_path", f"could not open install lock directory: {exc}") from exc


def _json_owner(directory_fd: int) -> OwnerRecord:
    metadata = entry_stat(directory_fd, "owner.json")
    if metadata is None:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        raise InstallError("unsafe_path", "lock owner metadata is not a regular file")
    try:
        descriptor = os.open("owner.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        with os.fdopen(descriptor, "rb") as handle:
            try:
                payload: JsonValue = json.loads(handle.read().decode())
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None
    except OSError as exc:
        raise InstallError("unsafe_path", f"could not read lock owner metadata: {exc}") from exc
    if not isinstance(payload, dict):
        return None
    pid = payload.get("pid")
    token = payload.get("token")
    device = payload.get("device")
    inode = payload.get("inode")
    if (
        set(payload) == OWNER_FIELDS
        and type(pid) is int
        and isinstance(token, str)
        and type(device) is int
        and type(inode) is int
        and pid > 0
        and token != ""
        and device >= 0
        and inode > 0
    ):
        return BoundOwner(pid, token, device, inode)
    if set(payload) == {"pid"} and type(pid) is int and pid > 0:
        return LegacyOwner(pid)
    return None


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _existing_is_reclaimable(parent_fd: int, name: str, stale_seconds: float) -> bool:
    metadata = entry_stat(parent_fd, name)
    if metadata is None:
        return False
    if not stat.S_ISDIR(metadata.st_mode):
        raise InstallError("unsafe_path", "install lock is not a directory")
    directory_fd = _open_directory(parent_fd, name)
    try:
        owner = _json_owner(directory_fd)
    finally:
        os.close(directory_fd)
    if owner is None:
        return time.time() - metadata.st_mtime > stale_seconds
    return not _pid_is_alive(owner.pid)


def _write_owner(directory_fd: int, owner: BoundOwner) -> None:
    descriptor = os.open(
        "owner.json",
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory_fd,
    )
    payload = {"pid": owner.pid, "token": owner.token, "device": owner.device, "inode": owner.inode}
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def acquire_lock(paths: InstallPaths) -> InstallLock:
    stale_seconds = _stale_seconds()
    lock_path = paths.state / "install.lock"
    with anchored_parent(paths.codex_home, LOCK_RELATIVE, create=True) as (parent_fd, name):
        metadata = entry_stat(parent_fd, name)
        if metadata is not None:
            observed_identity = _identity(metadata)
            if not _existing_is_reclaimable(parent_fd, name, stale_seconds):
                raise InstallError("lock_held", f"install lock already exists at {lock_path}")
            current = entry_stat(parent_fd, name)
            if current is None or _identity(current) != observed_identity:
                raise InstallError("lock_held", f"install lock changed during acquisition at {lock_path}")
            remove_at(parent_fd, name)
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError as exc:
            raise InstallError("lock_held", f"install lock already exists at {lock_path}") from exc
        directory_fd = _open_directory(parent_fd, name)
        try:
            created = os.fstat(directory_fd)
            token = secrets.token_urlsafe(32)
            owner = BoundOwner(os.getpid(), token, created.st_dev, created.st_ino)
            _write_owner(directory_fd, owner)
        except OSError as exc:
            current = entry_stat(parent_fd, name)
            if current is not None and _identity(current) == _identity(os.fstat(directory_fd)):
                remove_at(parent_fd, name)
            raise InstallError("lock_failed", f"could not create install lock: {exc}") from exc
        finally:
            os.close(directory_fd)
    return InstallLock(lock_path, owner.token, owner.device, owner.inode)


def release_lock(paths: InstallPaths, handle: InstallLock) -> bool:
    try:
        with anchored_parent(paths.codex_home, LOCK_RELATIVE, create=False) as (parent_fd, name):
            metadata = entry_stat(parent_fd, name)
            if metadata is None or _identity(metadata) != (handle.device, handle.inode):
                return False
            if not stat.S_ISDIR(metadata.st_mode):
                raise InstallError("unsafe_path", "install lock is not a directory")
            directory_fd = _open_directory(parent_fd, name)
            try:
                owner = _json_owner(directory_fd)
            finally:
                os.close(directory_fd)
            if not isinstance(owner, BoundOwner):
                return False
            if owner.token != handle.token or (owner.device, owner.inode) != (handle.device, handle.inode):
                return False
            current = entry_stat(parent_fd, name)
            if current is None or _identity(current) != (handle.device, handle.inode):
                return False
            remove_at(parent_fd, name)
            return True
    except InstallError as exc:
        if exc.code == "missing_target":
            return False
        raise
