#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from agent_company_install_fs import ensure_regular_tree, sha256_tree
from agent_company_install_io import read_json
from agent_company_install_types import InstallError, InstallTarget, JsonValue, ManagedIndex


MARKER: Final[str] = ".agent-company-skill.json"
SKIP_DIRS: Final[set[str]] = {"__pycache__", ".pytest_cache"}


@dataclass(frozen=True, slots=True)
class SkillInstallError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class SkillStage:
    agent_ref: str
    snapshot_id: str


@dataclass(frozen=True, slots=True)
class SkillOwnership:
    prior: ManagedIndex | None
    legacy_active: dict[str, JsonValue] | None


def skill_dirs(repo_root: Path) -> tuple[Path, ...]:
    root = repo_root / "skills"
    if not root.exists():
        return ()
    ensure_regular_tree(root)
    return tuple(
        path
        for path in sorted(root.iterdir())
        if path.is_dir() and (path / "SKILL.md").is_file()
    )


def stage_skills(repo_root: Path, output: Path, stage: SkillStage) -> tuple[InstallTarget, ...]:
    output.mkdir(parents=True, exist_ok=True)
    staged: list[InstallTarget] = []
    for source in skill_dirs(repo_root):
        target = output / source.name
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(*SKIP_DIRS))
        marker = {
            "schema_version": "0.2",
            "managed_by": "agent-company",
            "skill": source.name,
            "agent_company_ref": stage.agent_ref,
            "snapshot_id": stage.snapshot_id,
        }
        (target / MARKER).write_text(
            json.dumps(marker, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staged.append(
            InstallTarget(f"skills/{source.name}", target, sha256_tree(target), "dir")
        )
    return tuple(staged)


def legacy_owned(target: Path, active: dict[str, JsonValue] | None) -> bool:
    marker = target / MARKER
    if active is None or not marker.is_file() or marker.is_symlink():
        return False
    try:
        payload = read_json(marker)
    except InstallError:
        return False
    skills = active.get("skills")
    if not isinstance(skills, dict):
        return False
    installed = skills.get("installed")
    if not isinstance(installed, list):
        return False
    return payload.get("managed_by") == "agent-company" and target.name in installed


def plan_skills(
    codex_home: Path,
    desired: tuple[InstallTarget, ...],
    ownership: SkillOwnership,
) -> tuple[tuple[InstallTarget, ...], tuple[InstallTarget, ...]]:
    root = codex_home / "skills"
    if root.exists():
        ensure_regular_tree(root)
    prior_hashes = {} if ownership.prior is None else ownership.prior.skills
    desired_names = {Path(target.relative).name for target in desired}
    for target in desired:
        path = codex_home / target.relative
        if not path.exists():
            continue
        name = path.name
        expected = prior_hashes.get(name)
        if expected is not None and sha256_tree(path) == expected:
            continue
        if legacy_owned(path, ownership.legacy_active):
            continue
        raise InstallError("skill_conflict", f"{name} exists without matching managed ownership")
    stale: list[InstallTarget] = []
    for name, expected in sorted(prior_hashes.items()):
        if name in desired_names:
            continue
        path = root / name
        if not path.exists() or sha256_tree(path) != expected:
            raise InstallError("managed_drift", f"stale skill is missing or changed: {name}")
        stale.append(InstallTarget(f"skills/{name}", None, expected, "dir"))
    return desired, tuple(stale)
