from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import re
from dataclasses import dataclass
from typing import Final

from agent_company_design_review_common import (
    DesignReviewContractError,
    contract_ledger,
    exact,
    record,
    text,
)
from agent_company_design_review_context import TrustedReviewContext
from agent_company_design_review_coverage import (
    validate_conditions,
    validate_scenarios,
)
from agent_company_design_review_evidence import (
    ProvenanceContext,
    validate_provenance,
    validate_verification_layers,
    validate_visual_contract,
)
from agent_company_design_review_observations import validate_observation_coverage
from agent_company_role_schema import JsonValue


@dataclass(frozen=True, slots=True)
class DesignReviewAssessment:
    review_readiness: str
    conclusion_readiness: str
    observation_conclusion: str
    covered_conditions: int
    unknown_conditions: int
    omitted_conditions: int


FORMAT: Final[str] = "agent-company.design-implementation-review/v0.1"
ROOT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "format",
        "candidate",
        "surface",
        "conclusion_oracle",
        "conditions",
        "coverage",
        "scenarios",
        "environments",
        "observations",
        "motion_tokens",
        "reflow_expectations",
        "verification_layers",
    }
)
HASH: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


def assess_design_review(
    payload: JsonValue,
    context: TrustedReviewContext,
) -> DesignReviewAssessment:
    review = record(payload, "review")
    exact(review, ROOT_FIELDS, "review")
    if review.get("format") != FORMAT:
        raise DesignReviewContractError(
            "review_shape_invalid",
            "review format is unsupported",
        )
    ledger = contract_ledger()
    candidate = record(review.get("candidate"), "candidate")
    surface = record(review.get("surface"), "surface")
    oracle = record(review.get("conclusion_oracle"), "conclusion oracle")
    exact(
        candidate,
        frozenset({"candidate_id", "artifact_sha256", "implementation_owner_id"}),
        "candidate",
    )
    exact(
        surface,
        frozenset({"surface_id", "runtime_entry", "observation_authority_ref"}),
        "surface",
    )
    exact(
        oracle,
        frozenset({"approved_intent_ref", "oracle_ref"}),
        "conclusion oracle",
    )
    candidate_id = text(candidate.get("candidate_id"))
    artifact_sha = text(candidate.get("artifact_sha256"))
    implementation_owner_id = text(candidate.get("implementation_owner_id"))
    if implementation_owner_id != context.implementation_owner.owner_id:
        raise DesignReviewContractError(
            "implementation_owner_mismatch",
            "candidate implementation owner differs from trusted session ownership",
        )
    review_ready = bool(
        candidate_id
        and artifact_sha
        and HASH.fullmatch(artifact_sha)
        and implementation_owner_id
        and text(surface.get("surface_id"))
        and text(surface.get("runtime_entry"))
        and text(surface.get("observation_authority_ref"))
    )
    conclusion_ready = bool(
        text(oracle.get("approved_intent_ref"))
        and text(oracle.get("oracle_ref"))
    )
    condition_ids, counts = validate_conditions(review, ledger)
    scenario_environments = validate_scenarios(review, condition_ids)
    validate_provenance(
        review,
        ProvenanceContext(candidate_id, scenario_environments, ledger),
    )
    validate_visual_contract(review, ledger)
    validate_verification_layers(review, context, ledger)
    validate_observation_coverage(review, candidate_id, ledger, context)
    return DesignReviewAssessment(
        "evidence_ready" if review_ready else "blocked",
        "ready" if conclusion_ready else "unknown",
        "classified" if conclusion_ready else "unknown",
        counts[0],
        counts[1],
        counts[2],
    )


__all__ = [
    "DesignReviewAssessment",
    "DesignReviewContractError",
    "assess_design_review",
]
