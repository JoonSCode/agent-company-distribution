#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Run through the report hardening suite:
#      uv run scripts/test_agent_company_report_hardening.py
# ─────────────────

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from agent_company_deps import JsonValue
from agent_company_job_policy import PolicyError, object_list, text
from agent_company_report_status import (
    CleanupStatus,
    TerminalStatus,
    cleanup_state,
    enum_value,
)


@dataclass(frozen=True, slots=True)
class CleanupEvidence:
    states: tuple[str, ...]
    risks: tuple[str, ...]


def validate_specialist_assignments(
    assignments: list[dict[str, JsonValue]],
) -> None:
    for item in assignments:
        if item.get("role") == "specialist" and (
            not isinstance(item.get("request_id"), str)
            or item.get("decision_owner") != "sejong-lead"
        ):
            raise PolicyError(
                "specialist assignment lacks a bound request and Sejong decision owner",
            )


def _canonical_ref(value: str) -> str:
    return value if "://" in value else str(Path(value).expanduser().resolve())


def terminal_receipts(
    core_run: dict[str, JsonValue],
    expected_assignments: dict[str, dict[str, JsonValue]],
    run_id: str,
) -> dict[str, dict[str, JsonValue]]:
    result: dict[str, dict[str, JsonValue]] = {}
    for receipt in object_list(core_run.get("receipts"), "core receipts"):
        if receipt.get("receipt_type") != "worker_terminal":
            continue
        worker_id = text(receipt.get("worker_id"), "terminal worker_id")
        assignment = expected_assignments.get(worker_id)
        if assignment is None:
            raise PolicyError(f"terminal receipt names unknown worker {worker_id}")
        if worker_id in result:
            raise PolicyError(f"duplicate terminal receipt for worker {worker_id}")
        if text(receipt.get("run_id"), "terminal run_id") != run_id:
            raise PolicyError(f"terminal receipt run_id does not match {run_id}")
        status = enum_value(TerminalStatus, receipt.get("terminal_status"), "terminal_status")
        text(receipt.get("receipt_id"), "terminal receipt_id")
        backend = text(receipt.get("backend"), "terminal backend")
        worker_ref = text(receipt.get("backend_worker_ref"), "backend_worker_ref")
        if backend == "native" and not worker_ref.startswith("codex-thread://"):
            raise PolicyError("native terminal receipt lacks a Codex thread identity")
        if status is TerminalStatus.COMPLETED and receipt.get("blocker") is not None:
            raise PolicyError("completed terminal receipt cannot carry a blocker")
        _validate_plan_receipt(assignment, receipt)
        result[worker_id] = receipt
    return result


def cleanup_evidence(core_run: dict[str, JsonValue]) -> CleanupEvidence:
    states: list[str] = []
    risks: list[str] = []
    for receipt in object_list(core_run.get("receipts"), "core receipts"):
        if receipt.get("receipt_type") != "worker_cleanup":
            continue
        status = enum_value(
            CleanupStatus,
            receipt.get("cleanup_status"),
            "cleanup_status",
        )
        state = cleanup_state(status)
        if state is None:
            continue
        worker_id = text(receipt.get("worker_id"), "cleanup worker_id")
        blocker = text(receipt.get("blocker"), "cleanup blocker")
        states.append(state)
        risks.append(f"Worker {worker_id} cleanup {status.value}: {blocker}")
    return CleanupEvidence(tuple(states), tuple(risks))


def _validate_plan_receipt(
    assignment: dict[str, JsonValue],
    receipt: dict[str, JsonValue],
) -> None:
    raw_role_plan = assignment.get("role_plan_binding")
    raw_expected_receipt = assignment.get("execution_receipt_binding")
    if raw_role_plan is None and raw_expected_receipt is None:
        return
    if not isinstance(raw_role_plan, dict) or not isinstance(raw_expected_receipt, dict):
        raise PolicyError("plan-backed assignment bindings are incomplete")
    role_plan_ref = _canonical_ref(
        text(raw_role_plan.get("ref"), "role plan ref"),
    )
    expected_sha256 = text(raw_role_plan.get("sha256"), "role plan sha256")
    role_plan_path = Path(role_plan_ref)
    if (
        "://" in role_plan_ref
        or role_plan_path.is_symlink()
        or not role_plan_path.is_file()
    ):
        raise PolicyError("role plan ref is not a canonical local file")
    try:
        actual_sha256 = hashlib.sha256(role_plan_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise PolicyError("cannot read role plan ref") from exc
    if actual_sha256 != expected_sha256:
        raise PolicyError("role plan bytes differ from assignment binding")
    expected_receipt_id = text(
        raw_expected_receipt.get("receipt_id"),
        "expected receipt identity",
    )
    if (
        text(receipt.get("receipt_id"), "terminal receipt_id") != expected_receipt_id
        or _canonical_ref(
            text(receipt.get("worker_contract_ref"), "worker_contract_ref"),
        ) != role_plan_ref
    ):
        raise PolicyError("terminal receipt identity does not bind its role plan")
