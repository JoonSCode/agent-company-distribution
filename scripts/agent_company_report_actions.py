#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Run through the report hardening suite:
#      uv run scripts/test_agent_company_report_hardening.py
# 2. This module owns external-action ledger validation and report projection.
# ─────────────────

from __future__ import annotations

import hashlib
import json
import re
from typing import Final

from agent_company_deps import JsonValue
from agent_company_job_policy import PolicyError, object_list, string_list, text
from agent_company_report_evidence import project_evidence_refs
from agent_company_report_status import ExternalStatus, enum_value, external_state


LEDGER_KEYS: Final = {"format", "run_id", "updated_at", "receipts"}
ACTION_KEYS: Final = {
    "action_id", "action_name", "target_description", "input_sha256", "action_sha256",
    "idempotency_key", "approval", "status", "dispatched_at", "terminal_at", "evidence_refs",
}
APPROVAL_KEYS: Final = {
    "approval_record_ref", "approval_record_sha256", "run_id", "action_sha256",
    "issuer_authority", "issued_at", "expires_at", "source_user_decision_ref",
}
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


def _exact_keys(value: dict[str, JsonValue], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise PolicyError(f"{label} keys do not match the Core contract")


def project_external_actions(
    ledger: dict[str, JsonValue] | None, run_id: str, verified: bool,
) -> list[dict[str, JsonValue]]:
    if ledger is None:
        return []
    _exact_keys(ledger, LEDGER_KEYS, "external-action ledger")
    if ledger.get("format") != "sejong.external-action-receipts/v0.1-draft":
        raise PolicyError("external-action ledger has an unexpected format")
    if text(ledger.get("run_id"), "external-action run_id") != run_id:
        raise PolicyError("external-action run_id does not match the Core run")
    text(ledger.get("updated_at"), "external-action updated_at")
    projected: list[dict[str, JsonValue]] = []
    seen: set[str] = set()
    for receipt in object_list(ledger.get("receipts"), "external-action receipts"):
        _exact_keys(receipt, ACTION_KEYS, "external-action receipt")
        action_id = text(receipt.get("action_id"), "action_id")
        if action_id in seen:
            raise PolicyError(f"duplicate external-action receipt {action_id}")
        seen.add(action_id)
        action_hash = text(receipt.get("action_sha256"), "action_sha256")
        input_hash = text(receipt.get("input_sha256"), "input_sha256")
        canonical_action = {
            "action_id": action_id,
            "action_name": text(receipt.get("action_name"), "action_name"),
            "idempotency_key": text(receipt.get("idempotency_key"), "idempotency_key"),
            "input_sha256": input_hash,
            "target_description": text(
                receipt.get("target_description"),
                "target_description",
            ),
        }
        computed_action_hash = hashlib.sha256(json.dumps(
            canonical_action,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()).hexdigest()
        approval = receipt.get("approval")
        if not isinstance(approval, dict):
            raise PolicyError("external-action approval must be an object")
        _exact_keys(approval, APPROVAL_KEYS, "external-action approval")
        approved_hash = text(approval.get("action_sha256"), "approval action_sha256")
        record_hash = text(
            approval.get("approval_record_sha256"),
            "approval_record_sha256",
        )
        if (
            not SHA256_PATTERN.fullmatch(action_hash)
            or not SHA256_PATTERN.fullmatch(input_hash)
            or not SHA256_PATTERN.fullmatch(record_hash)
            or approved_hash != action_hash
            or computed_action_hash != action_hash
            or text(approval.get("run_id"), "approval run_id") != run_id
        ):
            raise PolicyError(f"external-action receipt {action_id} has tampered hashes")
        if approval.get("issuer_authority") not in {"host", "user"}:
            raise PolicyError(
                f"external-action receipt {action_id} has invalid approval authority",
            )
        for field in (
            "approval_record_ref", "issued_at", "expires_at", "source_user_decision_ref",
        ):
            text(approval.get(field), field)
        text(receipt.get("idempotency_key"), "idempotency_key")
        status = enum_value(
            ExternalStatus,
            receipt.get("status"),
            "external-action status",
        )
        dispatched_at = receipt.get("dispatched_at")
        terminal_at = receipt.get("terminal_at")
        expected_timestamps = {
            ExternalStatus.AUTHORIZED: (False, False),
            ExternalStatus.DISPATCHED: (True, False),
            ExternalStatus.COMPLETED: (True, True),
            ExternalStatus.FAILED: (True, True),
            ExternalStatus.CANCELLED: (False, True),
        }[status]
        if (isinstance(dispatched_at, str), isinstance(terminal_at, str)) != expected_timestamps:
            raise PolicyError(f"external-action receipt {action_id} has invalid timestamps")
        evidence_refs = string_list(
            receipt.get("evidence_refs"),
            "external-action evidence_refs",
        )
        if len(evidence_refs) != len(set(evidence_refs)):
            raise PolicyError(f"external-action receipt {action_id} repeats evidence")
        evidence_refs = project_evidence_refs(
            evidence_refs, "external-action evidence",
        )
        projected.append({
            "action_id": action_id,
            "action_name": canonical_action["action_name"],
            "target": canonical_action["target_description"],
            "state": external_state(status, verified),
            "evidence_refs": evidence_refs,
        })
    return projected
