from __future__ import annotations

# pyright: reportUnnecessaryComparison=false
from dataclasses import dataclass
from typing import Final, Literal, Never, assert_never

from agent_company_deps import JsonValue


class MarketingDecisionRuntimeError(Exception):
    """Raised when completed Marketing evidence violates the runtime contract."""

    detail: str

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


type Readiness = Literal["blocked", "conditional", "ready"]


@dataclass(frozen=True, slots=True)
class ScaleGate:
    readiness: Readiness
    blockers: tuple[str, ...]
    output: str


EXPERIMENT_TEXT_FIELDS: Final[tuple[str, ...]] = (
    "hypothesis",
    "intervention",
    "audience",
    "comparison",
    "arms_and_allocation",
    "unit_of_assignment",
    "exposure_eligibility",
    "instrumentation",
    "primary_metric",
    "primary_metric_denominator",
    "observation_window",
    "success_criteria",
    "failure_criteria",
    "downstream_quality_guardrail",
    "trust_guardrail",
    "guardrails",
    "decision_rule",
    "confounders",
    "stop_or_rollback",
    "owner",
    "win_action",
    "loss_action",
    "inconclusive_action",
    "tested_variable",
)
EXPERIMENT_FIELDS: Final[frozenset[str]] = frozenset(
    {*EXPERIMENT_TEXT_FIELDS, "fixed_variables", "external_outcome_transfer"}
)
ECONOMICS_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "revenue_basis",
        "currency",
        "included_adjustments",
        "excluded_adjustments",
        "economic_denominator",
        "acquisition_cost_treatment",
        "acquisition_cost_allocation_rule",
        "cohort_maturity_rule",
        "marginal_scale_rule",
    }
)


def error(detail: str) -> Never:
    raise MarketingDecisionRuntimeError(detail)


def object_value(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    match value:
        case dict() as result:
            return result
        case str() | bool() | int() | float() | list() | None:
            error(f"{label} must be an object")
        case unreachable:
            assert_never(unreachable)


def text_value(value: JsonValue | None, label: str) -> str:
    match value:
        case str() as result if result.strip():
            return result.strip()
        case str() | bool() | int() | float() | list() | dict() | None:
            error(f"{label} must be non-empty text")
        case unreachable:
            assert_never(unreachable)


def text_values(value: JsonValue | None, label: str) -> list[str]:
    match value:
        case list() as values:
            return [
                text_value(item, f"{label}[{index}]")
                for index, item in enumerate(values)
            ]
        case str() | bool() | int() | float() | dict() | None:
            error(f"{label} must be a list")
        case unreachable:
            assert_never(unreachable)


def exact_fields(
    value: dict[str, JsonValue], expected: frozenset[str], label: str
) -> None:
    if frozenset(value) != expected:
        error(f"{label} has an unsupported shape")


def readiness_value(value: dict[str, JsonValue]) -> Readiness:
    readiness = text_value(value.get("readiness"), "readiness")
    match readiness:
        case "blocked" | "conditional" | "ready":
            return readiness
        case str():
            error("readiness is invalid")
        case unreachable:
            assert_never(unreachable)


def validate_experiment(value: JsonValue | None) -> None:
    experiment = object_value(value, "experiment")
    exact_fields(experiment, EXPERIMENT_FIELDS, "experiment")
    for field in EXPERIMENT_TEXT_FIELDS:
        _ = text_value(experiment.get(field), f"experiment.{field}")
    fixed = text_values(experiment.get("fixed_variables"), "experiment.fixed_variables")
    if not fixed:
        error("experiment.fixed_variables must be non-empty")
    normalized = tuple(
        item.casefold().replace("_", " ").replace("-", " ") for item in fixed
    )
    if len(set(normalized)) != len(normalized):
        error("experiment.fixed_variables must be unique")
    tested = text_value(experiment.get("tested_variable"), "experiment.tested_variable")
    normalized_tested = tested.casefold().replace("_", " ").replace("-", " ")
    if normalized_tested in normalized:
        error("experiment.tested_variable cannot also be fixed")
    if any(
        term in normalized_tested
        for term in ("paywall", "price presentation", "offer presentation")
    ):
        required = {
            "audience",
            "eligibility",
            "offer",
            "price",
            "paywall timing",
            "channel",
            "product experience",
            "measurement",
        }
        if not required.issubset(normalized):
            error("paywall presentation requires the canonical fixed variables")
    match experiment.get("external_outcome_transfer"):
        case "forbidden":
            return
        case str() | bool() | int() | float() | list() | dict() | None:
            error("experiment.external_outcome_transfer must be forbidden")
        case unreachable:
            assert_never(unreachable)


def validate_economics(value: JsonValue | None, gate: ScaleGate) -> None:
    economics = object_value(value, "monetization_economics")
    exact_fields(economics, ECONOMICS_FIELDS, "monetization_economics")
    for field in (
        "currency",
        "economic_denominator",
        "acquisition_cost_allocation_rule",
        "cohort_maturity_rule",
        "marginal_scale_rule",
    ):
        _ = text_value(economics.get(field), f"monetization_economics.{field}")
    included = set(
        text_values(economics.get("included_adjustments"), "included_adjustments")
    )
    excluded = set(
        text_values(economics.get("excluded_adjustments"), "excluded_adjustments")
    )
    if included & excluded:
        error("revenue adjustments cannot be both included and excluded")
    match economics.get("revenue_basis"):
        case "gross" | "settled" | "net":
            pass
        case str() | bool() | int() | float() | list() | dict() | None:
            error("monetization_economics.revenue_basis is invalid")
        case unreachable:
            assert_never(unreachable)
    treatment = text_value(
        economics.get("acquisition_cost_treatment"), "acquisition_cost_treatment"
    )
    match treatment:
        case "held_constant_excluded_from_primary" | "not_applicable":
            pass
        case "allocated_to_assigned_cohort":
            rule = text_value(
                economics.get("acquisition_cost_allocation_rule"), "allocation rule"
            ).casefold()
            if "blended" in rule or "assigned" not in rule or "cohort" not in rule:
                error("assigned-cohort acquisition cost needs a cohort allocation rule")
        case str():
            error("monetization_economics.acquisition_cost_treatment is invalid")
        case unreachable:
            assert_never(unreachable)
    match gate.readiness:
        case "ready":
            if gate.blockers or gate.output != "execution_handoff":
                error("ready scale requires a blocker-free handoff")
            declarations = (
                text_value(economics.get("currency"), "currency"),
                text_value(
                    economics.get("economic_denominator"), "economic denominator"
                ),
                text_value(
                    economics.get("acquisition_cost_allocation_rule"), "allocation rule"
                ),
                text_value(economics.get("cohort_maturity_rule"), "maturity rule"),
                text_value(economics.get("marginal_scale_rule"), "scale rule"),
            )
            if any("unknown" in item.casefold() for item in declarations):
                error("ready scale forbids unknown economics")
            scale_rule = declarations[-1].casefold()
            if (
                "marginal" not in scale_rule
                or "blended" in scale_rule
                or "average" in scale_rule
            ):
                error("ready scale requires marginal scale evidence")
        case "blocked" | "conditional":
            if gate.output not in {"none", "evidence_action"}:
                error("scale handoff requires ready economics")
            if gate.readiness == "blocked" and not gate.blockers:
                error("blocked scale requires blockers")
        case unreachable:
            assert_never(unreachable)
