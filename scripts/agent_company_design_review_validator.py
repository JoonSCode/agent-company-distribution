from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportUnnecessaryComparison=false
from typing import assert_never

from agent_company_design_review_context import parse_trusted_review_context
from agent_company_design_review_contract import (
    DesignReviewAssessment,
    assess_design_review,
)
from agent_company_design_task_evidence import (
    FORMAT as DESIGN_TASK_EVIDENCE_FORMAT,
)
from agent_company_design_task_evidence import (
    DesignTaskEvidenceAssessment,
    validate_bounded_design_task_evidence,
)
from agent_company_role_schema import JsonValue


def validate_design_role_evidence(
    role_evidence: JsonValue,
    trusted_context: JsonValue,
) -> DesignReviewAssessment | DesignTaskEvidenceAssessment:
    """Validate raw Design review evidence against trusted task/session ownership."""
    context = parse_trusted_review_context(trusted_context)
    match context.task_type:
        case "implementation-design-qa":
            if (
                isinstance(role_evidence, dict)
                and role_evidence.get("format") == DESIGN_TASK_EVIDENCE_FORMAT
            ):
                return validate_bounded_design_task_evidence(
                    role_evidence,
                    context,
                )
            return assess_design_review(role_evidence, context)
        case "flow-interaction" | "visual-system-accessibility":
            return validate_bounded_design_task_evidence(role_evidence, context)
        case unreachable:
            assert_never(unreachable)


__all__ = [
    "DesignTaskEvidenceAssessment",
    "validate_design_role_evidence",
]
