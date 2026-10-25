"""Validate Company-consumed historical action evidence without an executor.

Historical schema labels are data. This module neither grants execution
authority nor fetches/loads a former Core installation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent_company_deps import JsonValue
from agent_company_job_policy import PolicyError, object_list, text
from agent_company_report_actions import project_external_actions


def timestamp(value: JsonValue, label: str) -> datetime:
    try:
        result = datetime.fromisoformat(text(value, label).replace("Z", "+00:00"))
    except ValueError as exc:
        raise PolicyError(f"{label} must be an ISO timestamp") from exc
    if result.tzinfo is None:
        raise PolicyError(f"{label} must include a timezone")
    return result.astimezone(timezone.utc)


def validate_external_action_ledger(ledger: dict[str, JsonValue]) -> None:
    run_id = text(ledger.get("run_id"), "external-action run_id")
    # Reuse the exact Company action/approval keys, hash, issuer and state checks.
    project_external_actions(ledger, run_id, False)
    updated = timestamp(ledger.get("updated_at"), "external-action updated_at")
    keys: set[str] = set()
    for receipt in object_list(ledger.get("receipts"), "external-action receipts"):
        key = text(receipt.get("idempotency_key"), "external-action idempotency key")
        if key in keys:
            raise PolicyError("external-action ledger has a duplicate idempotency key")
        keys.add(key)
        approval = receipt["approval"]
        assert isinstance(approval, dict)  # validated by project_external_actions
        issued = timestamp(approval.get("issued_at"), "external-action approval issued_at")
        expires = timestamp(approval.get("expires_at"), "external-action approval expires_at")
        if expires <= issued:
            raise PolicyError("external-action approval expires before issuance")
        if expires - issued > timedelta(hours=1):
            raise PolicyError("external-action approval window exceeds one hour")
        dispatched = receipt.get("dispatched_at")
        terminal = receipt.get("terminal_at")
        start = timestamp(dispatched, "external-action dispatched_at") if dispatched is not None else None
        end = timestamp(terminal, "external-action terminal_at") if terminal is not None else None
        if start is not None and not issued <= start <= expires:
            raise PolicyError("external-action dispatch falls outside its approval")
        if end is not None and (end < (start or issued) or end > updated):
            raise PolicyError("external-action terminal timestamps are inconsistent")
