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
from agent_company_deps import JsonValue, run_git
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
    "launchd",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "LICENSE",
    "VERSION",
    "agent-company.deps.json",
    "agent-company.lock.json",
)
SKIP_DIRS: Final[set[str]] = {"__pycache__", ".pytest_cache"}


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    snapshot_id: str
    agent_ref: str
    source_hash: str


def agent_commit() -> str:
    commit = run_git(["rev-parse", "HEAD"], cwd=ROOT)
    status = run_git(["status", "--porcelain"], cwd=ROOT)
    if not commit.ok or not status.ok:
        raise InstallError("source_unavailable", commit.stderr or status.stderr)
    if status.stdout and os.environ.get("AGENT_COMPANY_ALLOW_DIRTY") != "1":
        raise InstallError("dirty_worktree", "Agent Company worktree is dirty")
    return commit.stdout


def copy_entries(root: Path) -> tuple[str, ...]:
    # Evaluators are development-only; public runtime never needs private evals.
    return COPY_ENTRIES + (("evals",) if (root / "evals").is_dir() else ())


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for entry in copy_entries(root):
        source = root / entry
        paths = (source,) if source.is_file() else list_files(source)
        for path in paths:
            digest.update(str(path.relative_to(root)).encode())
            digest.update(sha256_file(path).encode())
    return digest.hexdigest()


def working_tree_hash() -> str:
    return tree_hash(ROOT)


RUNTIME_CONTRACT: Final[str] = "orca-company-standalone/v1"


def snapshot_identity() -> SourceIdentity:
    agent_ref = agent_commit()
    source_hash = working_tree_hash()
    snapshot_id = f"agent-{agent_ref[:12]}-{source_hash[:12]}"
    return SourceIdentity(snapshot_id, agent_ref, source_hash)


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
    source_hash = identity.source_hash
    with tempfile.TemporaryDirectory(prefix=f"agent-company-{transaction_id}-") as temp_dir:
        transaction = Path(temp_dir) / "stage"
        repo = transaction / "snapshot" / "repo"
        for entry in copy_entries(ROOT):
            copy_entry(ROOT / entry, repo / entry)
        if tree_hash(repo) != source_hash or working_tree_hash() != source_hash:
            raise InstallError("source_changed", "Agent Company source changed while staging")
        snapshot = transaction / "snapshot"
        files: dict[str, str] = {
            str(path.relative_to(snapshot)): sha256_file(path)
            for path in list_files(snapshot)
        }
        manifest_files: dict[str, JsonValue] = {}
        manifest_files.update(files)
        manifest: dict[str, JsonValue] = {"schema_version": "0.2", "snapshot_id": snapshot_id, "agent_company_commit": agent_ref, "runtime_contract": RUNTIME_CONTRACT, "source_content_sha256": source_hash, "files": manifest_files}
        (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        files["manifest.json"] = sha256_file(snapshot / "manifest.json")
        compile_agents(repo / "agents", transaction / "compiled-agents", execution_home=paths.codex_home)
        staged_skills = stage_skills(repo, transaction / "compiled-skills", SkillStage(agent_ref, snapshot_id))
        staged_agents = desired_agents(transaction / "compiled-agents")
        runtime_relative = f"agent-company/staging/{transaction_id}"
        replace_managed(paths, transaction, runtime_relative)
    runtime = paths.codex_home / runtime_relative
    corrupt_staged_target(runtime)
    skills = tuple(InstallTarget(target.relative, runtime / "compiled-skills" / Path(target.relative).name, target.expected_hash, target.kind) for target in staged_skills)
    agents = tuple(InstallTarget(target.relative, runtime / "compiled-agents" / Path(target.relative).name, target.expected_hash, target.kind) for target in staged_agents)
    return StagedGeneration(snapshot_id, agent_ref, files, skills, agents)
