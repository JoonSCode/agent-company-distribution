from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
from datetime import datetime, timedelta
from typing import Final

from agent_company_deps import JsonValue
from agent_company_design_review_context import TASK_PACKS
from agent_company_plan_delegation_binding import PlanAssignment, ValidatedPlan
from agent_company_plan_models import object_value

JsonObject = dict[str, JsonValue]
DESIGN_EVIDENCE_WINDOW: Final = timedelta(hours=24)
SEUNGJEONGWON_LEAD_ROLE: Final = "seungjeongwon"


def _worker_id(job_id: str, assignment: PlanAssignment) -> str:
    return f"{job_id}-{assignment.role}-{assignment.assignment_id}"


def _seungjeongwon_lead_id(job_id: str) -> str:
    return f"{job_id}-{SEUNGJEONGWON_LEAD_ROLE}-lead"


def design_evidence_context(
    job_id: str,
    assignment: PlanAssignment,
    plan: ValidatedPlan,
    context: JsonObject,
) -> JsonObject | None:
    if assignment.role != "design":
        return None
    selection = object_value(context.get("selection"), "knowledge selection")
    task_type = context.get("task_type")
    task_pack_id = selection.get("task_pack_id")
    if (
        not isinstance(task_type, str)
        or TASK_PACKS.get(task_type) != task_pack_id
    ):
        return None
    milestones = tuple(
        item for item in plan.milestones if item.leaf_id == assignment.leaf_id
    )
    if len(milestones) != 1:
        return None
    milestone = milestones[0]
    implementations = (
        tuple(
            item
            for item in plan.assignments
            if item.leaf_id in milestone.depends_on and item.role == "development"
        )
        if task_type == "implementation-design-qa"
        else tuple(
            item for item in plan.assignments if item.role == "development"
        )
    )
    verifiers = tuple(
        item for item in plan.assignments if item.role == "qa-release"
    )
    if len(implementations) != 1 or len(verifiers) > 1:
        return None
    if task_type == "implementation-design-qa" and len(verifiers) != 1:
        return None
    issued_at = context.get("issued_at")
    if not isinstance(issued_at, str):
        return None
    try:
        started_at = datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if started_at.tzinfo is None:
        return None
    implementation = implementations[0]
    verifier_id = (
        _worker_id(job_id, verifiers[0])
        if verifiers
        else _seungjeongwon_lead_id(job_id)
    )
    verifier_role = "qa-release" if verifiers else SEUNGJEONGWON_LEAD_ROLE
    deadline_at = started_at + DESIGN_EVIDENCE_WINDOW
    return {
        "task_type": task_type,
        "task_pack_id": task_pack_id,
        "implementation_owner_id": _worker_id(job_id, implementation),
        "implementation_owner_role": implementation.role,
        "verification_owners": [{
            "verification_owner_id": verifier_id,
            "verification_owner_role": verifier_role,
        }],
        "task_started_at": issued_at,
        "evidence_deadline_at": deadline_at.isoformat().replace("+00:00", "Z"),
    }
