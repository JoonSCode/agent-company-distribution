#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# Imported by agent_company_bootstrap.py; validate with test_agent_company_bootstrap.py.
# ──────────────────

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from agent_company_deps import SAFE_GIT_CONFIG, git_environment

type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
SHA: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
MARKER: Final[str] = "agent-company-managed-source.json"
CONTAINER_MARKER: Final[str] = ".agent-company-managed-sources"
KINDS: Final[frozenset[str]] = frozenset({"agent-company", "king-sejong"})
EXPECTED_ORIGINS: Final[dict[str, frozenset[str]]] = {
    "agent-company": frozenset({
        "https://github.com/JoonSCode/agent-company.git",
        "https://github.com/JoonSCode/agent-company-distribution.git",
    }),
    "king-sejong": frozenset({"https://github.com/JoonSCode/king-sejong.git"}),
}


class BootstrapError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class SourceSpec:
    kind: str
    origin: str
    commit: str
    clone_source: str | None = None


@dataclass(frozen=True, slots=True)
class CommandRequest:
    argv: tuple[str, ...]
    cwd: Path | None = None
    env: dict[str, str] | None = None
    error_code: str = "command_failed"


def command(request: CommandRequest) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(request.argv, cwd=request.cwd, env=request.env, text=True, capture_output=True, check=False, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BootstrapError("command_failed", f"{request.argv[0]}: {exc}") from exc


def checked(request: CommandRequest) -> str:
    result = command(request)
    if result.returncode != 0:
        raise BootstrapError(request.error_code, result.stderr.strip() or result.stdout.strip() or "no output")
    return result.stdout.rstrip("\n")


def git(root: Path, *args: str, code: str = "source_unavailable") -> str:
    return checked(
        CommandRequest(
            ("git", *SAFE_GIT_CONFIG, "-C", str(root), *args),
            env=git_environment(),
            error_code=code,
        )
    )


def object_value(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise BootstrapError("invalid_lock", f"{label} must be an object")
    return value


def text_value(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise BootstrapError("invalid_lock", f"{label} must be text")
    return value


def valid_spec(spec: SourceSpec) -> None:
    if spec.kind not in KINDS or spec.origin not in EXPECTED_ORIGINS.get(spec.kind, frozenset()) or SHA.fullmatch(spec.commit) is None:
        raise BootstrapError("invalid_source_spec", spec.kind)
    if spec.clone_source is not None:
        clone = Path(spec.clone_source)
        if spec.clone_source.startswith("-") or (not clone.is_absolute() and spec.clone_source not in EXPECTED_ORIGINS[spec.kind]):
            raise BootstrapError("invalid_source_spec", f"unsafe clone source for {spec.kind}")


def lexical_home(codex_home: Path) -> Path:
    selected = Path(os.path.abspath(str(codex_home.expanduser())))
    if selected == Path(selected.anchor):
        raise BootstrapError("unsafe_path", "CODEX_HOME cannot be a filesystem root")
    if selected.exists() and selected.is_symlink():
        raise BootstrapError("unsafe_path", f"CODEX_HOME cannot be a symlink: {selected}")
    return selected


def managed_container(codex_home: Path, *, create: bool) -> Path:
    current = lexical_home(codex_home)
    if current.exists():
        if not current.is_dir():
            raise BootstrapError("unsafe_path", f"CODEX_HOME is not a directory: {current}")
    elif create:
        current.mkdir(mode=0o700)
    else:
        return current
    for component in ("agent-company", "source-repos"):
        current /= component
        if current.exists() or current.is_symlink():
            if current.is_symlink() or not current.is_dir():
                raise BootstrapError("unsafe_path", f"managed source component is unsafe: {current}")
        elif create:
            current.mkdir(mode=0o700)
        else:
            return current
    marker = current / CONTAINER_MARKER
    if marker.exists() or marker.is_symlink():
        if marker.is_symlink() or not marker.is_file() or marker.read_text(encoding="utf-8") != "agent-company-source-repos/v0.1\n":
            raise BootstrapError("source_collision", f"managed source container marker differs: {marker}")
    elif any(current.iterdir()):
        raise BootstrapError("source_collision", f"unmanaged source container: {current}")
    elif create:
        marker.write_text("agent-company-source-repos/v0.1\n", encoding="utf-8")
        marker.chmod(0o600)
    return current


def source_target(codex_home: Path, spec: SourceSpec) -> Path:
    valid_spec(spec)
    root = lexical_home(codex_home) / "agent-company" / "source-repos"
    target = root / spec.kind / spec.commit
    if not target.is_relative_to(root):
        raise BootstrapError("unsafe_path", spec.kind)
    return target


def source_identity(root: Path) -> SourceSpec:
    resolved = root.expanduser().resolve()
    if git(resolved, "rev-parse", "--show-toplevel") != str(resolved):
        raise BootstrapError("source_unavailable", "Agent Company source must be a repository root")
    if git(resolved, "status", "--porcelain"):
        raise BootstrapError("dirty_source", "Agent Company source worktree is dirty")
    spec = SourceSpec(
        "agent-company",
        git(resolved, "remote", "get-url", "origin"),
        git(resolved, "rev-parse", "HEAD"),
        str(resolved),
    )
    valid_spec(spec)
    return spec


def core_spec(root: Path) -> SourceSpec:
    try:
        parsed: JsonValue = json.loads((root / "agent-company.lock.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BootstrapError("invalid_lock", "King Sejong fallback pin is unavailable") from exc
    lock = object_value(parsed, "lock")
    resolved = object_value(lock.get("resolved_dependencies"), "resolved_dependencies")
    king = object_value(resolved.get("king_sejong"), "king_sejong")
    fallback = object_value(king.get("github_ref_fallback"), "github_ref_fallback")
    clone_source: str | None = None
    local = king.get("local_develop_checkout")
    if isinstance(local, dict) and isinstance(local.get("git_root"), str):
        candidate = Path(local["git_root"]).expanduser()
        candidate = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        if candidate.is_dir():
            clone_source = str(candidate)
    spec = SourceSpec(
        "king-sejong",
        text_value(fallback.get("url"), "url"),
        text_value(fallback.get("resolved_commit"), "resolved_commit"),
        clone_source,
    )
    valid_spec(spec)
    return spec


def validate_materialized(target: Path, spec: SourceSpec) -> None:
    if target.is_symlink() or not target.is_dir() or (target / ".git").is_symlink():
        raise BootstrapError("source_collision", f"unsafe source path: {target}")
    marker = target / ".git" / MARKER
    if marker.is_symlink() or not marker.is_file():
        raise BootstrapError("source_collision", f"unmanaged source path: {target}")
    try:
        metadata: JsonValue = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BootstrapError("source_collision", f"unmanaged source path: {target}") from exc
    if metadata != {"commit": spec.commit, "kind": spec.kind, "origin": spec.origin}:
        raise BootstrapError("source_collision", f"managed source marker differs: {target}")
    if git(target, "rev-parse", "--show-toplevel") != str(target.resolve()):
        raise BootstrapError("source_collision", f"source root differs: {target}")
    if git(target, "remote", "get-url", "origin") != spec.origin or git(target, "rev-parse", "HEAD") != spec.commit:
        raise BootstrapError("source_collision", f"source identity differs: {target}")
    expected: dict[str, tuple[str, str]] = {}
    expected_directories: set[str] = set()
    for record in (item for item in git(target, "ls-tree", "-r", "-z", "HEAD").split("\0") if item):
        metadata, relative = record.split("\t", 1)
        mode, kind, blob = metadata.split(" ", 2)
        path = PurePosixPath(relative)
        if kind != "blob" or mode not in {"100644", "100755"} or path.is_absolute() or ".." in path.parts or ".git" in path.parts:
            raise BootstrapError("source_collision", f"unsupported pinned source entry: {relative}")
        expected[relative] = (mode, blob)
        expected_directories.update(parent.as_posix() for parent in path.parents if parent != PurePosixPath("."))
    seen: set[str] = set()
    pending = [target]
    while pending:
        directory = pending.pop()
        for candidate in directory.iterdir():
            if directory == target and candidate.name == ".git":
                continue
            relative = candidate.relative_to(target).as_posix()
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise BootstrapError("source_collision", f"source symlink differs from pin: {relative}")
            if stat.S_ISDIR(metadata.st_mode):
                if relative not in expected_directories:
                    raise BootstrapError("source_collision", f"extra source directory: {relative}")
                pending.append(candidate)
                continue
            pinned = expected.get(relative)
            if pinned is None or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise BootstrapError("source_collision", f"extra or unsafe source file: {relative}")
            content = candidate.read_bytes()
            digest = hashlib.sha1(usedforsecurity=False)
            digest.update(f"blob {len(content)}\0".encode())
            digest.update(content)
            mode = "100755" if metadata.st_mode & 0o111 else "100644"
            if (mode, digest.hexdigest()) != pinned:
                raise BootstrapError("source_collision", f"source bytes or mode differ: {relative}")
            seen.add(relative)
    if seen != set(expected):
        raise BootstrapError("source_collision", f"pinned source files are missing: {sorted(set(expected) - seen)}")


def materialize_source(codex_home: Path, spec: SourceSpec) -> Path:
    container = managed_container(codex_home, create=True)
    target = source_target(codex_home, spec)
    if target.exists() or target.is_symlink():
        validate_materialized(target, spec)
        return target
    kind_root = container / spec.kind
    if kind_root.exists() or kind_root.is_symlink():
        if kind_root.is_symlink() or not kind_root.is_dir():
            raise BootstrapError("unsafe_path", f"source kind path is unsafe: {kind_root}")
    else:
        kind_root.mkdir(mode=0o700)
    stage = Path(tempfile.mkdtemp(prefix=".bootstrap-", dir=kind_root))
    clone = stage / "repo"
    try:
        clone_source = spec.clone_source or spec.origin
        checked(CommandRequest(("git", *SAFE_GIT_CONFIG, "clone", "--no-checkout", "--origin", "origin", "--", clone_source, str(clone)), env=git_environment(), error_code="clone_failed"))
        checked(CommandRequest(("git", *SAFE_GIT_CONFIG, "-C", str(clone), "checkout", "--detach", spec.commit), env=git_environment(), error_code="checkout_failed"))
        checked(CommandRequest(("git", *SAFE_GIT_CONFIG, "-C", str(clone), "remote", "set-url", "origin", spec.origin), env=git_environment(), error_code="checkout_failed"))
        marker = clone / ".git" / MARKER
        marker.write_text(json.dumps({"commit": spec.commit, "kind": spec.kind, "origin": spec.origin}, sort_keys=True) + "\n", encoding="utf-8")
        marker.chmod(0o600)
        validate_materialized(clone, spec)
        if target.exists() or target.is_symlink():
            raise BootstrapError("source_collision", f"source appeared during staging: {target}")
        os.replace(clone, target)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return target
