#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false, reportUnusedCallResult=false

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from agent_company_agent_registry import desired_agents
from agent_company_agents import compile_agents
from agent_company_core_sync import build_sync_status, invalidate_sync_status, isolated_legacy_fixture_override
from agent_company_deps import (
    JsonValue,
    lock_json,
    record_json,
    resolve_dependency,
    run_git,
)
from agent_company_install_faults import corrupt_staged_target
from agent_company_install_fs import ensure_regular_tree, list_files, sha256_file
from agent_company_install_managed_fs import replace_managed
from agent_company_install_types import (
    InstallError,
    InstallPaths,
    InstallTarget,
    StagedGeneration,
)
from agent_company_skill_registry import SkillStage, stage_skills

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
COPY_ENTRIES: Final[tuple[str, ...]] = (
    "agents",
    "skills",
    "policies",
    "workflows",
    "scripts",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "LICENSE",
    "VERSION",
    "agent-company.deps.json",
)
SKIP_DIRS: Final[set[str]] = {"__pycache__", ".pytest_cache"}


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    snapshot_id: str
    agent_ref: str
    dependency: dict[str, JsonValue]
    source_hash: str


@dataclass(frozen=True, slots=True)
class CoreSyncBlocked(Exception):
    status: dict[str, JsonValue]


def agent_commit() -> str:
    commit = run_git(["rev-parse", "HEAD"], cwd=ROOT)
    status = run_git(["status", "--porcelain"], cwd=ROOT)
    if not commit.ok or not status.ok:
        raise InstallError("source_unavailable", commit.stderr or status.stderr)
    if status.stdout and os.environ.get("AGENT_COMPANY_ALLOW_DIRTY") != "1":
        raise InstallError("dirty_worktree", "Agent Company worktree is dirty")
    return commit.stdout


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for entry in COPY_ENTRIES:
        source = root / entry
        paths = (source,) if source.is_file() else list_files(source)
        for path in paths:
            digest.update(str(path.relative_to(root)).encode())
            digest.update(sha256_file(path).encode())
    return digest.hexdigest()


def working_tree_hash() -> str:
    return tree_hash(ROOT)


def snapshot_identity(*, require_core_sync: bool = True) -> SourceIdentity:
    dependency = None
    if require_core_sync and not isolated_legacy_fixture_override():
        core_sync = build_sync_status()
        activation = core_sync.get("activation")
        if not isinstance(activation, dict) or activation.get("allowed") is not True:
            raise CoreSyncBlocked(core_sync)
        dependency = resolve_dependency()
        layers = core_sync.get("layers")
        source = layers.get("core_source_candidate") if isinstance(layers, dict) else None
        if (
            not isinstance(source, dict)
            or dependency.worktree_status != "clean"
            or source.get("commit") != dependency.commit
            or source.get("content_sha256") != dependency.content_sha256
            or source.get("ref") != str(Path(dependency.git_root).resolve())
        ):
            raise CoreSyncBlocked(
                invalidate_sync_status(
                    core_sync,
                    state="source_runtime_diverged",
                    error="source_changed_after_preflight",
                )
            )
    dependency = dependency or resolve_dependency()
    agent_ref = agent_commit()
    source_hash = working_tree_hash()
    dependency_ref = dependency.content_sha256 or dependency.commit
    snapshot_id = f"agent-{agent_ref[:12]}-{source_hash[:12]}-sejong-{dependency_ref[:12]}"
    return SourceIdentity(snapshot_id, agent_ref, record_json(dependency), source_hash)


def copy_entry(source: Path, target: Path) -> None:
    ensure_regular_tree(source)
    if source.is_dir():
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(*SKIP_DIRS))
    elif source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    else:
        raise InstallError("missing_source", f"missing managed source entry: {source}")


def stage_generation(
    paths: InstallPaths,
    transaction_id: str,
    identity: SourceIdentity,
) -> StagedGeneration:
    snapshot_id = identity.snapshot_id
    agent_ref = identity.agent_ref
    dependency = identity.dependency
    source_hash = identity.source_hash
    with tempfile.TemporaryDirectory(prefix=f"agent-company-{transaction_id}-") as temp_dir:
        transaction = Path(temp_dir) / "stage"
        repo = transaction / "snapshot" / "repo"
        for entry in COPY_ENTRIES:
            copy_entry(ROOT / entry, repo / entry)
        if tree_hash(repo) != source_hash or working_tree_hash() != source_hash:
            raise InstallError("source_changed", "Agent Company source changed while staging")
        lock = resolve_dependency()
        if record_json(lock) != dependency:
            raise InstallError("source_changed", "King Sejong source changed after Core synchronization preflight")
        installed_lock = repo / "agent-company.lock.json"
        if lock.worktree_status == "clean":
            installed_lock.write_text(
                json.dumps(lock_json(lock), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            copy_entry(ROOT / "agent-company.lock.json", installed_lock)
        snapshot = transaction / "snapshot"
        files: dict[str, str] = {
            str(path.relative_to(snapshot)): sha256_file(path)
            for path in list_files(snapshot)
        }
        manifest_files: dict[str, JsonValue] = {}
        manifest_files.update(files)
        manifest: dict[str, JsonValue] = {"schema_version": "0.2", "snapshot_id": snapshot_id, "agent_company_commit": agent_ref, "king_sejong": dependency, "files": manifest_files}
        (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        files["manifest.json"] = sha256_file(snapshot / "manifest.json")
        compile_agents(repo / "agents", transaction / "compiled-agents")
        staged_skills = stage_skills(repo, transaction / "compiled-skills", SkillStage(agent_ref, snapshot_id))
        staged_agents = desired_agents(transaction / "compiled-agents")
        runtime_relative = f"agent-company/staging/{transaction_id}"
        replace_managed(paths, transaction, runtime_relative)
    runtime = paths.codex_home / runtime_relative
    corrupt_staged_target(runtime)
    skills = tuple(InstallTarget(target.relative, runtime / "compiled-skills" / Path(target.relative).name, target.expected_hash, target.kind) for target in staged_skills)
    agents = tuple(InstallTarget(target.relative, runtime / "compiled-agents" / Path(target.relative).name, target.expected_hash, target.kind) for target in staged_agents)
    return StagedGeneration(snapshot_id, agent_ref, files, skills, agents)
