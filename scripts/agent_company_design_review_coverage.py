from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportUnnecessaryComparison=false
from typing import Literal, TypeIs, assert_never

from agent_company_design_review_common import (
    DesignReviewContractError,
    configured_texts,
    exact,
    record,
    records,
    text,
    texts,
)
from agent_company_role_schema import JsonValue

type CoverageDisposition = Literal["covered", "unknown", "source_backed_omitted"]


def _is_disposition(value: JsonValue | None) -> TypeIs[CoverageDisposition]:
    return value in {"covered", "unknown", "source_backed_omitted"}


def validate_conditions(
    payload: dict[str, JsonValue],
    ledger: dict[str, JsonValue],
) -> tuple[frozenset[str], tuple[int, int, int]]:
    reconciliation = record(
        ledger.get("coverage_reconciliation"),
        "coverage reconciliation",
    )
    origins = frozenset(configured_texts(reconciliation, "condition_origins"))
    kinds = frozenset(configured_texts(reconciliation, "condition_kinds"))
    dispositions = frozenset(configured_texts(reconciliation, "dispositions"))
    condition_ids: list[str] = []
    for index, condition in enumerate(records(payload.get("conditions"), "conditions")):
        exact(
            condition,
            frozenset({"condition_id", "kind", "origin", "source_ref"}),
            f"conditions[{index}]",
        )
        condition_id = text(condition.get("condition_id"))
        if (
            condition_id is None
            or text(condition.get("source_ref")) is None
            or condition.get("kind") not in kinds
            or condition.get("origin") not in origins
        ):
            raise DesignReviewContractError(
                "condition_invalid",
                f"conditions[{index}] is incomplete",
            )
        condition_ids.append(condition_id)
    expected = frozenset(condition_ids)
    if len(expected) != len(condition_ids):
        raise DesignReviewContractError(
            "coverage_mismatch",
            "condition ids must be unique",
        )

    coverage_ids: list[str] = []
    covered = unknown = omitted = 0
    for index, cell in enumerate(records(payload.get("coverage"), "coverage")):
        condition_id = text(cell.get("condition_id"))
        raw_disposition = cell.get("disposition")
        if (
            condition_id is None
            or raw_disposition not in dispositions
            or not _is_disposition(raw_disposition)
        ):
            raise DesignReviewContractError(
                "coverage_mismatch",
                f"coverage[{index}] is invalid",
            )
        disposition = raw_disposition
        match disposition:
            case "covered":
                exact(
                    cell,
                    frozenset({"condition_id", "disposition", "evidence_ref"}),
                    f"coverage[{index}]",
                )
                if text(cell.get("evidence_ref")) is None:
                    raise DesignReviewContractError(
                        "coverage_mismatch",
                        "covered evidence is empty",
                    )
                covered += 1
            case "unknown":
                exact(
                    cell,
                    frozenset({"condition_id", "disposition", "reason"}),
                    f"coverage[{index}]",
                )
                if text(cell.get("reason")) is None:
                    raise DesignReviewContractError(
                        "coverage_mismatch",
                        "unknown reason is empty",
                    )
                unknown += 1
            case "source_backed_omitted":
                if (
                    text(cell.get("omission_source_ref")) is None
                    or text(cell.get("reason")) is None
                ):
                    raise DesignReviewContractError(
                        "omission_unbacked",
                        "omitted conditions require source and reason",
                    )
                exact(
                    cell,
                    frozenset(
                        {
                            "condition_id",
                            "disposition",
                            "omission_source_ref",
                            "reason",
                        }
                    ),
                    f"coverage[{index}]",
                )
                omitted += 1
            case unreachable:
                assert_never(unreachable)
        coverage_ids.append(condition_id)
    if frozenset(coverage_ids) != expected or len(coverage_ids) != len(expected):
        raise DesignReviewContractError(
            "coverage_mismatch",
            "every declared condition must be reconciled exactly once",
        )
    return expected, (covered, unknown, omitted)


def validate_scenarios(
    payload: dict[str, JsonValue],
    condition_ids: frozenset[str],
) -> frozenset[str]:
    scenario_ids: list[str] = []
    referenced: set[str] = set()
    environments: list[str] = []
    for index, scenario in enumerate(records(payload.get("scenarios"), "scenarios")):
        exact(
            scenario,
            frozenset({"scenario_id", "purpose", "condition_ids", "environment_id"}),
            f"scenarios[{index}]",
        )
        scenario_id = text(scenario.get("scenario_id"))
        environment_id = text(scenario.get("environment_id"))
        linked = frozenset(texts(scenario.get("condition_ids"), "condition_ids"))
        if (
            scenario_id is None
            or environment_id is None
            or text(scenario.get("purpose")) is None
            or not linked
            or not linked.issubset(condition_ids)
        ):
            raise DesignReviewContractError(
                "scenario_ledger_invalid",
                f"scenarios[{index}] is incomplete",
            )
        scenario_ids.append(scenario_id)
        environments.append(environment_id)
        referenced.update(linked)
    if len(set(scenario_ids)) != len(scenario_ids) or referenced != set(condition_ids):
        raise DesignReviewContractError(
            "scenario_ledger_invalid",
            "named scenarios must uniquely cover every condition",
        )
    return frozenset(environments)
