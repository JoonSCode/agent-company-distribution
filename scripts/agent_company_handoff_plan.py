from __future__ import annotations

import hashlib
from pathlib import Path

from agent_company_deps import JsonValue

ROOT = Path(__file__).resolve().parents[1]


class HandoffPlanError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)

    def __str__(self) -> str:
        return self.detail


def _object(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise HandoffPlanError(f"{label} must be an object")
    return value


def _text(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HandoffPlanError(f"{label} must be a non-empty string")
    return value


def _strings(value: JsonValue | None, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HandoffPlanError(f"{label} must be an array of strings")
    return [item for item in value if isinstance(item, str)]


def _local_path(value: JsonValue | None, label: str) -> tuple[str, Path]:
    reference = _text(value, label)
    if "://" in reference:
        raise HandoffPlanError(f"{label} must reference a local file")
    path = Path(reference).expanduser()
    return reference, (path if path.is_absolute() else ROOT / path).resolve()


def validate_plan_assignment(
    assignment: dict[str, JsonValue],
    payload: dict[str, JsonValue],
    scope: dict[str, JsonValue],
) -> bool:
    raw_role_plan = assignment.get("role_plan_binding")
    raw_receipt = assignment.get("execution_receipt_binding")
    if raw_role_plan is None and raw_receipt is None:
        return False
    if raw_role_plan is None or raw_receipt is None:
        raise HandoffPlanError("plan-backed assignment bindings are incomplete")
    role_plan = _object(raw_role_plan, "assignment role_plan_binding")
    receipt = _object(raw_receipt, "assignment execution_receipt_binding")
    role_plan_id = _text(role_plan.get("role_plan_id"), "role_plan_id")
    role_plan_ref, role_plan_path = _local_path(role_plan.get("ref"), "role plan ref")
    role_plan_sha256 = _text(role_plan.get("sha256"), "role plan sha256")
    if (
        role_plan_ref != str(role_plan_path)
        or role_plan_path.is_symlink()
        or not role_plan_path.is_file()
    ):
        raise HandoffPlanError("role plan ref must be a canonical local file")
    try:
        actual_sha256 = hashlib.sha256(role_plan_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise HandoffPlanError("cannot read role plan ref") from exc
    if actual_sha256 != role_plan_sha256:
        raise HandoffPlanError("role plan bytes differ from assignment binding")
    expected_binding: dict[str, JsonValue] = {
        "worker_id": _text(assignment.get("worker_id"), "assignment worker_id"),
        "assignment_id": _text(assignment.get("assignment_id"), "assignment_id"),
        "leaf_id": _text(assignment.get("leaf_id"), "assignment leaf_id"),
        "role_plan_id": role_plan_id,
        "role_plan_ref": role_plan_ref,
        "role_plan_sha256": role_plan_sha256,
        "receipt_id": _text(receipt.get("receipt_id"), "receipt_id"),
    }
    handoff_binding = _object(
        payload.get("assignment_binding"),
        "worker handoff assignment_binding",
    )
    if handoff_binding != expected_binding:
        raise HandoffPlanError("worker handoff does not bind the exact assignment")
    objective = _text(assignment.get("objective"), "assignment objective")
    if payload.get("objective") != objective:
        raise HandoffPlanError("worker handoff objective differs from assignment")
    read_scope = _strings(assignment.get("read_scope"), "assignment read_scope")
    write_scope = _strings(assignment.get("write_scope"), "assignment write_scope")
    allowed_paths = list(dict.fromkeys([*read_scope, *write_scope]))
    expected_scope: dict[str, JsonValue] = {
        "allowed_paths": list(allowed_paths),
        "read_refs": list(read_scope),
        "write_refs": list(write_scope),
        "stop_condition": _text(
            assignment.get("stop_condition"),
            "assignment stop_condition",
        ),
    }
    if scope != expected_scope:
        raise HandoffPlanError("worker handoff scope differs from assignment")
    return True
