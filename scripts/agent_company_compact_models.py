#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Import from the compact report boundary modules.
# ─────────────────

"""Immutable domain values for compact CEO projections."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EvidenceState(StrEnum):
    EXECUTED = "executed"
    VERIFIED = "verified"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNVERIFIED = "unverified"


class OverallState(StrEnum):
    EXECUTED = "executed"
    VERIFIED = "verified"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNVERIFIED = "unverified"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class CanonicalEntry:
    state: EvidenceState
    summary: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CanonicalReport:
    job_id: str
    overall_status: OverallState
    decision_summary: str
    ordinary_roles: tuple[str, ...]
    entries: tuple[CanonicalEntry, ...]
    next_actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CanonicalBinding:
    report: CanonicalReport
    payload: bytes
    sha256: str
    ref: str


@dataclass(frozen=True, slots=True)
class ValidatedRoute:
    lane: str
    ordinary_roles: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    candidate_payload: bytes
    core_payload: bytes
    external_mutation: bool
    approval_required: bool


@dataclass(frozen=True, slots=True)
class Risk:
    state: EvidenceState
    summary: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompactReport:
    source: CanonicalBinding
    route: ValidatedRoute
    lane: str
    outcome: str
    verification: OverallState
    decision_required: bool
    decision_prompt: str
    material_risks: tuple[Risk, ...]
    next_action: str
    evidence_links: tuple[str, ...]
