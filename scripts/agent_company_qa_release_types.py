#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv if needed.
# 2. Import from agent_company_qa_release.py; this module has no CLI.
# 3. Test: python3 scripts/test_qa_release_operating_system.py
# ─────────────────

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Surface(StrEnum):
    AUTOMATED = "automated"
    SIMULATOR = "simulator"
    REAL_DEVICE = "real_device"
    PERMISSIONS_PRIVACY = "permissions_privacy"
    STOREKIT = "storekit"
    APP_STORE_CONNECT = "app_store_connect"
    MANUAL = "manual"


class ObservationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNVERIFIED = "unverified"


class ObservedOutcome(StrEnum):
    ACCEPTANCE_OBSERVED = "acceptance_observed"
    ACCEPTANCE_FAILED = "acceptance_failed"
    AVAILABILITY_BLOCKED = "availability_blocked"
    EVIDENCE_MISSING = "evidence_missing"


class ActionKind(StrEnum):
    AUTOMATED_CHECK = "automated_check"
    SIMULATOR_INTERACTION = "simulator_interaction"
    DEVICE_INTERACTION = "device_interaction"
    PERMISSION_TRANSITION = "permission_transition"
    STOREKIT_TRANSACTION = "storekit_transaction"
    ACCOUNT_INSPECTION = "account_inspection"
    MANUAL_OBSERVATION = "manual_observation"
    AVAILABILITY_CHECK = "availability_check"


class ObservationCleanupDisposition(StrEnum):
    NOT_NEEDED = "not_needed"
    REMOVED = "removed"
    RESET = "reset"
    SANITIZED_ARTIFACT = "sanitized_artifact"
    NO_STATE_CREATED = "no_state_created"


class StopKind(StrEnum):
    TERMINAL_RESULT = "terminal_result"
    CRITERION_OBSERVED = "criterion_observed"
    ACCEPTANCE_FAILED = "acceptance_failed"
    SURFACE_UNAVAILABLE = "surface_unavailable"
    EVIDENCE_MISSING = "evidence_missing"
    SAFETY_STOP = "safety_stop"


class CleanupDisposition(StrEnum):
    REMOVED = "removed"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True, slots=True)
class Candidate:
    app_id: str
    version: str
    build: str
    git_commit: str
    source_state_sha256: str
    configuration: str


@dataclass(frozen=True, slots=True)
class Criterion:
    id: str
    surface: Surface


@dataclass(frozen=True, slots=True)
class InitialState:
    state_id: str
    detail: str


@dataclass(frozen=True, slots=True)
class Action:
    kind: ActionKind
    detail: str


@dataclass(frozen=True, slots=True)
class ObservedResult:
    outcome: ObservedOutcome
    detail: str


@dataclass(frozen=True, slots=True)
class ObservationCleanup:
    disposition: ObservationCleanupDisposition
    detail: str


@dataclass(frozen=True, slots=True)
class StopCondition:
    kind: StopKind
    detail: str


@dataclass(frozen=True, slots=True)
class Observation:
    criterion_id: str
    surface: Surface
    status: ObservationStatus
    candidate_identity_sha256: str
    initial_state: InitialState
    action: Action
    observed_result: ObservedResult
    evidence_ref: str
    cleanup: ObservationCleanup
    stop_condition: StopCondition


@dataclass(frozen=True, slots=True)
class Cleanup:
    screenshots_removed: bool
    state_reset: bool
    disposition: CleanupDisposition


@dataclass(frozen=True, slots=True)
class QaEvidence:
    candidate: Candidate
    criteria: tuple[Criterion, ...]
    observations: tuple[Observation, ...]
    cleanup: Cleanup
    specialist_routes: tuple[str, ...]
    residual_risks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CriterionStatus:
    criterion_id: str
    surface: Surface
    status: ObservationStatus
    evidence: Observation | None


@dataclass(frozen=True, slots=True)
class QaReport:
    status: ObservationStatus
    qa_readiness: str
    candidate: Candidate
    criteria_status: tuple[CriterionStatus, ...]
    passed_evidence: tuple[Observation, ...]
    failed_evidence: tuple[Observation, ...]
    blocked_evidence: tuple[Observation, ...]
    unverified_surfaces: tuple[str, ...]
    cleanup: Cleanup
    residual_risks: tuple[str, ...]
    specialist_routes: tuple[str, ...]
    passed_count: int
    failed_count: int
    blocked_count: int
    unverified_count: int
    failed_criteria: tuple[str, ...]
    blocked_criteria: tuple[str, ...]
    unverified_criteria: tuple[str, ...]
    next_recommended_surface: str = "seungjeongwon"
    final_verification_surface: str = "seungjeongwon"
