#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Import from Todo 4 runtime modules; this file has no standalone command.
# 3. Tests: python3 scripts/test_agent_company_privacy_security.py
# ─────────────────

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

import errno
import fcntl
import hashlib
import json
import os
import secrets
import stat
import threading
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, final, override

from agent_company_privacy import JsonObject


NOFOLLOW: Final[int] = getattr(os, "O_NOFOLLOW", 0)
DIRECTORY: Final[int] = getattr(os, "O_DIRECTORY", 0)
THREAD_LOCK: Final = threading.RLock()


@final
class StorageError(Exception):
    """Typed private-storage failure."""

    code: str
    detail: str

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)
        self.code = code
        self.detail = detail

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class PrivateDirectory:
    fd: int

    def _checked_existing(self, name: str) -> os.stat_result:
        try:
            before = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        except FileNotFoundError:
            raise
        if (
            stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid() or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
        ):
            raise StorageError("unsafe_path", "private file is not an owned regular file")
        return before

    def open_regular(self, name: str, flags: int, mode: int = 0o600) -> int:
        before: os.stat_result | None
        try:
            before = self._checked_existing(name)
        except FileNotFoundError:
            before = None
        try:
            descriptor = os.open(name, flags | NOFOLLOW, mode, dir_fd=self.fd)
        except FileNotFoundError:
            if not flags & os.O_CREAT:
                raise
            descriptor = os.open(name, flags | NOFOLLOW, mode, dir_fd=self.fd)
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.EISDIR, errno.ENOTDIR}:
                raise StorageError("unsafe_path", "private file path is unsafe") from exc
            raise
        after = os.fstat(descriptor)
        safe = stat.S_ISREG(after.st_mode) and after.st_uid == os.geteuid() and after.st_nlink == 1
        unchanged = before is None or (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
        if not safe or not unchanged:
            os.close(descriptor)
            raise StorageError("symlink_swap", "private file changed during open")
        if before is None:
            os.fchmod(descriptor, 0o600)
        return descriptor

    def read(self, name: str) -> bytes | None:
        try:
            descriptor = self.open_regular(name, os.O_RDONLY)
        except FileNotFoundError:
            return None
        with os.fdopen(descriptor, "rb") as handle:
            if os.fstat(handle.fileno()).st_nlink != 1:
                raise StorageError("hardlink_swap", "private file gained another link before read")
            return handle.read()

    def atomic_replace(self, name: str, payload: bytes) -> None:
        temporary = f".{name}.{secrets.token_hex(8)}.tmp"
        descriptor = self.open_regular(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                _ = handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            _ = os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
            descriptor = self.open_regular(name, os.O_RDONLY)
            os.close(descriptor)
            os.fsync(self.fd)
        finally:
            if temporary in self.names():
                os.unlink(temporary, dir_fd=self.fd)

    def remove(self, name: str) -> None:
        try:
            _ = self._checked_existing(name)
            os.unlink(name, dir_fd=self.fd)
            os.fsync(self.fd)
        except FileNotFoundError:
            return

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(os.listdir(self.fd)))


def _open_child(parent_fd: int, name: str) -> int:
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
    except FileExistsError as exc:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(before.st_mode):
            raise StorageError("unsafe_directory", "private directory component is not a directory") from exc
    else:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode) or before.st_uid != os.geteuid():
        raise StorageError("unsafe_directory", "private directory is not an owned real directory")
    descriptor = os.open(name, os.O_RDONLY | DIRECTORY | NOFOLLOW, dir_fd=parent_fd)
    after = os.fstat(descriptor)
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino) or after.st_uid != os.geteuid():
        os.close(descriptor)
        raise StorageError("directory_swap", "private directory changed during open")
    os.fchmod(descriptor, 0o700)
    return descriptor


@contextmanager
def private_directory(codex_home: Path, namespace: str) -> Generator[PrivateDirectory, None, None]:
    codex_home.mkdir(parents=True, exist_ok=True, mode=0o700)
    root_fd = os.open(codex_home, os.O_RDONLY | DIRECTORY | NOFOLLOW)
    company_fd = -1
    namespace_fd = -1
    try:
        company_fd = _open_child(root_fd, "agent-company")
        namespace_fd = _open_child(company_fd, namespace)
        yield PrivateDirectory(namespace_fd)
    finally:
        if namespace_fd >= 0:
            os.close(namespace_fd)
        if company_fd >= 0:
            os.close(company_fd)
        os.close(root_fd)


@contextmanager
def locked(directory: PrivateDirectory, name: str) -> Generator[None, None, None]:
    with THREAD_LOCK:
        descriptor = directory.open_regular(name, os.O_CREAT | os.O_RDWR)
        with os.fdopen(descriptor, "r+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


def quarantine(directory: PrivateDirectory, name: str, raw: bytes, reason: str) -> None:
    digest = hashlib.sha256(raw).hexdigest()
    metadata: JsonObject = {
        "format": "agent-company.corruption-quarantine/v0.2", "original_name": name,
        "sha256": digest, "size_bytes": len(raw), "reason": reason,
    }
    quarantine_fd = _open_child(directory.fd, "quarantine")
    try:
        child = PrivateDirectory(quarantine_fd)
        child.atomic_replace(f"{Path(name).stem}-{digest[:12]}.json", (json.dumps(metadata, sort_keys=True) + "\n").encode())
    finally:
        os.close(quarantine_fd)
    directory.remove(name)
