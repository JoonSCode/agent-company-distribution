#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class InstallError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class InstallPaths:
    codex_home: Path
    root: Path
    state: Path
    staging: Path
    snapshots: Path
    rollback: Path
    journal: Path
    transactions: Path


@dataclass(frozen=True, slots=True)
class ManagedIndex:
    snapshot_id: str
    skills: dict[str, str]
    agents: dict[str, str]


@dataclass(frozen=True, slots=True)
class TransactionSpec:
    transaction_id: str
    action: str
    snapshot_id: str


@dataclass(frozen=True, slots=True)
class GenerationCommit:
    snapshot_id: str
    agent_ref: str
    files: dict[str, str]
    index: ManagedIndex


@dataclass(frozen=True, slots=True)
class InstallTarget:
    relative: str
    source: Path | None
    expected_hash: str
    kind: str


@dataclass(frozen=True, slots=True)
class InstallPlan:
    action: str
    transaction_id: str
    snapshot_id: str
    stage: Path
    snapshot_files: dict[str, str]
    skills: tuple[InstallTarget, ...]
    agents: tuple[InstallTarget, ...]
    stale_skills: tuple[InstallTarget, ...]
    stale_agents: tuple[InstallTarget, ...]
    prior_index: ManagedIndex | None

    @property
    def managed_targets(self) -> tuple[InstallTarget, ...]:
        return self.skills + self.agents + self.stale_skills + self.stale_agents


@dataclass(frozen=True, slots=True)
class StagedGeneration:
    snapshot_id: str
    agent_ref: str
    files: dict[str, str]
    skills: tuple[InstallTarget, ...]
    agents: tuple[InstallTarget, ...]


@dataclass(frozen=True, slots=True)
class ApplyBatch:
    desired: tuple[InstallTarget, ...]
    stale: tuple[InstallTarget, ...]
    midpoint: str
    staging_root: Path | None = None
    race_kind: str | None = None


@dataclass(frozen=True, slots=True)
class BackupEntry:
    relative: str
    kind: str
    backup: str
    mode: int
    content_sha256: str
