from __future__ import annotations

# pyright: reportUnnecessaryComparison=false
from typing import Final, Literal, assert_never

from agent_company_deps import JsonValue
from agent_company_marketing_decision_runtime_contract import (
    MarketingDecisionRuntimeError,
    ScaleGate,
    error,
    exact_fields,
    object_value,
    readiness_value,
    text_value,
    text_values,
    validate_economics,
    validate_experiment,
)

type DecisionKind = Literal["artifact", "execution", "scale"]
type DecisionScope = Literal["narrow", "compound_monetization"]

TASK_PACKS: Final[dict[str, str]] = {
    "demand-positioning": "task-pack:marketing:demand-positioning",
    "experiment-growth": "task-pack:marketing:experiment-growth",
    "mobile-monetization": "task-pack:marketing:mobile-monetization",
}
TOP_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "format",
        "decision_scope",
        "decision_question",
        "stage",
        "known",
        "inferred",
        "unknown",
        "primary_objective",
        "rejected_or_deferred_tactics",
        "decision_slices",
        "next_decision",
        "execution_surface",
        "recommended_reasoning_owner",
    }
)
SLICE_FIELDS: Final[frozenset[str]] = frozenset(
    {"decision_id", "decision_kind", "readiness", "blockers", "allowed_output"}
)
EVIDENCE_ACTION_TEXT_FIELDS: Final[tuple[str, ...]] = (
    "objective",
    "method",
    "success_criteria",
    "failure_criteria",
    "downstream_quality_guardrail",
    "trust_guardrail",
    "stop_or_rollback",
    "owner",
)
EVIDENCE_ACTION_FIELDS: Final[frozenset[str]] = frozenset(
    {*EVIDENCE_ACTION_TEXT_FIELDS, "no_live_action"}
)

__all__ = ("MarketingDecisionRuntimeError", "validate_marketing_decision_for_task")


def _validate_evidence_action_output(
    decision: dict[str, JsonValue], output: str
) -> None:
    has_evidence_action = "evidence_action" in decision
    match output:
        case "evidence_action":
            if not has_evidence_action:
                error("evidence_action output requires the canonical evidence action")
            evidence_action = object_value(
                decision.get("evidence_action"), "evidence_action"
            )
            exact_fields(evidence_action, EVIDENCE_ACTION_FIELDS, "evidence_action")
            for field in EVIDENCE_ACTION_TEXT_FIELDS:
                _ = text_value(evidence_action.get(field), f"evidence_action.{field}")
            match evidence_action.get("no_live_action"):
                case True:
                    return
                case False | str() | int() | float() | list() | dict() | None:
                    error("evidence_action.no_live_action must be true")
                case unreachable:
                    assert_never(unreachable)
        case str():
            if has_evidence_action:
                error("evidence_action is allowed only with evidence_action output")


def _slice(value: JsonValue) -> tuple[DecisionKind, dict[str, JsonValue]]:
    decision = object_value(value, "decision slice")
    kind = text_value(decision.get("decision_kind"), "decision_kind")
    _ = text_value(decision.get("decision_id"), "decision_id")
    readiness = readiness_value(decision)
    blockers = tuple(text_values(decision.get("blockers"), "blockers"))
    output = text_value(decision.get("allowed_output"), "allowed_output")
    match kind:
        case "artifact":
            extra_fields: frozenset[str] = (
                frozenset(
                    field
                    for field in ("experiment", "evidence_action")
                    if field in decision
                )
            )
            fields = SLICE_FIELDS | extra_fields
            exact_fields(decision, fields, "artifact decision")
            _validate_evidence_action_output(decision, output)
            match readiness:
                case "blocked":
                    if (
                        not blockers
                        or decision.get("experiment") is not None
                        or output not in {"none", "evidence_action"}
                    ):
                        error("blocked artifact is invalid")
                case "conditional" | "ready":
                    match output:
                        case "bounded_blueprint":
                            validate_experiment(decision.get("experiment"))
                        case "none" | "evidence_action":
                            if decision.get("experiment") is not None:
                                error("artifact experiment requires bounded_blueprint")
                        case str():
                            error("artifact allowed_output is invalid")
                        case unreachable:
                            assert_never(unreachable)
                case unreachable:
                    assert_never(unreachable)
            return "artifact", decision
        case "execution":
            extra_fields = (
                frozenset({"evidence_action"})
                if "evidence_action" in decision
                else frozenset[str]()
            )
            exact_fields(decision, SLICE_FIELDS | extra_fields, "execution decision")
            _validate_evidence_action_output(decision, output)
            match readiness:
                case "ready":
                    if blockers or output != "execution_handoff":
                        error("ready execution requires a blocker-free handoff")
                case "blocked" | "conditional":
                    if output not in {"none", "evidence_action"}:
                        error("execution handoff requires ready execution")
                    if readiness == "blocked" and not blockers:
                        error("blocked execution requires blockers")
                case unreachable:
                    assert_never(unreachable)
            return "execution", decision
        case "scale":
            extra_fields = (
                frozenset({"evidence_action"})
                if "evidence_action" in decision
                else frozenset[str]()
            )
            exact_fields(
                decision,
                SLICE_FIELDS | {"monetization_economics"} | extra_fields,
                "scale decision",
            )
            _validate_evidence_action_output(decision, output)
            validate_economics(
                decision.get("monetization_economics"),
                ScaleGate(readiness=readiness, blockers=blockers, output=output),
            )
            return "scale", decision
        case str():
            error("decision_kind is invalid")
        case unreachable:
            assert_never(unreachable)


def validate_marketing_decision_for_task(
    value: JsonValue | None, *, task_type: str, task_pack_id: str
) -> None:
    """Validate completed Marketing evidence without non-stdlib dependencies."""
    if TASK_PACKS.get(task_type) != task_pack_id:
        error("marketing task classification binding is invalid")
    decision = object_value(value, "marketing decision")
    exact_fields(decision, TOP_FIELDS, "marketing decision")
    if decision.get("format") != "agent-company.marketing-decision/v0.1":
        error("marketing decision format is invalid")
    match decision.get("decision_scope"):
        case "narrow" | "compound_monetization" as scope:
            decision_scope = scope
        case str() | bool() | int() | float() | list() | dict() | None:
            error("decision_scope is invalid")
        case unreachable:
            assert_never(unreachable)
    for field in (
        "decision_question",
        "stage",
        "primary_objective",
        "next_decision",
        "execution_surface",
        "recommended_reasoning_owner",
    ):
        _ = text_value(decision.get(field), field)
    for field in ("known", "inferred", "unknown"):
        _ = text_values(decision.get(field), field)
    if not text_values(
        decision.get("rejected_or_deferred_tactics"), "rejected_or_deferred_tactics"
    ):
        error("rejected_or_deferred_tactics must be non-empty")
    match decision.get("decision_slices"):
        case list() as slices if 1 <= len(slices) <= 3:
            parsed = tuple(_slice(item) for item in slices)
        case list() | str() | bool() | int() | float() | dict() | None:
            error("decision_slices must contain one to three decisions")
        case unreachable:
            assert_never(unreachable)
    kinds = {kind for kind, _ in parsed}
    identifiers = {
        text_value(item.get("decision_id"), "decision_id") for _, item in parsed
    }
    if len(kinds) != len(parsed) or len(identifiers) != len(parsed):
        error("decision_slices require unique decision kinds and identifiers")
    match decision_scope:
        case "narrow":
            pass
        case "compound_monetization":
            if len(parsed) != 3 or kinds != {"artifact", "execution", "scale"}:
                error(
                    "compound monetization requires artifact, execution, and scale decisions"
                )
    artifact = next((item for kind, item in parsed if kind == "artifact"), None)
    if artifact is None:
        return
    match readiness_value(artifact):
        case "conditional":
            if artifact.get("allowed_output") != "bounded_blueprint":
                error("conditional marketing task requires a bounded blueprint")
            validate_experiment(artifact.get("experiment"))
        case "blocked" | "ready":
            return
        case unreachable:
            assert_never(unreachable)
