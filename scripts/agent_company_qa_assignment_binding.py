from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, override

from agent_company_deps import JsonValue

__all__ = [
    "QaAssignmentBindingError",
    "validate_qa_assignment_binding",
]

REQUIRED_PLAN_FIELDS: Final[tuple[str, ...]] = (
    "format",
    "candidate",
    "criteria",
    "risk_boundary_matrix",
)
OPTIONAL_PLAN_FIELDS: Final[tuple[str, ...]] = (
    "target",
    "evidence_window",
)


@dataclass(frozen=True, slots=True)
class QaAssignmentBindingError(Exception):
    field: str
    detail: str

    @override
    def __str__(self) -> str:
        return f"{self.field}: {self.detail}"


def _object(
    value: JsonValue | None,
    field: str,
) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return value
    raise QaAssignmentBindingError(field, "must be an object")


def _require_exact_field(
    parent: dict[str, JsonValue],
    worker: dict[str, JsonValue],
    field: str,
) -> None:
    if field not in parent:
        raise QaAssignmentBindingError(
            f"parent assignment.qa_verification.{field}",
            "is required",
        )
    if worker.get(field) != parent[field]:
        raise QaAssignmentBindingError(
            f"worker qa_verification.{field}",
            f"differs from parent assignment {field}",
        )


def validate_qa_assignment_binding(
    assignment: Mapping[str, JsonValue],
    worker_qa_verification: JsonValue | None,
) -> None:
    """Validate immutable QA plan fields against the parent assignment."""
    if assignment.get("role") != "qa-release":
        raise QaAssignmentBindingError(
            "parent assignment.role",
            "must be qa-release",
        )
    parent = _object(
        assignment.get("qa_verification"),
        "parent assignment.qa_verification",
    )
    worker = _object(
        worker_qa_verification,
        "worker qa_verification",
    )
    for field in REQUIRED_PLAN_FIELDS:
        _require_exact_field(parent, worker, field)
    for field in OPTIONAL_PLAN_FIELDS:
        if field in parent or field in worker:
            _require_exact_field(parent, worker, field)
