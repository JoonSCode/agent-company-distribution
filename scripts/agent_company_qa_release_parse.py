#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv if needed.
# 2. Import through agent_company_qa_release.py; this module has no CLI.
# 3. Test: python3 scripts/test_qa_release_security.py
# ─────────────────

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Final, assert_never

from agent_company_plan_models import JsonValue, PlanError, item_values, load_object, object_value, require_keys, text_value, text_values
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
from agent_company_qa_release_validation import reject_private_payload, validate_evidence


FORMAT: Final = "agent-company.qa-observation/v0.1"
OBSERVATION_FIELDS: Final = frozenset({
    "criterion_id", "surface", "status", "candidate_identity_sha256", "initial_state", "action",
    "observed_result", "evidence_ref", "cleanup", "stop_condition",
})


def _enum_value[EnumT: StrEnum](enum_type: type[EnumT], value: JsonValue, path: str) -> EnumT:
    raw = text_value(value, path)
    try:
        return enum_type(raw)
    except ValueError as exc:
        raise PlanError("malformed_input", path, "unsupported value") from exc


def _bool_value(value: JsonValue, path: str) -> bool:
    match value:
        case bool():
            return value
        case str() | int() | float() | None | list() | dict():
            raise PlanError("malformed_input", path, "must be a boolean")
        case unreachable:
            assert_never(unreachable)


def _statement(value: JsonValue, path: str, fields: frozenset[str]) -> dict[str, JsonValue]:
    match value:
        case str():
            raise PlanError("thin_evidence", path, "must be a structured evidence object")
        case dict():
            require_keys(value, fields, path)
            return value
        case int() | float() | bool() | None | list():
            raise PlanError("malformed_input", path, "must be a structured evidence object")
        case unreachable:
            assert_never(unreachable)


def _parse_candidate(value: JsonValue) -> Candidate:
    path = "$evidence.candidate"
    raw = object_value(value, path)
    fields = (
        "app_id",
        "version",
        "build",
        "git_commit",
        "source_state_sha256",
        "configuration",
    )
    require_keys(raw, frozenset(fields), path)
    text = tuple(text_value(raw.get(field), f"{path}.{field}") for field in fields)
    return Candidate(*text)


def _parse_criteria(value: JsonValue) -> tuple[Criterion, ...]:
    result: list[Criterion] = []
    for index, item in enumerate(item_values(value, "$evidence.acceptance_criteria")):
        path = f"$evidence.acceptance_criteria[{index}]"
        raw = object_value(item, path)
        require_keys(raw, frozenset({"id", "surface"}), path)
        result.append(Criterion(text_value(raw.get("id"), f"{path}.id"), _enum_value(Surface, raw.get("surface"), f"{path}.surface")))
    return tuple(result)


def _parse_observation(item: JsonValue, index: int) -> Observation:
    path = f"$evidence.observations[{index}]"
    raw = object_value(item, path)
    require_keys(raw, OBSERVATION_FIELDS, path)
    initial = _statement(raw.get("initial_state"), f"{path}.initial_state", frozenset({"state_id", "detail"}))
    action = _statement(raw.get("action"), f"{path}.action", frozenset({"kind", "detail"}))
    result = _statement(raw.get("observed_result"), f"{path}.observed_result", frozenset({"outcome", "detail"}))
    cleanup = _statement(raw.get("cleanup"), f"{path}.cleanup", frozenset({"disposition", "detail"}))
    stop = _statement(raw.get("stop_condition"), f"{path}.stop_condition", frozenset({"kind", "detail"}))
    return Observation(
        text_value(raw.get("criterion_id"), f"{path}.criterion_id"),
        _enum_value(Surface, raw.get("surface"), f"{path}.surface"),
        _enum_value(ObservationStatus, raw.get("status"), f"{path}.status"),
        text_value(raw.get("candidate_identity_sha256"), f"{path}.candidate_identity_sha256"),
        InitialState(text_value(initial.get("state_id"), f"{path}.initial_state.state_id"), text_value(initial.get("detail"), f"{path}.initial_state.detail")),
        Action(_enum_value(ActionKind, action.get("kind"), f"{path}.action.kind"), text_value(action.get("detail"), f"{path}.action.detail")),
        ObservedResult(_enum_value(ObservedOutcome, result.get("outcome"), f"{path}.observed_result.outcome"), text_value(result.get("detail"), f"{path}.observed_result.detail")),
        text_value(raw.get("evidence_ref"), f"{path}.evidence_ref"),
        ObservationCleanup(_enum_value(ObservationCleanupDisposition, cleanup.get("disposition"), f"{path}.cleanup.disposition"), text_value(cleanup.get("detail"), f"{path}.cleanup.detail")),
        StopCondition(_enum_value(StopKind, stop.get("kind"), f"{path}.stop_condition.kind"), text_value(stop.get("detail"), f"{path}.stop_condition.detail")),
    )


def parse_evidence(path: Path) -> QaEvidence:
    raw = load_object(path)
    reject_private_payload(raw)
    fields = frozenset({"format", "candidate", "acceptance_criteria", "observations", "cleanup", "specialist_routes", "residual_risks"})
    require_keys(raw, fields, "$evidence")
    if raw.get("format") != FORMAT:
        raise PlanError("malformed_input", "$evidence.format", "unsupported QA observation format")
    cleanup_path = "$evidence.cleanup"
    cleanup_raw = object_value(raw.get("cleanup"), cleanup_path)
    require_keys(cleanup_raw, frozenset({"screenshots_removed", "state_reset", "disposition"}), cleanup_path)
    evidence = QaEvidence(
        _parse_candidate(raw.get("candidate")),
        _parse_criteria(raw.get("acceptance_criteria")),
        tuple(_parse_observation(item, index) for index, item in enumerate(item_values(raw.get("observations"), "$evidence.observations"))),
        Cleanup(
            _bool_value(cleanup_raw.get("screenshots_removed"), f"{cleanup_path}.screenshots_removed"),
            _bool_value(cleanup_raw.get("state_reset"), f"{cleanup_path}.state_reset"),
            _enum_value(CleanupDisposition, cleanup_raw.get("disposition"), f"{cleanup_path}.disposition"),
        ),
        text_values(raw.get("specialist_routes"), "$evidence.specialist_routes", allow_empty=True),
        text_values(raw.get("residual_risks"), "$evidence.residual_risks", allow_empty=True),
    )
    validate_evidence(evidence)
    return evidence
