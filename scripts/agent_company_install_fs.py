#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import hashlib
import os
import shutil
import stat
from pathlib import Path
from types import TracebackType
from typing import Final

from agent_company_install_types import InstallError


SKIP_DIRS: Final[frozenset[str]] = frozenset({"__pycache__", ".pytest_cache"})
OPEN_DIR: Final[int] = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class TreeDigest:
    """Expose the narrow byte-only digest boundary used by tree hashing."""

    __slots__ = ("_digest",)

    def __init__(self) -> None:
        self._digest = hashlib.sha256()

    def update(self, value: bytes) -> None:
        self._digest.update(value)

    def hexdigest(self) -> str:
        return self._digest.hexdigest()


def safe_relative(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise InstallError("unsafe_path", f"unsafe managed relative path: {value}")
    return path


def codex_location(path: Path) -> tuple[Path, str] | None:
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser().absolute()
    try:
        relative = path.absolute().relative_to(home)
    except ValueError:
        return None
    return home, str(relative)


def ensure_regular_tree(path: Path, *, allow_missing: bool = False) -> None:
    if not path.exists():
        if allow_missing:
            return
        raise InstallError("missing_target", f"missing required path: {path}")
    if path.is_symlink():
        raise InstallError("unsafe_path", f"symlink is not allowed: {path}")
    items = (path,) if path.is_file() else tuple(path.rglob("*"))
    for item in items:
        if item.is_symlink() or (item.is_file() and item.stat().st_nlink != 1):
            raise InstallError("unsafe_path", f"unsafe linked path: {item}")


def list_files(root: Path) -> tuple[Path, ...]:
    return tuple(path for path in sorted(root.rglob("*")) if path.is_file() and not any(part in SKIP_DIRS for part in path.relative_to(root).parts))


def sha256_file(path: Path) -> str:
    location = codex_location(path)
    if location is not None:
        root, relative = location
        with anchored_parent(root, relative, create=False) as (parent_fd, name):
            return hash_at(parent_fd, name, "file")
    ensure_regular_tree(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_tree(root: Path) -> str:
    location = codex_location(root)
    if location is not None:
        codex_home, relative = location
        with anchored_parent(codex_home, relative, create=False) as (parent_fd, name):
            return hash_at(parent_fd, name, "dir")
    ensure_regular_tree(root)
    digest = hashlib.sha256()
    for path in list_files(root):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class AnchoredParent:
    """Owns nofollow directory descriptors for one managed target chain."""

    __slots__ = ("create", "descriptors", "relative", "root", "safe")

    def __init__(self, root: Path, relative: str, *, create: bool) -> None:
        self.root = root
        self.relative = relative
        self.safe = safe_relative(relative)
        self.create = create
        self.descriptors: list[int] = []

    def __enter__(self) -> tuple[int, str]:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            self.descriptors.append(os.open(self.root, OPEN_DIR))
            for part in self.safe.parent.parts:
                try:
                    descriptor = os.open(part, OPEN_DIR, dir_fd=self.descriptors[-1])
                except FileNotFoundError:
                    if not self.create:
                        raise InstallError("missing_target", f"managed parent is missing: {self.relative}") from None
                    os.mkdir(part, mode=0o700, dir_fd=self.descriptors[-1])
                    descriptor = os.open(part, OPEN_DIR, dir_fd=self.descriptors[-1])
                self.descriptors.append(descriptor)
        except InstallError:
            self.close()
            raise
        except OSError as exc:
            self.close()
            raise InstallError("unsafe_path", f"unsafe managed path chain: {self.relative}: {exc}") from exc
        return self.descriptors[-1], self.safe.name

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        for descriptor in reversed(self.descriptors):
            os.close(descriptor)
        self.descriptors.clear()


def anchored_parent(root: Path, relative: str, *, create: bool) -> AnchoredParent:
    return AnchoredParent(root, relative, create=create)


def entry_stat(parent_fd: int, name: str) -> os.stat_result | None:
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(metadata.st_mode) or not (stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)):
        raise InstallError("unsafe_path", f"managed target is not regular: {name}")
    if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1:
        raise InstallError("unsafe_path", f"managed target is hard-linked: {name}")
    return metadata


def remove_at(parent_fd: int, name: str) -> None:
    metadata = entry_stat(parent_fd, name)
    if metadata is None:
        return
    if stat.S_ISREG(metadata.st_mode):
        os.unlink(name, dir_fd=parent_fd)
        return
    child_fd = os.open(name, OPEN_DIR, dir_fd=parent_fd)
    try:
        for child in os.listdir(child_fd):
            remove_at(child_fd, child)
    finally:
        os.close(child_fd)
    os.rmdir(name, dir_fd=parent_fd)


def copy_path_at(source: Path, parent_fd: int, name: str) -> None:
    ensure_regular_tree(source)
    remove_at(parent_fd, name)
    mode = source.stat().st_mode & 0o777
    if source.is_file():
        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent_fd)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(source.read_bytes())
        return
    os.mkdir(name, mode=mode, dir_fd=parent_fd)
    child_fd = os.open(name, OPEN_DIR, dir_fd=parent_fd)
    try:
        for child in sorted(source.iterdir()):
            copy_path_at(child, child_fd, child.name)
    finally:
        os.close(child_fd)


def hash_at(parent_fd: int, name: str, kind: str) -> str:
    metadata = entry_stat(parent_fd, name)
    if metadata is None:
        raise InstallError("missing_target", f"managed target disappeared: {name}")
    if kind == "file":
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        with os.fdopen(descriptor, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    child_fd = os.open(name, OPEN_DIR, dir_fd=parent_fd)
    try:
        digest = TreeDigest()
        hash_tree_fd(child_fd, "", digest)
        return digest.hexdigest()
    finally:
        os.close(child_fd)


def hash_tree_fd(directory_fd: int, prefix: str, digest: TreeDigest) -> None:
    for name in sorted(os.listdir(directory_fd)):
        metadata = entry_stat(directory_fd, name)
        if metadata is None:
            raise InstallError("missing_target", f"managed target disappeared: {name}")
        relative = f"{prefix}/{name}" if prefix else name
        if stat.S_ISDIR(metadata.st_mode):
            child_fd = os.open(name, OPEN_DIR, dir_fd=directory_fd)
            try:
                hash_tree_fd(child_fd, relative, digest)
            finally:
                os.close(child_fd)
            continue
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        with os.fdopen(descriptor, "rb") as handle:
            digest.update(relative.encode())
            digest.update(b"\0")
            digest.update(handle.read())
            digest.update(b"\0")


def copy_at_at(source_fd: int, source_name: str, target_fd: int, target_name: str) -> None:
    metadata = entry_stat(source_fd, source_name)
    if metadata is None:
        raise InstallError("missing_target", f"managed source disappeared: {source_name}")
    remove_at(target_fd, target_name)
    mode = metadata.st_mode & 0o777
    if stat.S_ISREG(metadata.st_mode):
        reader = os.open(source_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=source_fd)
        writer = os.open(target_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=target_fd)
        with os.fdopen(reader, "rb") as source_handle, os.fdopen(writer, "wb") as target_handle:
            shutil.copyfileobj(source_handle, target_handle)
        return
    os.mkdir(target_name, mode=mode, dir_fd=target_fd)
    source_child = os.open(source_name, OPEN_DIR, dir_fd=source_fd)
    target_child = os.open(target_name, OPEN_DIR, dir_fd=target_fd)
    try:
        for child in sorted(os.listdir(source_child)):
            copy_at_at(source_child, child, target_child, child)
    finally:
        os.close(source_child)
        os.close(target_child)
