#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Import build_compact_report from this module.
# ─────────────────

"""Project immutable canonical and route bindings into compact status."""

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false, reportUnnecessaryComparison=false

from typing import TypeAlias, assert_never

from agent_company_compact_canonical import validate_canonical_binding
from agent_company_compact_models import (
    CanonicalBinding,
    CanonicalEntry,
    CompactReport,
    EvidenceState,
    OverallState,
    Risk,
    ValidatedRoute,
)
from agent_company_compact_route import validate_route_binding
from agent_company_route_contract import JsonValue
from agent_company_projection_policy import PolicyError


JsonObject: TypeAlias = dict[str, JsonValue]


def _lane(roles: tuple[str, ...]) -> str:
    return "direct" if not roles else "role" if len(roles) == 1 else "squad"


def _verification(entries: tuple[CanonicalEntry, ...], reported: OverallState) -> OverallState:
    states = {entry.state for entry in entries}
    match reported:
        case OverallState.VERIFIED:
            return OverallState.VERIFIED if states == {EvidenceState.VERIFIED} else OverallState.MIXED
        case OverallState.EXECUTED:
            return OverallState.EXECUTED if states <= {EvidenceState.EXECUTED, EvidenceState.VERIFIED} else OverallState.MIXED
        case OverallState.FAILED | OverallState.BLOCKED | OverallState.UNVERIFIED | OverallState.MIXED:
            return reported
        case unreachable:
            assert_never(unreachable)


def _material_risks(
    entries: tuple[CanonicalEntry, ...], reported: OverallState,
) -> tuple[Risk, ...]:
    risks: list[Risk] = []
    seen: set[tuple[EvidenceState, str, tuple[str, ...]]] = set()
    adverse = {EvidenceState.FAILED, EvidenceState.BLOCKED, EvidenceState.UNVERIFIED}
    for entry in entries:
        identity = (entry.state, entry.summary, entry.evidence_refs)
        if entry.state in adverse and identity not in seen:
            seen.add(identity)
            risks.append(Risk(*identity))
    match reported:
        case OverallState.FAILED:
            state = EvidenceState.FAILED
        case OverallState.BLOCKED:
            state = EvidenceState.BLOCKED
        case OverallState.UNVERIFIED | OverallState.MIXED:
            state = EvidenceState.UNVERIFIED
        case OverallState.EXECUTED | OverallState.VERIFIED:
            return tuple(risks)
        case unreachable:
            assert_never(unreachable)
    if not any(risk.state is state for risk in risks):
        risks.append(Risk(
            state,
            f"Canonical overall status is {reported.value} without matching itemized evidence.",
            (),
        ))
    return tuple(risks)


def _project(source: CanonicalBinding, route: ValidatedRoute) -> CompactReport:
    source = validate_canonical_binding(source)
    route = validate_route_binding(route)
    lane = _lane(source.report.ordinary_roles)
    if route.lane != lane or route.ordinary_roles != source.report.ordinary_roles:
        raise PolicyError("validated route contradicts canonical report roles")
    risks = _material_risks(source.report.entries, source.report.overall_status)
    links = tuple(dict.fromkeys((
        source.ref,
        *route.evidence_refs,
        *(ref for entry in source.report.entries for ref in entry.evidence_refs),
    )))
    decision_risk = risks[0] if risks else None
    return CompactReport(
        source,
        route,
        lane,
        source.report.decision_summary,
        _verification(source.report.entries, source.report.overall_status),
        decision_risk is not None,
        decision_risk.summary if decision_risk is not None else "None recorded in canonical state.",
        risks,
        source.report.next_actions[0] if source.report.next_actions else "None recorded in canonical state.",
        links,
    )


def build_compact_report(source: CanonicalBinding, route: ValidatedRoute) -> CompactReport:
    """Build an immutable compact report from byte-bound validated inputs."""
    return _project(source, route)


def validate_compact_report(report: CompactReport) -> CompactReport:
    """Reproject source bytes to reject replaced or manually constructed views."""
    expected = _project(report.source, report.route)
    if expected != report:
        raise PolicyError("compact report fields contradict their bound canonical state")
    return expected


def compact_report_json(report: CompactReport) -> JsonObject:
    """Serialize only after immutable projection revalidation."""
    report = validate_compact_report(report)
    source: JsonObject = {
        "format": "agent-company.ceo-report/v0.1",
        "job_id": report.source.report.job_id,
        "ref": report.source.ref,
        "sha256": report.source.sha256,
        "overall_status": report.source.report.overall_status.value,
    }
    risk_values: list[JsonValue] = []
    for risk in report.material_risks:
        risk_values.append({
            "state": risk.state.value,
            "summary": risk.summary,
            "evidence_refs": list(risk.evidence_refs),
        })
    return {
        "format": "agent-company.compact-ceo-report/v0.2",
        "source_report": source,
        "lane": report.lane,
        "outcome": report.outcome,
        "verification": report.verification.value,
        "decision_required": report.decision_required,
        "decision_prompt": report.decision_prompt,
        "material_risks": risk_values,
        "next_action": report.next_action,
        "evidence_links": list(report.evidence_links),
    }
