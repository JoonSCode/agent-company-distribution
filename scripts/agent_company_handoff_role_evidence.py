from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
from typing import assert_never, override

from agent_company_deps import JsonValue
from agent_company_design_review_common import DesignReviewContractError
from agent_company_design_review_validator import validate_design_role_evidence
from agent_company_development_evidence import (
    DevelopmentEvidenceError,
    validate_development_task_evidence,
)
from agent_company_founder_task_evidence import (
    FounderTaskEvidenceError,
    validate_founder_task_evidence,
)
from agent_company_knowledge_context import KnowledgeContext
from agent_company_planning_invariants import (
    PlanningInvariantError,
    validate_planning_invariants,
)

INTEGRATED_ROLES = frozenset(
    {"founder", "planning", "marketing", "design", "development"}
)
ENVELOPE_FIELDS = frozenset(
    {
        "task_type",
        "task_pack_id",
        "context_binding",
        "disposition",
        "payload",
        "blocker",
    }
)
BLOCKER_FIELDS = frozenset({"id", "reason", "next_check"})


class RoleEvidenceError(Exception):
    detail: str

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)

    @override
    def __str__(self) -> str:
        return self.detail


def _object(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    match value:
        case dict():
            return value
        case str() | int() | float() | bool() | None | list():
            raise RoleEvidenceError(f"{label} must be an object")
        case unreachable:
            assert_never(unreachable)


def _text(value: JsonValue | None, label: str) -> str:
    match value:
        case str() if value.strip():
            return value
        case str() | int() | float() | bool() | None | list() | dict():
            raise RoleEvidenceError(f"{label} must be non-empty text")
        case unreachable:
            assert_never(unreachable)


def _envelope(
    value: JsonValue | None,
    context: KnowledgeContext,
) -> tuple[dict[str, JsonValue], str, JsonValue]:
    envelope = _object(value, "role_evidence")
    if frozenset(envelope) != ENVELOPE_FIELDS:
        raise RoleEvidenceError("role_evidence has an unsupported envelope shape")
    task_type = _text(envelope.get("task_type"), "role_evidence.task_type")
    task_pack_id = _text(
        envelope.get("task_pack_id"),
        "role_evidence.task_pack_id",
    )
    if (task_type, task_pack_id) != (context.task_type, context.task_pack_id):
        raise RoleEvidenceError(
            "role_evidence task binding differs from validated knowledge context"
        )
    binding = _object(
        envelope.get("context_binding"),
        "role_evidence.context_binding",
    )
    disposition = _text(
        envelope.get("disposition"),
        "role_evidence.disposition",
    )
    if disposition == "completed":
        if envelope.get("blocker") is not None:
            raise RoleEvidenceError(
                "completed role_evidence cannot carry a blocker"
            )
    elif disposition == "blocked":
        blocker = _object(
            envelope.get("blocker"),
            "role_evidence.blocker",
        )
        if frozenset(blocker) != BLOCKER_FIELDS:
            raise RoleEvidenceError(
                "role_evidence.blocker has an unsupported shape"
            )
        for field in BLOCKER_FIELDS:
            _text(blocker.get(field), f"role_evidence.blocker.{field}")
        if envelope.get("payload") is not None:
            raise RoleEvidenceError(
                "blocked role_evidence cannot carry completed payload"
            )
    else:
        raise RoleEvidenceError(
            "role_evidence disposition must be completed or blocked"
        )
    return binding, disposition, envelope.get("payload")


def _validate_marketing(
    payload: JsonValue,
    context: KnowledgeContext,
) -> None:
    from agent_company_marketing_decision_runtime import (
        MarketingDecisionRuntimeError,
        validate_marketing_decision_for_task,
    )

    try:
        validate_marketing_decision_for_task(
            payload,
            task_type=context.task_type,
            task_pack_id=context.task_pack_id,
        )
    except MarketingDecisionRuntimeError as exc:
        raise RoleEvidenceError(
            f"marketing role_evidence is invalid: {exc}"
        ) from exc


def validate_role_evidence(
    *,
    role: str,
    context: KnowledgeContext,
    value: JsonValue | None,
    expected_context_binding: JsonValue | None = None,
    receipt_ingress: bool = False,
) -> str:
    if role not in INTEGRATED_ROLES:
        if value is not None:
            raise RoleEvidenceError(f"role_evidence is unsupported for {role}")
        return "completed"
    binding, disposition, payload = _envelope(value, context)
    if expected_context_binding is not None and binding != expected_context_binding:
        raise RoleEvidenceError(
            "role_evidence context differs from the parent assignment"
        )
    if disposition == "blocked":
        return disposition
    if role == "design" and receipt_ingress and expected_context_binding is None:
        raise RoleEvidenceError(
            "Design role_evidence requires a parent-issued context binding"
        )
    try:
        if role == "founder":
            validate_founder_task_evidence(
                payload,
                task_type=context.task_type,
                task_pack_id=context.task_pack_id,
            )
        elif role == "planning":
            validate_planning_invariants(
                payload,
                task_type=context.task_type,
                task_pack_id=context.task_pack_id,
            )
        elif role == "marketing":
            _validate_marketing(payload, context)
        elif role == "design":
            validate_design_role_evidence(payload, binding)
        elif role == "development":
            validate_development_task_evidence(
                payload,
                task_type=context.task_type,
                task_pack_id=context.task_pack_id,
            )
        else:
            raise RoleEvidenceError(f"unsupported role evidence role: {role}")
    except (
        PlanningInvariantError,
        DesignReviewContractError,
        DevelopmentEvidenceError,
        FounderTaskEvidenceError,
    ) as exc:
        raise RoleEvidenceError(f"{role} role_evidence is invalid: {exc}") from exc
    return disposition


def blocked_role_evidence(
    context: KnowledgeContext,
    context_binding: JsonValue | None = None,
) -> dict[str, JsonValue]:
    return {
        "task_type": context.task_type,
        "task_pack_id": context.task_pack_id,
        "context_binding": _object(context_binding or {}, "context_binding"),
        "disposition": "blocked",
        "payload": None,
        "blocker": {
            "id": "role-evidence-pending",
            "reason": "No task-specific role evidence was supplied.",
            "next_check": "Supply candidate-bound evidence for the selected task.",
        },
    }


def completed_role_evidence(
    context: KnowledgeContext,
    payload: JsonValue,
    context_binding: JsonValue | None = None,
) -> dict[str, JsonValue]:
    return {
        "task_type": context.task_type,
        "task_pack_id": context.task_pack_id,
        "context_binding": _object(context_binding or {}, "context_binding"),
        "disposition": "completed",
        "payload": payload,
        "blocker": None,
    }


__all__ = [
    "RoleEvidenceError",
    "blocked_role_evidence",
    "completed_role_evidence",
    "validate_role_evidence",
]
