#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

from agent_company_install_fs import (
    anchored_parent,
    codex_location,
    copy_at_at,
    ensure_regular_tree,
    entry_stat,
    hash_at,
    remove_at,
    OPEN_DIR,
)
from agent_company_install_types import InstallError, InstallPaths


def copy_source_at(source: Path, parent_fd: int, name: str) -> None:
    ensure_regular_tree(source)
    remove_at(parent_fd, name)
    mode = source.stat().st_mode & 0o777
    if source.is_file():
        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent_fd)
        with source.open("rb") as source_handle, os.fdopen(descriptor, "wb") as target_handle:
            shutil.copyfileobj(source_handle, target_handle)
        return
    os.mkdir(name, mode=mode, dir_fd=parent_fd)
    child_fd = os.open(name, OPEN_DIR, dir_fd=parent_fd)
    try:
        for child in sorted(source.iterdir()):
            copy_source_at(child, child_fd, child.name)
    finally:
        os.close(child_fd)


def replace_managed(paths: InstallPaths, source: Path, relative: str) -> None:
    location = codex_location(source)
    if location is not None and location[0] == paths.codex_home.absolute():
        copy_managed(paths, location[1], relative)
        return
    with anchored_parent(paths.codex_home, relative, create=True) as (parent_fd, name):
        copy_source_at(source, parent_fd, name)


def copy_managed(paths: InstallPaths, source_relative: str, target_relative: str) -> None:
    with anchored_parent(paths.codex_home, source_relative, create=False) as (source_fd, source_name):
        with anchored_parent(paths.codex_home, target_relative, create=True) as (target_fd, target_name):
            copy_at_at(source_fd, source_name, target_fd, target_name)


def remove_managed(paths: InstallPaths, relative: str) -> None:
    with anchored_parent(paths.codex_home, relative, create=False) as (parent_fd, name):
        remove_at(parent_fd, name)


def hash_managed(paths: InstallPaths, relative: str, kind: str) -> str:
    with anchored_parent(paths.codex_home, relative, create=False) as (parent_fd, name):
        return hash_at(parent_fd, name, kind)


def ensure_managed_dir(paths: InstallPaths, relative: str, mode: int = 0o700) -> None:
    with anchored_parent(paths.codex_home, relative, create=True) as (parent_fd, name):
        metadata = entry_stat(parent_fd, name)
        if metadata is None:
            os.mkdir(name, mode=mode, dir_fd=parent_fd)
            return
        if not stat.S_ISDIR(metadata.st_mode):
            raise InstallError("unsafe_path", f"managed directory is not regular: {relative}")
        os.chmod(name, mode, dir_fd=parent_fd, follow_symlinks=False)


def require_managed_dir(paths: InstallPaths, relative: str) -> None:
    with anchored_parent(paths.codex_home, relative, create=False) as (parent_fd, name):
        metadata = entry_stat(parent_fd, name)
        if metadata is None or not stat.S_ISDIR(metadata.st_mode):
            raise InstallError("corrupt_recovery", f"managed directory is missing: {relative}")


def managed_exists(paths: InstallPaths, relative: str) -> bool:
    try:
        with anchored_parent(paths.codex_home, relative, create=False) as (parent_fd, name):
            return entry_stat(parent_fd, name) is not None
    except InstallError as exc:
        if exc.code == "missing_target":
            return False
        raise


def rename_managed(paths: InstallPaths, source_relative: str, target_relative: str) -> None:
    with anchored_parent(paths.codex_home, source_relative, create=False) as (source_fd, source_name):
        with anchored_parent(paths.codex_home, target_relative, create=True) as (target_fd, target_name):
            if entry_stat(target_fd, target_name) is not None:
                raise InstallError("stale_state", f"rename target already exists: {target_relative}")
            os.rename(source_name, target_name, src_dir_fd=source_fd, dst_dir_fd=target_fd)


def read_path_bytes(path: Path) -> bytes:
    location = codex_location(path)
    if location is None:
        ensure_regular_tree(path)
        return path.read_bytes()
    root, relative = location
    with anchored_parent(root, relative, create=False) as (parent_fd, name):
        metadata = entry_stat(parent_fd, name)
        if metadata is None or not stat.S_ISREG(metadata.st_mode):
            raise InstallError("missing_target", f"managed file is missing: {relative}")
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        with os.fdopen(descriptor, "rb") as handle:
            return handle.read()


def atomic_write_path(path: Path, content: bytes, mode: int) -> bool:
    location = codex_location(path)
    if location is None:
        return False
    root, relative = location
    with anchored_parent(root, relative, create=True) as (parent_fd, name):
        temporary = f".{name}.{os.getpid()}.tmp"
        remove_at(parent_fd, temporary)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent_fd)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
    return True
