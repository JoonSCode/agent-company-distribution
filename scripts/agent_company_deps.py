#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/agent_company_deps.py
# 3. Or run with system Python when stdlib-only execution is preferred:
#      python3 scripts/agent_company_deps.py
# ──────────────────

from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Mapping, assert_never


JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
type DependencyMode = Literal["auto", "local", "github"]

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DEPS_FILE: Final[Path] = ROOT / "agent-company.deps.json"
GIT_TIMEOUT_SECONDS: Final[int] = 20
KING_SEJONG_ORIGIN: Final[str] = "https://github.com/JoonSCode/king-sejong.git"
SAFE_GIT_CONFIG: Final[tuple[str, ...]] = (
    "-c", "core.fsmonitor=false",
    "-c", "core.untrackedCache=false",
    "-c", "submodule.recurse=false",
)


@dataclass(frozen=True, slots=True)
class DepsError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class DependencyConfig:
    local_path: Path
    github_url: str
    github_ref: str


@dataclass(frozen=True, slots=True)
class GitResult:
    ok: bool
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class DependencyRecord:
    selected_source: str
    commit: str
    local_path: str
    git_root: str
    branch: str
    worktree_status: str
    github_url: str
    github_ref: str
    github_resolved_commit: str
    content_sha256: str


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
    files = run_git(["ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root)
    if not files.ok:
        raise DepsError("dependency_resolution_failed", files.stderr or "could not enumerate dependency files")
    digest = hashlib.sha256()
    for relative in sorted(item for item in files.stdout.split("\0") if item):
        path = root / relative
        if not path.is_file():
            continue
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def json_object(value: JsonValue, field: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise DepsError("malformed_input", f"{field} must be an object")
    return value


def text_field(values: dict[str, JsonValue], field: str) -> str:
    value = values.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DepsError("malformed_input", f"{field} must be a non-empty string")
    return value


def dependency_mode(value: str) -> DependencyMode:
    if value == "auto":
        return "auto"
    if value == "local":
        return "local"
    if value == "github":
        return "github"
    raise DepsError("malformed_input", f"bad dependency mode: {value}")


def load_config(env: Mapping[str, str]) -> DependencyConfig:
    try:
        parsed: JsonValue = json.loads(DEPS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DepsError("malformed_input", f"missing {DEPS_FILE}") from exc
    except json.JSONDecodeError as exc:
        raise DepsError("malformed_input", f"invalid dependency manifest: {exc.msg}") from exc
    except OSError as exc:
        raise DepsError("malformed_input", f"could not read dependency manifest: {exc}") from exc
    root = json_object(parsed, "$")
    dependencies = json_object(root.get("dependencies"), "dependencies")
    king = json_object(dependencies.get("king_sejong"), "dependencies.king_sejong")
    local = json_object(king.get("local_develop_checkout"), "local_develop_checkout")
    github = json_object(king.get("github_ref_fallback"), "github_ref_fallback")
    local_path = env.get("AGENT_COMPANY_KING_SEJONG_LOCAL_PATH") or text_field(local, "path")
    github_url = env.get("AGENT_COMPANY_KING_SEJONG_GITHUB_URL") or text_field(github, "url")
    github_ref = env.get("AGENT_COMPANY_KING_SEJONG_GITHUB_REF") or text_field(github, "ref")
    return DependencyConfig(Path(local_path).expanduser(), github_url, github_ref)


def resolve_local(config: DependencyConfig) -> DependencyRecord | None:
    if not config.local_path.exists():
        return None
    git_root = run_git(["rev-parse", "--show-toplevel"], cwd=config.local_path)
    commit = run_git(["rev-parse", "HEAD"], cwd=config.local_path)
    branch = run_git(["branch", "--show-current"], cwd=config.local_path)
    status = run_git(["status", "--porcelain"], cwd=config.local_path)
    if not git_root.ok or not commit.ok or not status.ok:
        return None
    content_hash = working_tree_sha256(Path(git_root.stdout))
    if status.stdout:
        return DependencyRecord(
            "local_develop_checkout",
            commit.stdout,
            str(config.local_path),
            git_root.stdout,
            branch.stdout,
            "dirty",
            config.github_url,
            config.github_ref,
            "",
            content_hash,
        )
    return DependencyRecord(
        "local_develop_checkout",
        commit.stdout,
        str(config.local_path),
        git_root.stdout,
        branch.stdout,
        "clean",
        config.github_url,
        config.github_ref,
        "",
        content_hash,
    )


def resolve_github(config: DependencyConfig) -> DependencyRecord:
    if config.github_url != KING_SEJONG_ORIGIN or config.github_ref != "main":
        raise DepsError("dependency_resolution_failed", "GitHub fallback must use the canonical King Sejong main ref")
    remote = run_git(["ls-remote", "--", config.github_url, config.github_ref])
    if not remote.ok:
        raise DepsError("dependency_resolution_failed", remote.stderr or "git ls-remote failed")
    first_line = remote.stdout.splitlines()[0] if remote.stdout else ""
    commit = first_line.split()[0] if first_line else ""
    if len(commit) != 40:
        raise DepsError("dependency_resolution_failed", "GitHub fallback did not resolve to a commit")
    return DependencyRecord(
        "github_ref_fallback",
        commit,
        str(config.local_path),
        "",
        "",
        "not_used",
        config.github_url,
        config.github_ref,
        commit,
        "",
    )


def resolve_dependency(env: Mapping[str, str] | None = None) -> DependencyRecord:
    active_env = os.environ if env is None else env
    mode = dependency_mode(active_env.get("AGENT_COMPANY_DEP_MODE", "auto"))
    config = load_config(active_env)
    local = resolve_local(config)
    allow_dirty = active_env.get("AGENT_COMPANY_ALLOW_DIRTY_DEPENDENCY") == "1"
    match mode:
        case "local":
            if local is None:
                raise DepsError("dependency_resolution_failed", "local King Sejong checkout is unavailable")
            if local.worktree_status != "clean" and not allow_dirty:
                raise DepsError("dirty_worktree", "local King Sejong checkout is dirty")
            return local
        case "github":
            return resolve_github(config)
        case "auto":
            if local is not None and (local.worktree_status == "clean" or allow_dirty):
                return local
            return resolve_github(config)
        case unreachable:
            assert_never(unreachable)


def record_json(record: DependencyRecord) -> dict[str, JsonValue]:
    return {
        "schema_version": "0.1",
        "dependency": "king_sejong",
        "selected_source": record.selected_source,
        "commit": record.commit,
        "local_develop_checkout": {
            "path": record.local_path,
            "git_root": record.git_root,
            "branch": record.branch,
            "worktree_status": record.worktree_status,
            "commit": record.commit,
            "content_sha256": record.content_sha256,
            "reproducible": record.worktree_status == "clean",
            "inspectable": bool(record.git_root and record.commit),
        },
        "github_ref_fallback": {
            "url": record.github_url,
            "ref": record.github_ref,
            "resolved_commit": record.github_resolved_commit or record.commit,
        },
    }


def lock_json(record: DependencyRecord) -> dict[str, JsonValue]:
    return {
        "schema_version": "0.1",
        "lockfile_kind": "dependency_resolution",
        "resolved_dependencies": {"king_sejong": record_json(record)},
    }


def main() -> int:
    try:
        print(json.dumps(record_json(resolve_dependency()), indent=2, sort_keys=True))
    except DepsError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
