#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv if needed.
# 2. Imported by both QA parsing and evaluation boundaries.
# 3. Test: python3 scripts/test_qa_release_direct_validation.py
# ─────────────────

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from typing import Final

from agent_company_plan_models import JsonValue, PlanError
from agent_company_privacy import PrivacyError, reject_sensitive
from agent_company_qa_release_types import (
    Action,
    ActionKind,
    Candidate,
    Cleanup,
    CleanupDisposition,
    Criterion,
    InitialState,
    Observation,
    ObservationCleanup,
    ObservationCleanupDisposition,
    ObservationStatus,
    ObservedOutcome,
    ObservedResult,
    QaEvidence,
    StopCondition,
    StopKind,
    Surface,
)


GIT_COMMIT: Final = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
SHA256: Final = re.compile(r"[0-9a-f]{64}")
STATE_ID: Final = re.compile(r"[a-z][a-z0-9-]{3,}")
ROUTE_ID: Final = re.compile(r"[a-z][a-z0-9:._-]{2,}")
EVIDENCE_REF: Final = re.compile(r"(?:artifact|qa)://[A-Za-z0-9._~:/-]+")
DEVICE_PATH: Final = re.compile(r"(?i)(?:file:///|/(?:private/var|data/user|sdcard|storage/emulated)/)[^\s\"']+")
PLACEHOLDERS: Final = frozenset({
    "all", "complete", "completed", "done", "n", "n-a", "na", "none", "ok", "pass", "passed",
    "same", "success", "successful", "tbd", "unknown", "x",
})
SURFACE_ACTIONS: Final = {
    Surface.AUTOMATED: frozenset({ActionKind.AUTOMATED_CHECK}),
    Surface.SIMULATOR: frozenset({ActionKind.SIMULATOR_INTERACTION}),
    Surface.REAL_DEVICE: frozenset({ActionKind.DEVICE_INTERACTION, ActionKind.AVAILABILITY_CHECK}),
    Surface.PERMISSIONS_PRIVACY: frozenset({ActionKind.PERMISSION_TRANSITION}),
    Surface.STOREKIT: frozenset({ActionKind.STOREKIT_TRANSACTION}),
    Surface.APP_STORE_CONNECT: frozenset({ActionKind.ACCOUNT_INSPECTION}),
    Surface.MANUAL: frozenset({ActionKind.MANUAL_OBSERVATION}),
}
REAL_DEVICE_ACTIONS_BY_STATUS: Final = {
    ObservationStatus.PASSED: frozenset({ActionKind.DEVICE_INTERACTION}),
    ObservationStatus.FAILED: frozenset({ActionKind.DEVICE_INTERACTION}),
    ObservationStatus.BLOCKED: frozenset({ActionKind.DEVICE_INTERACTION, ActionKind.AVAILABILITY_CHECK}),
    ObservationStatus.UNVERIFIED: frozenset({ActionKind.DEVICE_INTERACTION, ActionKind.AVAILABILITY_CHECK}),
}
STATUS_OUTCOMES: Final = {
    ObservationStatus.PASSED: frozenset({ObservedOutcome.ACCEPTANCE_OBSERVED}),
    ObservationStatus.FAILED: frozenset({ObservedOutcome.ACCEPTANCE_FAILED}),
    ObservationStatus.BLOCKED: frozenset({ObservedOutcome.AVAILABILITY_BLOCKED}),
    ObservationStatus.UNVERIFIED: frozenset({ObservedOutcome.EVIDENCE_MISSING}),
}
STATUS_STOPS: Final = {
    ObservationStatus.PASSED: frozenset({StopKind.TERMINAL_RESULT, StopKind.CRITERION_OBSERVED}),
    ObservationStatus.FAILED: frozenset({StopKind.ACCEPTANCE_FAILED, StopKind.SAFETY_STOP}),
    ObservationStatus.BLOCKED: frozenset({StopKind.SURFACE_UNAVAILABLE, StopKind.SAFETY_STOP}),
    ObservationStatus.UNVERIFIED: frozenset({StopKind.EVIDENCE_MISSING, StopKind.SURFACE_UNAVAILABLE}),
}


def _text(value: str, path: str) -> str:
    if type(value) is not str or not value.strip():
        raise PlanError("malformed_input", path, "must be non-empty text")
    return value.strip()


def _detail(value: str, path: str) -> str:
    text = _text(value, path)
    words = frozenset(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", text.casefold()))
    if not words or words <= PLACEHOLDERS:
        raise PlanError("thin_evidence", path, "must contain concrete observed detail")
    return text


def reject_private_payload(value: JsonValue) -> None:
    try:
        reject_sensitive(value)
    except PrivacyError as exc:
        raise PlanError("privacy_rejected", "$evidence", "evidence contains forbidden private data") from exc
    if DEVICE_PATH.search(json.dumps(value, ensure_ascii=False)) is not None:
        raise PlanError("privacy_rejected", "$evidence", "evidence contains forbidden private data")


def _validate_candidate(candidate: Candidate) -> str:
    if not isinstance(candidate, Candidate):
        raise PlanError("malformed_input", "$evidence.candidate", "must be Candidate")
    for field in (
        "app_id",
        "version",
        "build",
        "git_commit",
        "source_state_sha256",
        "configuration",
    ):
        _text(getattr(candidate, field), f"$evidence.candidate.{field}")
    if GIT_COMMIT.fullmatch(candidate.git_commit) is None:
        raise PlanError("malformed_input", "$evidence.candidate.git_commit", "must be a full lowercase commit")
    if SHA256.fullmatch(candidate.source_state_sha256) is None:
        raise PlanError(
            "malformed_input",
            "$evidence.candidate.source_state_sha256",
            "must be lowercase SHA-256",
        )
    canonical = json.dumps(asdict(candidate), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(canonical).hexdigest()


def _validate_criterion(criterion: Criterion, path: str) -> None:
    if not isinstance(criterion, Criterion) or type(criterion.surface) is not Surface:
        raise PlanError("malformed_input", path, "must be a typed criterion")
    _detail(criterion.id, f"{path}.id")


def _validate_initial(value: InitialState, path: str) -> str:
    if not isinstance(value, InitialState):
        raise PlanError("malformed_input", path, "must be InitialState")
    state_id = _text(value.state_id, f"{path}.state_id")
    if STATE_ID.fullmatch(state_id) is None or state_id in PLACEHOLDERS:
        raise PlanError("thin_evidence", f"{path}.state_id", "must be a semantic state identifier")
    return _detail(value.detail, f"{path}.detail")


def _validate_action(value: Action, path: str) -> str:
    if not isinstance(value, Action) or type(value.kind) is not ActionKind:
        raise PlanError("malformed_input", path, "must be a typed Action")
    return _detail(value.detail, f"{path}.detail")


def _validate_result(value: ObservedResult, path: str) -> str:
    if not isinstance(value, ObservedResult) or type(value.outcome) is not ObservedOutcome:
        raise PlanError("malformed_input", path, "must be a typed ObservedResult")
    return _detail(value.detail, f"{path}.detail")


def _validate_observation_cleanup(value: ObservationCleanup, path: str) -> None:
    if not isinstance(value, ObservationCleanup) or type(value.disposition) is not ObservationCleanupDisposition:
        raise PlanError("malformed_input", path, "must be typed observation cleanup")
    _detail(value.detail, f"{path}.detail")


def _validate_stop(value: StopCondition, path: str) -> str:
    if not isinstance(value, StopCondition) or type(value.kind) is not StopKind:
        raise PlanError("malformed_input", path, "must be a typed StopCondition")
    return _detail(value.detail, f"{path}.detail")


def _validate_observation(observation: Observation, candidate_hash: str, criteria: dict[str, Criterion], index: int) -> None:
    path = f"$evidence.observations[{index}]"
    if not isinstance(observation, Observation) or type(observation.surface) is not Surface or type(observation.status) is not ObservationStatus:
        raise PlanError("malformed_input", path, "must be a typed Observation")
    criterion_id = _detail(observation.criterion_id, f"{path}.criterion_id")
    if SHA256.fullmatch(_text(observation.candidate_identity_sha256, f"{path}.candidate_identity_sha256")) is None:
        raise PlanError("malformed_input", f"{path}.candidate_identity_sha256", "must be lowercase SHA-256")
    if observation.candidate_identity_sha256 != candidate_hash:
        raise PlanError("candidate_mismatch", criterion_id, "observation belongs to another candidate")
    criterion = criteria.get(criterion_id)
    if criterion is None:
        raise PlanError("unknown_criterion", criterion_id, "observation is not bound to acceptance criteria")
    if observation.surface is not criterion.surface:
        raise PlanError("surface_mismatch", criterion_id, "observation is not from the required matching surface")
    initial = _validate_initial(observation.initial_state, f"{path}.initial_state")
    action = _validate_action(observation.action, f"{path}.action")
    result = _validate_result(observation.observed_result, f"{path}.observed_result")
    _validate_observation_cleanup(observation.cleanup, f"{path}.cleanup")
    stop = _validate_stop(observation.stop_condition, f"{path}.stop_condition")
    if observation.observed_result.outcome not in STATUS_OUTCOMES[observation.status]:
        raise PlanError("evidence_status_mismatch", f"{path}.observed_result.outcome", "outcome must match observation status")
    if observation.action.kind not in SURFACE_ACTIONS[observation.surface]:
        raise PlanError("surface_action_mismatch", f"{path}.action.kind", "action kind does not match observation surface")
    if observation.surface is Surface.REAL_DEVICE and observation.action.kind not in REAL_DEVICE_ACTIONS_BY_STATUS[observation.status]:
        raise PlanError("action_status_mismatch", f"{path}.action.kind", "action kind is insufficient for observation status")
    if observation.stop_condition.kind not in STATUS_STOPS[observation.status]:
        raise PlanError("stop_status_mismatch", f"{path}.stop_condition.kind", "stop kind does not match observation status")
    evidence_ref = _text(observation.evidence_ref, f"{path}.evidence_ref")
    if EVIDENCE_REF.fullmatch(evidence_ref) is None:
        raise PlanError("thin_evidence", f"{path}.evidence_ref", "must be a bounded artifact or QA reference")
    if len({item.casefold() for item in (initial, action, result, stop)}) != 4:
        raise PlanError("thin_evidence", path, "QA phases must carry distinct concrete details")


def _validate_cleanup(cleanup: Cleanup) -> None:
    if not isinstance(cleanup, Cleanup) or type(cleanup.screenshots_removed) is not bool or type(cleanup.state_reset) is not bool or type(cleanup.disposition) is not CleanupDisposition:
        raise PlanError("malformed_input", "$evidence.cleanup", "must be typed cleanup")
    complete = cleanup.screenshots_removed and cleanup.state_reset
    if complete != (cleanup.disposition is CleanupDisposition.REMOVED):
        raise PlanError("cleanup_mismatch", "$evidence.cleanup", "cleanup disposition contradicts cleanup flags")


def validate_evidence(evidence: QaEvidence) -> None:
    if not isinstance(evidence, QaEvidence) or type(evidence.criteria) is not tuple or type(evidence.observations) is not tuple:
        raise PlanError("malformed_input", "$evidence", "must be typed QA evidence")
    try:
        payload: JsonValue = json.loads(json.dumps(asdict(evidence), ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise PlanError("malformed_input", "$evidence", "evidence graph must be JSON-compatible") from exc
    reject_private_payload(payload)
    candidate_hash = _validate_candidate(evidence.candidate)
    if not evidence.criteria:
        raise PlanError("malformed_input", "$evidence.acceptance_criteria", "must not be empty")
    for index, criterion in enumerate(evidence.criteria):
        _validate_criterion(criterion, f"$evidence.acceptance_criteria[{index}]")
    criteria = {item.id: item for item in evidence.criteria}
    if len(criteria) != len(evidence.criteria):
        raise PlanError("malformed_input", "$evidence.acceptance_criteria", "must contain unique criteria")
    for index, observation in enumerate(evidence.observations):
        _validate_observation(observation, candidate_hash, criteria, index)
    if len({item.criterion_id for item in evidence.observations}) != len(evidence.observations):
        raise PlanError("malformed_input", "$evidence.observations", "criterion observations must be unique")
    _validate_cleanup(evidence.cleanup)
    if type(evidence.specialist_routes) is not tuple or type(evidence.residual_risks) is not tuple:
        raise PlanError("malformed_input", "$evidence", "routes and risks must be tuples")
    if len(set(evidence.specialist_routes)) != len(evidence.specialist_routes) or len(set(evidence.residual_risks)) != len(evidence.residual_risks):
        raise PlanError("malformed_input", "$evidence", "routes and risks must contain unique values")
    for index, route in enumerate(evidence.specialist_routes):
        if ROUTE_ID.fullmatch(_text(route, f"$evidence.specialist_routes[{index}]")) is None:
            raise PlanError("malformed_input", f"$evidence.specialist_routes[{index}]", "must be a bounded route id")
    for index, risk in enumerate(evidence.residual_risks):
        _detail(risk, f"$evidence.residual_risks[{index}]")
