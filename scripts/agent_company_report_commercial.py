from __future__ import annotations

from dataclasses import dataclass

from agent_company_deps import JsonValue
from agent_company_job_policy import text


@dataclass(frozen=True, slots=True)
class CompanyCommercialProjection:
    summary: str
    claim: dict[str, JsonValue] | None
    risk: str | None
    state: str | None
    needs_evidence: bool


def project_company_commercial(
    job: dict[str, JsonValue],
) -> CompanyCommercialProjection:
    company_context = job.get("company_context")
    if not isinstance(company_context, dict):
        return CompanyCommercialProjection("", None, None, None, False)
    hypothesis = text(
        company_context.get("commercial_hypothesis"),
        "commercial_hypothesis",
    )
    evidence_state = text(
        company_context.get("commercial_evidence_state"),
        "commercial_evidence_state",
    )
    summary = (
        f" Initiative {text(company_context.get('initiative_id'), 'initiative_id')} "
        f"origin={text(company_context.get('initiative_origin'), 'initiative_origin')} "
        f"commercial_evidence={evidence_state}."
    )
    if evidence_state == "observed":
        return CompanyCommercialProjection(
            summary, None, None, evidence_state, False,
        )
    return CompanyCommercialProjection(
        summary,
        {
            "claim": hypothesis,
            "state": "unverified",
            "evidence_refs": [],
        },
        f"Commercial hypothesis remains {evidence_state}: {hypothesis}",
        evidence_state,
        True,
    )
