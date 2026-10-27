from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportUnnecessaryComparison=false
from dataclasses import dataclass
from typing import Final, assert_never

from agent_company_design_review_common import (
    DesignReviewContractError,
    exact,
    record,
    records,
    text,
    texts,
)
from agent_company_design_review_context import TrustedReviewContext
from agent_company_role_schema import JsonValue

FORMAT: Final[str] = "agent-company.design-task-evidence/v0.1"
ROOT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "format",
        "task_type",
        "task_pack_id",
        "decision",
        "evidence",
        "scenarios",
        "deliverables",
        "verification",
        "stop",
    }
)
FORBIDDEN_CLAIMS: Final[frozenset[str]] = frozenset(
    {"final verification", "release readiness", "Uigwe approval"}
)
IMPLEMENTATION_QA_FORBIDDEN_CLAIMS: Final[frozenset[str]] = (
    FORBIDDEN_CLAIMS
    | frozenset({"candidate conformance", "candidate disposition"})
)
# Current producers use Company surfaces. Historical labels remain readable
# without translating them into a new owner, permission, or Core execution path.
CURRENT_NEXT_SURFACES: Final[frozenset[str]] = frozenset(
    {"company-lead", "planning", "qa-release", "user"}
)
LEGACY_NEXT_SURFACES: Final[frozenset[str]] = frozenset(
    {"jangyeongsil", "jiphyeonjeon", "uigwe", "seungjeongwon"}
)
NEXT_SURFACES: Final[frozenset[str]] = CURRENT_NEXT_SURFACES | LEGACY_NEXT_SURFACES


@dataclass(frozen=True, slots=True)
class DesignTaskEvidenceAssessment:
    evidence_readiness: str
    decision_status: str
    scenario_count: int


def _required_texts(value: JsonValue | None, label: str) -> tuple[str, ...]:
    result = texts(value, label)
    if not result:
        raise DesignReviewContractError(
            "design_task_evidence_incomplete",
            f"{label} must not be empty",
        )
    return result


def _validate_decision(payload: dict[str, JsonValue]) -> str:
    decision = record(payload.get("decision"), "decision")
    exact(
        decision,
        frozenset(
            {
                "status",
                "selected_direction",
                "serious_alternative",
                "rejection_evidence_refs",
                "revival_condition",
            }
        ),
        "decision",
    )
    status = text(decision.get("status"))
    if (
        status not in {"proposed", "conditional", "blocked"}
        or text(decision.get("selected_direction")) is None
        or text(decision.get("serious_alternative")) is None
        or text(decision.get("revival_condition")) is None
    ):
        raise DesignReviewContractError(
            "design_task_evidence_incomplete",
            "decision fields are incomplete",
        )
    _ = _required_texts(
        decision.get("rejection_evidence_refs"),
        "decision.rejection_evidence_refs",
    )
    return status


def _validate_evidence(payload: dict[str, JsonValue]) -> None:
    evidence = record(payload.get("evidence"), "evidence")
    exact(
        evidence,
        frozenset({"known", "inferred", "unknown", "source_refs", "artifact_refs"}),
        "evidence",
    )
    for field in ("known", "inferred", "unknown"):
        _ = texts(evidence.get(field), f"evidence.{field}")
    _ = _required_texts(evidence.get("source_refs"), "evidence.source_refs")
    _ = _required_texts(evidence.get("artifact_refs"), "evidence.artifact_refs")


def _validate_scenarios(payload: dict[str, JsonValue]) -> int:
    scenarios = records(payload.get("scenarios"), "scenarios")
    if not scenarios:
        raise DesignReviewContractError(
            "design_task_evidence_incomplete",
            "at least one named scenario is required",
        )
    scenario_ids: list[str] = []
    fields = frozenset(
        {
            "scenario_id",
            "evidence_refs",
            "accessibility_checks",
            "verification_steps",
        }
    )
    for index, scenario in enumerate(scenarios):
        exact(scenario, fields, f"scenarios[{index}]")
        scenario_id = text(scenario.get("scenario_id"))
        if scenario_id is None:
            raise DesignReviewContractError(
                "design_task_evidence_incomplete",
                f"scenarios[{index}].scenario_id is required",
            )
        scenario_ids.append(scenario_id)
        for field in ("evidence_refs", "accessibility_checks", "verification_steps"):
            _ = _required_texts(
                scenario.get(field),
                f"scenarios[{index}].{field}",
            )
    if len(scenario_ids) != len(set(scenario_ids)):
        raise DesignReviewContractError(
            "design_task_evidence_incomplete",
            "scenario identities must be unique",
        )
    return len(scenarios)


def _validate_deliverables(
    payload: dict[str, JsonValue],
    context: TrustedReviewContext,
) -> None:
    deliverables = record(payload.get("deliverables"), "deliverables")
    match context.task_type:
        case "flow-interaction":
            fields = (
                "information_architecture_refs",
                "state_transition_refs",
                "accessibility_behavior_refs",
            )
        case "visual-system-accessibility":
            fields = (
                "semantic_token_refs",
                "accessibility_constraint_refs",
                "proportional_artifact_refs",
            )
        case "implementation-design-qa":
            fields = (
                "semantic_direction_refs",
                "source_constraint_refs",
                "candidate_evidence_request_refs",
            )
        case unreachable:
            assert_never(unreachable)
    exact(deliverables, frozenset(fields), "deliverables")
    for field in fields:
        _ = _required_texts(deliverables.get(field), f"deliverables.{field}")


def _validate_verification(
    payload: dict[str, JsonValue],
    context: TrustedReviewContext,
) -> None:
    verification = record(payload.get("verification"), "verification")
    exact(
        verification,
        frozenset(
            {
                "implementation_owner_id",
                "verification_owner_ids",
                "plan_refs",
            }
        ),
        "verification",
    )
    owner_ids = frozenset(
        _required_texts(
            verification.get("verification_owner_ids"),
            "verification.verification_owner_ids",
        )
    )
    trusted_ids = {owner.owner_id for owner in context.verification_owners}
    if (
        verification.get("implementation_owner_id")
        != context.implementation_owner.owner_id
        or set(owner_ids) != trusted_ids
    ):
        raise DesignReviewContractError(
            "verification_owner_not_independent",
            "verification ownership differs from the trusted session mapping",
        )
    _ = _required_texts(verification.get("plan_refs"), "verification.plan_refs")


def _validate_stop(
    payload: dict[str, JsonValue],
    context: TrustedReviewContext,
) -> None:
    stop = record(payload.get("stop"), "stop")
    exact(
        stop,
        frozenset({"next_recommended_surface", "stop_reason", "forbidden_claims"}),
        "stop",
    )
    expected_forbidden = (
        IMPLEMENTATION_QA_FORBIDDEN_CLAIMS
        if context.task_type == "implementation-design-qa"
        else FORBIDDEN_CLAIMS
    )
    if (
        text(stop.get("next_recommended_surface")) not in NEXT_SURFACES
        or text(stop.get("stop_reason")) is None
        or frozenset(texts(stop.get("forbidden_claims"), "stop.forbidden_claims"))
        != expected_forbidden
    ):
        raise DesignReviewContractError(
            "design_task_evidence_incomplete",
            "stop boundary is incomplete",
        )


def validate_bounded_design_task_evidence(
    value: JsonValue,
    context: TrustedReviewContext,
) -> DesignTaskEvidenceAssessment:
    payload = record(value, "design task evidence")
    exact(payload, ROOT_FIELDS, "design task evidence")
    if (
        payload.get("format") != FORMAT
        or payload.get("task_type") != context.task_type
        or payload.get("task_pack_id") != context.task_pack_id
    ):
        raise DesignReviewContractError(
            "design_task_binding_mismatch",
            "evidence task pair differs from the trusted assignment",
        )
    status = _validate_decision(payload)
    _validate_evidence(payload)
    scenario_count = _validate_scenarios(payload)
    _validate_deliverables(payload, context)
    _validate_verification(payload, context)
    _validate_stop(payload, context)
    return DesignTaskEvidenceAssessment("bounded", status, scenario_count)
