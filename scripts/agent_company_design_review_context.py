from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, TypeIs

from agent_company_design_review_common import (
    DesignReviewContractError,
    exact,
    record,
    records,
    text,
)
from agent_company_role_schema import JsonValue

type DesignTaskType = Literal[
    "flow-interaction",
    "visual-system-accessibility",
    "implementation-design-qa",
]
TASK_PACKS: Final[dict[DesignTaskType, str]] = {
    "flow-interaction": "task-pack:design:flow-interaction",
    "visual-system-accessibility": "task-pack:design:visual-system-accessibility",
    "implementation-design-qa": "task-pack:design:implementation-design-qa",
}
CONTEXT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "task_type",
        "task_pack_id",
        "implementation_owner_id",
        "implementation_owner_role",
        "verification_owners",
        "task_started_at",
        "evidence_deadline_at",
    }
)
VERIFIER_FIELDS: Final[frozenset[str]] = frozenset(
    {"verification_owner_id", "verification_owner_role"}
)
VERIFICATION_ROLES: Final[frozenset[str]] = frozenset(
    {"qa-release", "seungjeongwon"}
)


@dataclass(frozen=True, slots=True)
class TrustedOwner:
    owner_id: str
    role: str


@dataclass(frozen=True, slots=True)
class TrustedReviewContext:
    task_type: DesignTaskType
    task_pack_id: str
    implementation_owner: TrustedOwner
    verification_owners: tuple[TrustedOwner, ...]
    task_started_at: datetime
    evidence_deadline_at: datetime


def _timestamp(value: JsonValue | None, field: str) -> datetime:
    raw = text(value)
    if raw is None:
        raise DesignReviewContractError("trusted_context_invalid", f"{field} is required")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DesignReviewContractError(
            "trusted_context_invalid",
            f"{field} must be an ISO-8601 timestamp",
        ) from exc
    if parsed.tzinfo is None:
        raise DesignReviewContractError(
            "trusted_context_invalid",
            f"{field} must include a timezone",
        )
    return parsed


def _is_task_type(value: str | None) -> TypeIs[DesignTaskType]:
    return value in TASK_PACKS


def parse_trusted_review_context(value: JsonValue) -> TrustedReviewContext:
    context = record(value, "trusted_context")
    exact(context, CONTEXT_FIELDS, "trusted_context")
    task_type = text(context.get("task_type"))
    task_pack_id = text(context.get("task_pack_id"))
    if not _is_task_type(task_type):
        raise DesignReviewContractError(
            "review_task_type_unsupported",
            "Design evidence requires an exact registered task pair",
        )
    if task_pack_id is None or task_pack_id != TASK_PACKS[task_type]:
        raise DesignReviewContractError(
            "review_task_type_unsupported",
            "Design evidence requires an exact registered task pair",
        )
    implementation_owner_id = text(context.get("implementation_owner_id"))
    implementation_owner_role = text(context.get("implementation_owner_role"))
    if implementation_owner_id is None or implementation_owner_role != "development":
        raise DesignReviewContractError(
            "implementation_owner_mismatch",
            "trusted implementation owner must bind the Development role",
        )
    owners: list[TrustedOwner] = []
    for index, raw_owner in enumerate(
        records(context.get("verification_owners"), "verification_owners")
    ):
        exact(raw_owner, VERIFIER_FIELDS, f"verification_owners[{index}]")
        owner_id = text(raw_owner.get("verification_owner_id"))
        role = text(raw_owner.get("verification_owner_role"))
        if (
            owner_id is None
            or role not in VERIFICATION_ROLES
            or role == implementation_owner_role
            or owner_id == implementation_owner_id
        ):
            raise DesignReviewContractError(
                "verification_owner_not_independent",
                f"verification_owners[{index}] is not independently owned",
            )
        owners.append(TrustedOwner(owner_id, role))
    if not owners or len({owner.owner_id for owner in owners}) != len(owners):
        raise DesignReviewContractError(
            "trusted_context_invalid",
            "verification owner identities must be nonempty and unique",
        )
    started_at = _timestamp(context.get("task_started_at"), "task_started_at")
    deadline_at = _timestamp(
        context.get("evidence_deadline_at"),
        "evidence_deadline_at",
    )
    if started_at > deadline_at:
        raise DesignReviewContractError(
            "trusted_context_invalid",
            "task_started_at must not follow evidence_deadline_at",
        )
    return TrustedReviewContext(
        task_type,
        task_pack_id,
        TrustedOwner(implementation_owner_id, implementation_owner_role),
        tuple(owners),
        started_at,
        deadline_at,
    )
