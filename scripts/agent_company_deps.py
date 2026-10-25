#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Company-owned JSON types and safe local Git operations.

The historical module name is retained for pure Company consumers. No external
Core resolver, checkout, network fallback, dependency pin or executor lives here.
"""
from __future__ import annotations

import os
import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
GIT_TIMEOUT_SECONDS: Final[int] = 20
SAFE_GIT_CONFIG: Final[tuple[str, ...]] = (
    "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
    "-c", "submodule.recurse=false",
)

@dataclass(frozen=True, slots=True)
class DepsError(Exception):
    code: str
    detail: str
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"

@dataclass(frozen=True, slots=True)
class GitResult:
    ok: bool
    stdout: str
    stderr: str


def git_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_CONFIG_COUNT": "3",
            "GIT_CONFIG_KEY_0": "core.fsmonitor",
            "GIT_CONFIG_VALUE_0": "false",
            "GIT_CONFIG_KEY_1": "core.untrackedCache",
            "GIT_CONFIG_VALUE_1": "false",
            "GIT_CONFIG_KEY_2": "submodule.recurse",
            "GIT_CONFIG_VALUE_2": "false",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return env


def run_git(args: list[str], *, cwd: Path | None = None) -> GitResult:
    try:
        completed = subprocess.run(
            ["git", *SAFE_GIT_CONFIG, *args],
            cwd=cwd,
            env=git_environment(),
            text=True,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        return GitResult(False, "", f"git timed out after {exc.timeout} seconds")
    except OSError as exc:
        return GitResult(False, "", f"git failed to start: {exc}")
    return GitResult(completed.returncode == 0, completed.stdout.strip(), completed.stderr.strip())


def working_tree_sha256(root: Path) -> str:
    """Hash one explicitly supplied local Git tree; never resolve dependencies."""
    files = run_git(["ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root)
    if not files.ok:
        raise DepsError("source_unavailable", files.stderr or "could not enumerate local files")
    digest = hashlib.sha256()
    for relative in sorted(filter(None, files.stdout.split("\0"))):
        path = root / relative
        if not path.is_file():
            continue
        digest.update(relative.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()
