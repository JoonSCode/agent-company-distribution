#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

from pathlib import Path

from agent_company_agent_output import INDEX_NAME, parse_managed_index
from agent_company_install_fs import (
    ensure_regular_tree,
    list_files,
    sha256_file,
    sha256_tree,
)
from agent_company_install_io import read_json
from agent_company_install_types import InstallError, InstallTarget, StagedGeneration
from agent_company_role_contract import NativeAgentError


def _source_digest(target: InstallTarget) -> str:
    source = target.source
    if source is None:
        raise InstallError("staged_source_drift", f"missing staged source: {target.relative}")
    ensure_regular_tree(source)
    if target.kind == "file" and not source.is_file():
        raise InstallError("staged_source_drift", f"staged source is not a file: {target.relative}")
    if target.kind == "dir" and not source.is_dir():
        raise InstallError("staged_source_drift", f"staged source is not a directory: {target.relative}")
    if target.kind not in {"file", "dir"}:
        raise InstallError("staged_source_drift", f"staged source kind is invalid: {target.relative}")
    return sha256_file(source) if target.kind == "file" else sha256_tree(source)


def verify_target_bytes(targets: tuple[InstallTarget, ...]) -> None:
    for target in targets:
        if _source_digest(target) != target.expected_hash:
            raise InstallError("staged_source_drift", f"staged source changed: {target.relative}")


def verify_staged_snapshot(stage: Path, staged: StagedGeneration) -> None:
    snapshot = stage / "snapshot"
    ensure_regular_tree(snapshot)
    actual_paths = {str(path.relative_to(snapshot)): path for path in list_files(snapshot)}
    if set(actual_paths) != set(staged.files):
        raise InstallError("staged_source_drift", "staged snapshot file set changed")
    for relative, expected in staged.files.items():
        if sha256_file(actual_paths[relative]) != expected:
            raise InstallError("staged_source_drift", f"staged snapshot changed: {relative}")
    manifest = read_json(snapshot / "manifest.json", "staged_source_drift")
    manifest_files = manifest.get("files")
    expected_manifest = {
        relative: digest
        for relative, digest in staged.files.items()
        if relative != "manifest.json"
    }
    if (
        manifest.get("schema_version") != "0.2"
        or manifest.get("snapshot_id") != staged.snapshot_id
        or manifest.get("agent_company_commit") != staged.agent_ref
        or manifest_files != expected_manifest
    ):
        raise InstallError("staged_source_drift", "staged snapshot manifest changed")


def _entry_names(root: Path) -> set[str]:
    ensure_regular_tree(root)
    return {path.name for path in root.iterdir()}


def _target_names(targets: tuple[InstallTarget, ...]) -> set[str]:
    names = {Path(target.relative).name for target in targets}
    if len(names) != len(targets):
        raise InstallError("staged_source_drift", "staged targets contain duplicate names")
    return names


def verify_all_staged_targets(stage: Path, staged: StagedGeneration) -> None:
    verify_staged_snapshot(stage, staged)
    skill_names = _target_names(staged.skills)
    agent_names = _target_names(staged.agents)
    if _entry_names(stage / "compiled-skills") != skill_names:
        raise InstallError("staged_source_drift", "staged skill target set changed")
    if _entry_names(stage / "compiled-agents") != {*agent_names, INDEX_NAME}:
        raise InstallError("staged_source_drift", "staged agent target set changed")
    try:
        agent_index = parse_managed_index(stage / "compiled-agents" / INDEX_NAME)
    except NativeAgentError as exc:
        raise InstallError("staged_source_drift", "staged agent target manifest changed") from exc
    indexed_agents = {agent.filename: agent.sha256 for agent in agent_index.agents}
    expected_agents = {
        Path(target.relative).name: target.expected_hash for target in staged.agents
    }
    if indexed_agents != expected_agents:
        raise InstallError("staged_source_drift", "staged agent target manifest changed")
    for target in staged.skills:
        if target.source != stage / "compiled-skills" / Path(target.relative).name:
            raise InstallError("staged_source_drift", f"staged skill source escaped: {target.relative}")
    for target in staged.agents:
        if target.source != stage / "compiled-agents" / Path(target.relative).name:
            raise InstallError("staged_source_drift", f"staged agent source escaped: {target.relative}")
    verify_target_bytes((*staged.skills, *staged.agents))


__all__ = [
    "verify_all_staged_targets", "verify_staged_snapshot", "verify_target_bytes",
]
