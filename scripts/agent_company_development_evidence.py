from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportUnnecessaryComparison=false
from dataclasses import dataclass
from typing import Final, assert_never, override

from agent_company_architecture_safety import (
    ArchitectureSafetyError,
    parse_architecture_safety_packet,
)
from agent_company_deps import JsonValue

MAX_TEXT: Final[int] = 500
FEATURE_FIELDS: Final[frozenset[str]] = frozenset(
    {"pre_change_evidence", "pre_change_infeasibility"}
)
INFEASIBILITY_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "unavailable_control",
        "safety_reason",
        "bounded_substitute_observation",
        "remaining_verification_owner",
    }
)
CAUSAL_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "hypothesis",
        "observable_reentry_signal",
        "next_bounded_check",
        "owner",
    }
)
ARCHITECTURE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "disposition",
        "impact_scope",
        "reversibility",
        "evidence",
        "materiality_reason",
        "architecture_safety",
    }
)
ARCHITECTURE_DISPOSITIONS: Final[frozenset[str]] = frozenset(
    {"material", "preserved", "not_applicable", "unknown"}
)


@dataclass(frozen=True, slots=True)
class DevelopmentEvidenceError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return self.detail


def _object(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    match value:
        case dict():
            return value
        case str() | int() | float() | bool() | None | list():
            raise DevelopmentEvidenceError(f"{label} must be an object")
        case unreachable:
            assert_never(unreachable)


def _text(value: JsonValue | None, label: str) -> str:
    match value:
        case str() if value.strip() and len(value) <= MAX_TEXT:
            return value
        case str() | int() | float() | bool() | None | list() | dict():
            raise DevelopmentEvidenceError(
                f"{label} must be bounded non-empty text"
            )
        case unreachable:
            assert_never(unreachable)


def _exact_fields(
    value: dict[str, JsonValue],
    expected: frozenset[str],
    label: str,
) -> None:
    actual = frozenset(value)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    raise DevelopmentEvidenceError(
        f"{label} fields differ; missing={missing}, extra={extra}"
    )


def _validate_feature(value: JsonValue | None) -> None:
    evidence = _object(value, "role_evidence")
    extra = sorted(frozenset(evidence) - FEATURE_FIELDS)
    if extra:
        raise DevelopmentEvidenceError(
            f"feature role_evidence has unsupported fields: {extra}"
        )
    pre_change = evidence.get("pre_change_evidence")
    infeasibility = evidence.get("pre_change_infeasibility")
    if pre_change is None and infeasibility is None:
        raise DevelopmentEvidenceError(
            "feature role_evidence requires pre_change_evidence or pre_change_infeasibility"
        )
    if pre_change is not None:
        _ = _text(pre_change, "pre_change_evidence")
    if infeasibility is None:
        return
    record = _object(infeasibility, "pre_change_infeasibility")
    _exact_fields(record, INFEASIBILITY_FIELDS, "pre_change_infeasibility")
    for field in INFEASIBILITY_FIELDS:
        _ = _text(record.get(field), f"pre_change_infeasibility.{field}")


def _validate_causal(value: JsonValue | None) -> None:
    evidence = _object(value, "role_evidence")
    _exact_fields(evidence, CAUSAL_FIELDS, "causal role_evidence")
    for field in CAUSAL_FIELDS:
        _ = _text(evidence.get(field), field)


def _validate_architecture(value: JsonValue | None) -> None:
    evidence = _object(value, "role_evidence")
    _exact_fields(evidence, ARCHITECTURE_FIELDS, "architecture role_evidence")
    disposition = _text(evidence.get("disposition"), "disposition")
    if disposition not in ARCHITECTURE_DISPOSITIONS:
        raise DevelopmentEvidenceError("architecture disposition is unsupported")
    for field in ARCHITECTURE_FIELDS - {"disposition", "architecture_safety"}:
        _ = _text(evidence.get(field), field)
    try:
        _ = parse_architecture_safety_packet(evidence.get("architecture_safety"))
    except ArchitectureSafetyError as error:
        raise DevelopmentEvidenceError(
            f"architecture_safety: {error}"
        ) from error


def validate_development_task_evidence(
    value: JsonValue | None,
    *,
    task_type: str,
    task_pack_id: str,
) -> None:
    """Validate the task-specific Development evidence selected by context."""
    if task_type == "feature-implementation":
        expected_pack = "task-pack:development:feature-implementation"
        validator = _validate_feature
    elif task_type == "causal-debugging":
        expected_pack = "task-pack:development:causal-debugging"
        validator = _validate_causal
    elif task_type == "architecture-risk":
        expected_pack = "task-pack:development:architecture-risk"
        validator = _validate_architecture
    else:
        raise DevelopmentEvidenceError(
            f"unsupported Development task type: {task_type}"
        )
    if task_pack_id != expected_pack:
        raise DevelopmentEvidenceError(
            f"Development task pack mismatch: expected {expected_pack}"
        )
    validator(value)


__all__ = [
    "DevelopmentEvidenceError",
    "validate_development_task_evidence",
]
