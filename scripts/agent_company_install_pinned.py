#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias, assert_never

from agent_company_install_fs import OPEN_DIR, anchored_parent, remove_at
from agent_company_install_types import InstallError, InstallPaths


@dataclass(frozen=True, slots=True)
class PinnedFile:
    name: str
    mode: int
    content: bytes


@dataclass(frozen=True, slots=True)
class PinnedDirectory:
    name: str
    mode: int
    entries: tuple["PinnedEntry", ...]


PinnedEntry: TypeAlias = PinnedFile | PinnedDirectory


def _identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_nlink,
        metadata.st_uid, metadata.st_size, metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _require_owned(metadata: os.stat_result, name: str, *, directory: bool) -> None:
    kind_matches = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not kind_matches or metadata.st_uid != os.getuid():
        raise InstallError("staged_source_drift", f"staged entry is unsafe: {name}")
    if not directory and metadata.st_nlink != 1:
        raise InstallError("staged_source_drift", f"staged file is linked: {name}")


def _capture_file(parent_fd: int, name: str) -> PinnedFile:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
    with os.fdopen(descriptor, "rb") as handle:
        before = os.fstat(handle.fileno())
        _require_owned(before, name, directory=False)
        content = handle.read()
        after = os.fstat(handle.fileno())
    if _identity(before) != _identity(after):
        raise InstallError("staged_source_drift", f"staged file changed while read: {name}")
    return PinnedFile(name, stat.S_IMODE(before.st_mode), content)


def _capture_directory(parent_fd: int, name: str) -> PinnedDirectory:
    descriptor = os.open(name, OPEN_DIR, dir_fd=parent_fd)
    try:
        return _capture_directory_fd(descriptor, name)
    finally:
        os.close(descriptor)


def _capture_directory_fd(descriptor: int, name: str) -> PinnedDirectory:
    before = os.fstat(descriptor)
    _require_owned(before, name, directory=True)
    names = tuple(sorted(os.listdir(descriptor)))
    entries = tuple(_capture_entry(descriptor, child) for child in names)
    after_names = tuple(sorted(os.listdir(descriptor)))
    after = os.fstat(descriptor)
    if names != after_names or _identity(before) != _identity(after):
        raise InstallError("staged_source_drift", f"staged directory changed while read: {name}")
    return PinnedDirectory(name, stat.S_IMODE(before.st_mode), entries)


def _capture_entry(parent_fd: int, name: str) -> PinnedEntry:
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            return _capture_directory(parent_fd, name)
        if stat.S_ISREG(metadata.st_mode):
            return _capture_file(parent_fd, name)
    except OSError as exc:
        raise InstallError("staged_source_drift", f"cannot pin staged entry: {name}") from exc
    raise InstallError("staged_source_drift", f"staged entry is not regular: {name}")


def pin_staged_source(
    paths: InstallPaths,
    source: Path,
    kind: str,
) -> PinnedEntry:
    try:
        relative = source.absolute().relative_to(paths.codex_home.absolute())
    except ValueError as exc:
        raise InstallError("staged_source_drift", "staged source escaped managed home") from exc
    try:
        with anchored_parent(paths.codex_home, str(relative), create=False) as (parent_fd, name):
            pinned = _capture_entry(parent_fd, name)
    except InstallError as exc:
        if exc.code == "staged_source_drift":
            raise
        raise InstallError("staged_source_drift", f"cannot pin staged source: {relative}") from exc
    if (kind == "file" and not isinstance(pinned, PinnedFile)) or (
        kind == "dir" and not isinstance(pinned, PinnedDirectory)
    ):
        raise InstallError("staged_source_drift", f"staged source kind changed: {relative}")
    if kind not in {"file", "dir"}:
        raise InstallError("staged_source_drift", f"invalid staged source kind: {kind}")
    return pinned


def pinned_digest(source: PinnedEntry) -> str:
    match source:
        case PinnedFile(content=content):
            return hashlib.sha256(content).hexdigest()
        case PinnedDirectory():
            payload = bytearray()
            _hash_entries(source.entries, "", payload)
            return hashlib.sha256(payload).hexdigest()
        case unreachable:
            assert_never(unreachable)


def _hash_entries(
    entries: tuple[PinnedEntry, ...],
    prefix: str,
    payload: bytearray,
) -> None:
    for entry in entries:
        relative = f"{prefix}/{entry.name}" if prefix else entry.name
        match entry:
            case PinnedFile(content=content):
                payload.extend(relative.encode())
                payload.extend(b"\0")
                payload.extend(content)
                payload.extend(b"\0")
            case PinnedDirectory(entries=children):
                _hash_entries(children, relative, payload)
            case unreachable:
                assert_never(unreachable)


def pinned_file_hashes(source: PinnedEntry) -> dict[str, str]:
    if not isinstance(source, PinnedDirectory):
        raise InstallError("staged_source_drift", "staged snapshot is not a directory")
    found: dict[str, str] = {}
    _collect_hashes(source.entries, "", found)
    return found


def _collect_hashes(
    entries: tuple[PinnedEntry, ...],
    prefix: str,
    found: dict[str, str],
) -> None:
    for entry in entries:
        relative = f"{prefix}/{entry.name}" if prefix else entry.name
        match entry:
            case PinnedFile(content=content):
                found[relative] = hashlib.sha256(content).hexdigest()
            case PinnedDirectory(entries=children):
                _collect_hashes(children, relative, found)
            case unreachable:
                assert_never(unreachable)


def pinned_shape(source: PinnedEntry) -> tuple[tuple[str, str, int], ...]:
    found: list[tuple[str, str, int]] = []
    _collect_shape((source,), "", found, root=True)
    return tuple(found)


def _collect_shape(
    entries: tuple[PinnedEntry, ...],
    prefix: str,
    found: list[tuple[str, str, int]],
    *,
    root: bool = False,
) -> None:
    for entry in entries:
        relative = "" if root else (f"{prefix}/{entry.name}" if prefix else entry.name)
        match entry:
            case PinnedFile(mode=mode):
                found.append(("file", relative, mode))
            case PinnedDirectory(mode=mode, entries=children):
                found.append(("dir", relative, mode))
                _collect_shape(children, relative, found)
            case unreachable:
                assert_never(unreachable)


def replace_with_pinned(
    paths: InstallPaths,
    source: PinnedEntry,
    relative: str,
) -> None:
    with anchored_parent(paths.codex_home, relative, create=True) as (parent_fd, name):
        remove_at(parent_fd, name)
        _write_entry(parent_fd, source, name)


def _write_entry(parent_fd: int, source: PinnedEntry, name: str) -> None:
    match source:
        case PinnedFile(mode=mode, content=content):
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                mode,
                dir_fd=parent_fd,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                os.fchmod(handle.fileno(), mode)
        case PinnedDirectory(mode=mode, entries=entries):
            os.mkdir(name, mode=mode, dir_fd=parent_fd)
            descriptor = os.open(name, OPEN_DIR, dir_fd=parent_fd)
            try:
                os.fchmod(descriptor, mode)
                for entry in entries:
                    _write_entry(descriptor, entry, entry.name)
            finally:
                os.close(descriptor)
        case unreachable:
            assert_never(unreachable)


def verify_installed_pinned(
    paths: InstallPaths,
    relative: str,
    expected: PinnedEntry,
) -> None:
    target = paths.codex_home / relative
    actual = pin_staged_source(
        paths,
        target,
        "file" if isinstance(expected, PinnedFile) else "dir",
    )
    if pinned_digest(actual) != pinned_digest(expected) or pinned_shape(actual) != pinned_shape(expected):
        raise InstallError("staged_source_drift", f"installed target mismatched staged bytes: {relative}")


__all__ = [
    "PinnedDirectory", "PinnedEntry", "PinnedFile", "pin_staged_source",
    "pinned_digest", "pinned_file_hashes", "pinned_shape",
    "replace_with_pinned", "verify_installed_pinned",
]
