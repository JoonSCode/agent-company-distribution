from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
from typing import Final

from agent_company_founder_evidence_common import (
    FounderTaskEvidenceError,
    JsonValue,
    authority_is_bounded,
    commitment,
    forbidden_claims,
    record,
    text,
    text_like,
    text_list,
)

COMMON_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "decision_question",
        "decision_owner",
        "decision_horizon",
        "decision_readiness",
        "no_action_consequence",
        "known",
        "inferred",
        "unknown",
        "evidence_refs",
        "recommended_action",
        "strongest_support",
        "strongest_disconfirmation",
        "serious_alternative",
        "assumptions",
        "opportunity_cost",
        "next_reversible_commitment",
        "success_criteria",
        "failure_criteria",
        "kill_criteria",
        "revisit_trigger",
        "next_owner",
        "next_surface",
        "forbidden_claims",
    }
)
PACK_FIELDS: Final[dict[str, tuple[str, frozenset[str]]]] = {
    "portfolio-decision": (
        "task-pack:founder:portfolio-decision",
        frozenset(
            {
                "options_considered",
                "rejected_option_reasons",
                "capacity_constraint",
                "not_funded",
                "residual_risk",
                "confidence",
            }
        ),
    ),
    "opportunity-validation": (
        "task-pack:founder:opportunity-validation",
        frozenset(
            {
                "opportunity_claim",
                "target_user",
                "buyer",
                "approver",
                "problem_evidence",
                "commercial_evidence",
                "access_evidence",
                "switching_friction",
                "not_funded",
                "residual_risk",
                "confidence",
            }
        ),
    ),
    "continue-change-stop": (
        "task-pack:founder:continue-change-stop",
        frozenset(
            {
                "original_hypothesis",
                "original_criteria",
                "observed_results",
                "evidence_validity",
                "failure_type_evidence",
                "released_or_used_capacity",
                "residual_risk",
                "exit_obligations",
                "confidence",
            }
        ),
    ),
}
SURFACES: Final[frozenset[str]] = frozenset(
    {"jangyeongsil", "jiphyeonjeon", "uigwe", "seungjeongwon", "planning"}
)
READINESS: Final[frozenset[str]] = frozenset({"blocked", "conditional", "ready"})
CONFIDENCE: Final[frozenset[str]] = frozenset({"low", "medium", "high"})
VALIDITIES: Final[frozenset[str]] = frozenset({"valid", "partially valid", "invalid"})


def _common(payload: dict[str, JsonValue]) -> str:
    missing = COMMON_FIELDS - frozenset(payload)
    if missing:
        raise FounderTaskEvidenceError(f"Founder evidence is missing {sorted(missing)}")
    for field in COMMON_FIELDS - {
        "evidence_refs",
        "forbidden_claims",
        "next_reversible_commitment",
    }:
        _ = text_like(payload.get(field), field)
    _ = text_list(payload.get("evidence_refs"), "evidence_refs")
    commitment(payload.get("next_reversible_commitment"))
    forbidden_claims(payload.get("forbidden_claims"))
    readiness = text(payload.get("decision_readiness"), "decision_readiness").casefold()
    if readiness not in READINESS:
        raise FounderTaskEvidenceError("decision_readiness is unsupported")
    surface = text(payload.get("next_surface"), "next_surface").casefold()
    if surface not in SURFACES:
        raise FounderTaskEvidenceError("next_surface is unsupported")
    if not authority_is_bounded(payload):
        raise FounderTaskEvidenceError("authority boundary is exceeded")
    return readiness


def _readiness(payload: dict[str, JsonValue], readiness: str) -> None:
    action = text(payload.get("recommended_action"), "recommended_action").casefold()
    if readiness == "blocked":
        if not any(
            token in action for token in ("evidence", "observe", "interview", "measure")
        ):
            raise FounderTaskEvidenceError(
                "blocked readiness requires an evidence request"
            )
        return
    if readiness == "conditional":
        commitment(payload.get("next_reversible_commitment"))
        return
    if readiness == "ready":
        return
    raise FounderTaskEvidenceError("decision_readiness is unsupported")


def _pack(payload: dict[str, JsonValue], task_type: str) -> None:
    _, fields = PACK_FIELDS[task_type]
    missing = fields - frozenset(payload)
    if missing:
        raise FounderTaskEvidenceError(
            f"{task_type} evidence is missing {sorted(missing)}"
        )
    for field in fields - {"confidence", "evidence_validity"}:
        _ = text_like(payload.get(field), field)
    confidence = text(payload.get("confidence"), "confidence").casefold()
    if confidence not in CONFIDENCE:
        raise FounderTaskEvidenceError("confidence is unsupported")
    if task_type == "continue-change-stop":
        validity = text(
            payload.get("evidence_validity"), "evidence_validity"
        ).casefold()
        if validity not in VALIDITIES:
            raise FounderTaskEvidenceError("evidence_validity is unsupported")
        action = text(
            payload.get("recommended_action"), "recommended_action"
        ).casefold()
        if action not in {"continue", "change", "pause", "stop"}:
            raise FounderTaskEvidenceError(
                "continue-change-stop recommended_action is unsupported"
            )


def validate_founder_task_evidence(
    value: JsonValue | None,
    *,
    task_type: str,
    task_pack_id: str,
) -> None:
    """Validate bounded Founder decision evidence for its assigned task pack."""
    if task_type not in PACK_FIELDS:
        raise FounderTaskEvidenceError(f"unsupported Founder task type: {task_type}")
    expected_pack = PACK_FIELDS[task_type][0]
    if task_pack_id != expected_pack:
        raise FounderTaskEvidenceError(
            f"Founder task pack mismatch: expected {expected_pack}"
        )
    payload = record(value, "Founder evidence")
    expected_fields = COMMON_FIELDS | PACK_FIELDS[task_type][1]
    actual_fields = frozenset(payload)
    if actual_fields != expected_fields:
        missing = sorted(expected_fields - actual_fields)
        extra = sorted(actual_fields - expected_fields)
        raise FounderTaskEvidenceError(
            f"Founder evidence has unsupported fields: missing={missing}, extra={extra}"
        )
    readiness = _common(payload)
    _readiness(payload, readiness)
    _pack(payload, task_type)


__all__ = ["FounderTaskEvidenceError", "JsonValue", "validate_founder_task_evidence"]
