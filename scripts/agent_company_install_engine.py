#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import hashlib
import os
import time
import uuid
from pathlib import Path
from typing import Final

from agent_company_agent_registry import plan_agents
from agent_company_deps import DepsError, JsonValue
from agent_company_install_apply import apply_snapshot, apply_targets, remove_target
from agent_company_install_fs import safe_relative, sha256_file
from agent_company_install_faults import before_phase, midpoint, race_staged_target
from agent_company_install_integrity import verify_all_staged_targets
from agent_company_install_io import read_json, write_json
from agent_company_install_managed_fs import hash_managed, remove_managed
from agent_company_install_source import ROOT, snapshot_identity, stage_generation
from agent_company_install_state import load_index, write_index
from agent_company_install_transaction import begin, capture, cleanup_success, phase, preserve_rollback, restore_transaction
from agent_company_install_types import ApplyBatch, GenerationCommit, InstallError, InstallPaths, InstallTarget, ManagedIndex, TransactionSpec
from agent_company_role_contract import NativeAgentError
from agent_company_skill_registry import SkillInstallError, SkillOwnership, plan_skills, skill_dirs


EXPECTED_AGENT_FILES: Final[tuple[str, ...]] = (
    "agent-company-design.toml",
    "agent-company-development.toml",
    "agent-company-founder.toml",
    "agent-company-marketing.toml",
    "agent-company-planning.toml",
    "agent-company-qa-release.toml",
)


def active_payload(paths: InstallPaths) -> dict[str, JsonValue] | None:
    path = paths.root / "active.json"
    return read_json(path, "stale_state") if path.exists() else None


def verify_prior(paths: InstallPaths, index: ManagedIndex | None) -> None:
    active = active_payload(paths)
    hashes_path = paths.root / "installed-hashes.json"
    if active is None:
        if index is not None or hashes_path.exists():
            raise InstallError("mixed_generation", "active, hash, and managed-index ledgers are incomplete")
        return
    if active is not None:
        schema_version = active.get("schema_version")
        if schema_version not in {"0.1", "0.2"}:
            raise InstallError("mixed_generation", "active ledger version is unsupported")
        snapshot_id = active.get("snapshot_id")
        if not isinstance(snapshot_id, str) or len(safe_relative(snapshot_id).parts) != 1:
            raise InstallError("stale_state", "active snapshot id is missing")
        hashes = read_json(hashes_path, "malformed_input")
        files = hashes.get("files")
        if not isinstance(files, dict):
            raise InstallError("malformed_hashes", "installed file hashes are missing")
        if hashes.get("snapshot_id") != snapshot_id:
            raise InstallError("mixed_generation", "active and installed-hash generations disagree")
        for relative, expected in files.items():
            if not isinstance(expected, str) or sha256_file(paths.snapshots / snapshot_id / safe_relative(relative)) != expected:
                raise InstallError("hash_mismatch", f"installed snapshot drift: {relative}")
        manifest_hash = sha256_file(paths.snapshots / snapshot_id / "manifest.json")
        if active.get("manifest_sha256") != manifest_hash:
            raise InstallError("mixed_generation", "active manifest digest disagrees with snapshot")
        if active.get("schema_version") == "0.2" and index is None:
            raise InstallError("mixed_generation", "v0.2 active generation has no managed index")
        if index is not None:
            if index.snapshot_id != snapshot_id:
                raise InstallError("mixed_generation", "active and managed-index generations disagree")
            index_hash = sha256_file(paths.root / "managed-index.json")
            if active.get("managed_index_sha256") != index_hash or hashes.get("managed_index_sha256") != index_hash:
                raise InstallError("managed_drift", "active/hash ledger disagrees with managed index")
            if hashes.get("skills") != index.skills or hashes.get("agents") != index.agents:
                raise InstallError("mixed_generation", "installed hashes disagree with managed targets")
            active_skills = active.get("skills")
            active_agents = active.get("agents")
            if not isinstance(active_skills, dict) or active_skills.get("installed") != sorted(index.skills):
                raise InstallError("mixed_generation", "active skill set disagrees with managed index")
            if not isinstance(active_agents, dict) or active_agents.get("installed") != sorted(index.agents) or active_agents.get("installed_count") != len(index.agents):
                raise InstallError("mixed_generation", "active agent set disagrees with managed index")
    if index is None:
        return
    for name, expected in index.skills.items():
        if hash_managed(paths, f"skills/{name}", "dir") != expected:
            raise InstallError("managed_drift", f"managed skill changed: {name}")
    for name, expected in index.agents.items():
        if hash_managed(paths, f"agents/{name}", "file") != expected:
            raise InstallError("managed_drift", f"managed agent changed: {name}")


def placeholder_targets() -> tuple[tuple[InstallTarget, ...], tuple[InstallTarget, ...]]:
    skills = tuple(InstallTarget(f"skills/{path.name}", path, "", "dir") for path in skill_dirs(ROOT))
    agents = tuple(InstallTarget(f"agents/{name}", None, "", "file") for name in EXPECTED_AGENT_FILES)
    return skills, agents


def commit_generation(paths: InstallPaths, commit: GenerationCommit) -> None:
    snapshot_id = commit.snapshot_id
    index = commit.index
    index_hash = sha256_file(paths.root / "managed-index.json")
    write_json(paths.root / "installed-hashes.json", {"schema_version": "0.2", "snapshot_id": snapshot_id, "files": commit.files, "managed_index_sha256": index_hash, "skills": index.skills, "agents": index.agents})
    midpoint("ledger_hashes")
    write_json(
        paths.root / "active.json",
        {
            "schema_version": "0.2",
            "snapshot_id": snapshot_id,
            "manifest_sha256": sha256_file(paths.snapshots / snapshot_id / "manifest.json"),
            "managed_index_sha256": index_hash,
            "agent_company_ref": commit.agent_ref,
            "skills": {"installed": sorted(index.skills), "root": str(paths.codex_home / "skills")},
            "agents": {"installed": sorted(index.agents), "installed_count": len(index.agents), "root": str(paths.codex_home / "agents")},
        },
    )
    midpoint("ledger_active")


def update_runtime_metadata(paths: InstallPaths) -> None:
    device_path = paths.state / "device.json"
    if not device_path.exists():
        source = os.environ.get("AGENT_COMPANY_DEVICE_ID", "") or str(paths.root)
        write_json(device_path, {"schema_version": "0.1", "device_id": hashlib.sha256(source.encode()).hexdigest()[:16], "codex_home": str(paths.codex_home)})
    status_path = paths.state / "status.json"
    try:
        status = read_json(status_path) if status_path.exists() else {}
    except InstallError:
        status = {}
    status["last_update_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_json(status_path, status)


def execute_generation(paths: InstallPaths, action: str) -> dict[str, JsonValue]:
    prior = load_index(paths)
    verify_prior(paths, prior)
    identity = snapshot_identity()
    snapshot_id = identity.snapshot_id
    transaction_id = uuid.uuid4().hex
    begin(paths, TransactionSpec(transaction_id, action, snapshot_id))
    try:
        skill_placeholders, agent_placeholders = placeholder_targets()
        legacy = active_payload(paths)
        ownership = SkillOwnership(prior, legacy)
        before_phase("preflight_all")
        plan_skills(paths.codex_home, skill_placeholders, ownership)
        plan_agents(paths.codex_home, agent_placeholders, prior)
        phase(paths, "preflight_all")
        before_phase("stage_all")
        staged = stage_generation(paths, transaction_id, identity)
        staged_id = staged.snapshot_id
        staged_ref = staged.agent_ref
        files = staged.files
        stage = paths.staging / transaction_id
        skills = staged.skills
        agents = staged.agents
        skills, stale_skills = plan_skills(paths.codex_home, skills, ownership)
        agents, stale_agents = plan_agents(paths.codex_home, agents, prior)
        phase(paths, "stage_all")
        before_phase("backup_managed")
        relatives = ("agent-company/active.json", "agent-company/installed-hashes.json", "agent-company/managed-index.json", f"agent-company/snapshots/{staged_id}", *(target.relative for target in skills + stale_skills + agents + stale_agents))
        capture(paths, transaction_id, relatives)
        phase(paths, "backup_managed")
        verify_all_staged_targets(stage, staged)
        race_staged_target(stage, "agent-index")
        verify_all_staged_targets(stage, staged)
        before_phase("apply_snapshot")
        apply_snapshot(paths, stage, staged)
        midpoint("apply_snapshot")
        phase(paths, "apply_snapshot")
        before_phase("apply_skills")
        apply_targets(
            paths,
            ApplyBatch(skills, stale_skills, "apply_skills", stage, "skill"),
        )
        phase(paths, "apply_skills")
        before_phase("apply_agents")
        apply_targets(
            paths,
            ApplyBatch(agents, stale_agents, "apply_agents", stage, "agent"),
        )
        phase(paths, "apply_agents")
        before_phase("write_indexes")
        index = ManagedIndex(staged_id, {Path(item.relative).name: item.expected_hash for item in skills}, {Path(item.relative).name: item.expected_hash for item in agents})
        write_index(paths, index)
        midpoint("write_index")
        phase(paths, "write_indexes")
        before_phase("commit_active_hashes")
        commit_generation(paths, GenerationCommit(staged_id, staged_ref, files, index))
        phase(paths, "commit_active_hashes")
        before_phase("cleanup")
        phase(paths, "cleanup")
        preserve_rollback(paths, transaction_id)
        cleanup_success(paths, transaction_id)
    except (DepsError, InstallError, NativeAgentError, SkillInstallError, OSError, ValueError):
        restore_transaction(paths, transaction_id)
        raise
    update_runtime_metadata(paths)
    return {"status": "ok", "action": action, "snapshot_id": snapshot_id, "agents": 6}


def uninstall(paths: InstallPaths) -> dict[str, JsonValue]:
    prior = load_index(paths)
    if prior is None:
        return {"status": "ok", "action": "uninstall", "removed": False}
    verify_prior(paths, prior)
    transaction_id = uuid.uuid4().hex
    begin(paths, TransactionSpec(transaction_id, "uninstall", prior.snapshot_id))
    try:
        before_phase("preflight_all")
        phase(paths, "preflight_all")
        before_phase("stage_all")
        phase(paths, "stage_all")
        targets = tuple(f"skills/{name}" for name in prior.skills) + tuple(f"agents/{name}" for name in prior.agents)
        before_phase("backup_managed")
        capture(paths, transaction_id, ("agent-company/active.json", "agent-company/installed-hashes.json", "agent-company/managed-index.json", *targets))
        phase(paths, "backup_managed")
        before_phase("apply_snapshot")
        phase(paths, "apply_snapshot")
        before_phase("apply_skills")
        changed = 0
        for name in prior.skills:
            remove_target(paths, InstallTarget(f"skills/{name}", None, prior.skills[name], "dir"))
            changed += 1
            if changed == 1:
                midpoint("apply_skills")
        phase(paths, "apply_skills")
        before_phase("apply_agents")
        changed = 0
        for name in prior.agents:
            remove_target(paths, InstallTarget(f"agents/{name}", None, prior.agents[name], "file"))
            changed += 1
            if changed == 1:
                midpoint("apply_agents")
        phase(paths, "apply_agents")
        before_phase("write_indexes")
        remove_managed(paths, "agent-company/managed-index.json")
        midpoint("write_index")
        phase(paths, "write_indexes")
        before_phase("commit_active_hashes")
        remove_managed(paths, "agent-company/installed-hashes.json")
        midpoint("ledger_hashes")
        remove_managed(paths, "agent-company/active.json")
        midpoint("ledger_active")
        phase(paths, "commit_active_hashes")
        before_phase("cleanup")
        phase(paths, "cleanup")
        preserve_rollback(paths, transaction_id)
        cleanup_success(paths, transaction_id)
    except (InstallError, OSError, ValueError):
        restore_transaction(paths, transaction_id)
        raise
    return {"status": "ok", "action": "uninstall", "removed": True}
