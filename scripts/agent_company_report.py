#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/agent_company_jobs.py report --help
# 3. Or make executable and run:
#      chmod +x scripts/agent_company_jobs.py && ./scripts/agent_company_jobs.py report --help
# ─────────────────

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path
from typing import Final, TypeVar

import agent_company_report_runtime as _core_runtime
import agent_company_report_actions as _actions
import agent_company_report_commercial as _commercial
import agent_company_report_deliveries as _deliveries
import agent_company_report_evidence as _evidence
import agent_company_report_receipts as _receipts
import agent_company_report_render as _render
import agent_company_report_runtime_capture as _runtime_capture
import agent_company_report_status as _status
import agent_company_report_verification as _verification
from agent_company_external_action_validation import (
    validate_external_action_ledger,
)
from agent_company_deps import JsonValue
from agent_company_job_definition import (
    validate_company_context,
)
from agent_company_job_policy import PolicyError, object_list, string_list, text
from agent_company_report_byte_provenance import (
    require_unchanged_runtime_provenance,
)

ROOT: Final[Path] = _render.ROOT
REPORT_TEMPLATE_PATH: Final[Path] = _render.REPORT_TEMPLATE_PATH
REPORT_STATES: Final = _render.REPORT_STATES
TEMPLATE_TOKENS: Final = _render.TEMPLATE_TOKENS
TOKEN_PATTERN: Final = _render.TOKEN_PATTERN
LEDGER_KEYS: Final = _actions.LEDGER_KEYS
ACTION_KEYS: Final = _actions.ACTION_KEYS
APPROVAL_KEYS: Final = _actions.APPROVAL_KEYS
SHA256_PATTERN: Final = _actions.SHA256_PATTERN
EnumValue = TypeVar("EnumValue", bound=StrEnum)
TerminalStatus = _status.TerminalStatus
ExternalStatus = _status.ExternalStatus
ReportRuntimeBindings = _core_runtime.ReportRuntimeBindings
TerminalStatus.__module__ = __name__
ExternalStatus.__module__ = __name__

__all__ = [
    "ACTION_KEYS",
    "APPROVAL_KEYS",
    "LEDGER_KEYS",
    "REPORT_STATES",
    "REPORT_TEMPLATE_PATH",
    "ROOT",
    "SHA256_PATTERN",
    "TEMPLATE_TOKENS",
    "TOKEN_PATTERN",
    "EnumValue",
    "ExternalStatus",
    "Final",
    "Iterable",
    "JsonValue",
    "Path",
    "PolicyError",
    "ReportRuntimeBindings",
    "StrEnum",
    "TerminalStatus",
    "TypeVar",
    "build_ceo_report",
    "hashlib",
    "json",
    "load_ceo_report_template",
    "object_list",
    "re",
    "render_ceo_report_markdown",
    "require_unchanged_runtime_provenance",
    "string_list",
    "text",
    "validate_company_context",
    "validate_external_action_ledger",
]


def _json_array(values: Iterable[JsonValue]) -> list[JsonValue]:
    return list(values)


def load_ceo_report_template() -> str:
    return _render.load_ceo_report_template()


def render_ceo_report_markdown(report: dict[str, JsonValue], template: str) -> str:
    return _render.render_ceo_report_markdown(report, template)


def build_ceo_report(
    delegation_input: dict[str, JsonValue],
    bindings: ReportRuntimeBindings,
) -> dict[str, JsonValue]:
    validated_runtime = _core_runtime.validate_report_runtime(bindings)
    job = bindings.job
    core_run = bindings.core_run
    verification_run = bindings.verification_run
    job_ref = bindings.job_ref
    core_run_ref = bindings.core_run_ref
    external_action_ledger_ref = bindings.external_action_ledger_ref
    external_action_ledger = bindings.external_action_ledger
    # Reporting reads stored evidence; historical owner labels do not route work.
    validate_company_context(job, historical_read=True)
    if job.get("format") != "agent-company.job/v0.1":
        raise PolicyError("job has an unexpected format")
    if delegation_input.get("format") != "agent-company.core-delegation-input/v0.1":
        raise PolicyError("delegation input has an unexpected format")
    if core_run.get("format") != "sejong.delegation-run/v0.1-draft":
        raise PolicyError("Core run has an unexpected format")
    job_id = text(job.get("job_id"), "job_id")
    if text(delegation_input.get("job_id"), "delegation job_id") != job_id:
        raise PolicyError("delegation job_id does not match the job")
    if text(core_run.get("run_id"), "Core run_id") != job_id:
        raise PolicyError("Core run_id does not match the job and delegation")
    selected_roles = string_list(job.get("selected_roles"), "selected_roles")
    delegated_roles = string_list(
        delegation_input.get("selected_roles"),
        "delegation selected_roles",
    )
    if (
        len(selected_roles) != len(set(selected_roles))
        or set(delegated_roles) != set(selected_roles)
    ):
        raise PolicyError("selected roles do not match across job and delegation")
    assignments = object_list(delegation_input.get("assignments"), "assignments")
    assignment_ids = [text(item.get("worker_id"), "worker_id") for item in assignments]
    if len(assignment_ids) != len(set(assignment_ids)):
        raise PolicyError("delegation assignments repeat a worker_id")
    assignment_roles = [text(item.get("role"), "assignment role") for item in assignments]
    ordinary_roles = {role for role in assignment_roles if role != "specialist"}
    if not ordinary_roles.issubset(selected_roles):
        raise PolicyError("assignment role was not selected by the job")
    _receipts.validate_specialist_assignments(assignments)
    assignment_by_worker = {
        text(item.get("worker_id"), "worker_id"): item
        for item in assignments
    }
    terminals = _receipts.terminal_receipts(
        core_run,
        assignment_by_worker,
        job_id,
    )
    runtime_capture = _runtime_capture.capture_report_runtime(
        delegation_input,
        bindings,
    )
    cleanup = _receipts.cleanup_evidence(core_run)
    verification = _verification.verification_evidence(
        verification_run,
        _verification.VerificationBindings(
            job_ref=job_ref,
            core_run_ref=core_run_ref,
            verification_run_ref=bindings.verification_run_ref,
            core_run=core_run,
            terminals=terminals,
            assignments=assignment_by_worker,
            external_action_ledger_ref=external_action_ledger_ref,
            external_action_ledger_sha256=validated_runtime.external_action_ledger_sha256,
            runtime_byte_provenance=(
                runtime_capture.provenance
                if runtime_capture is not None
                else None
            ),
        ),
    )
    states = list(cleanup.states)
    risks = list(cleanup.risks)
    delivery_projection = _deliveries.project_deliveries(
        assignments,
        terminals,
        verification,
        selected_roles,
    )
    deliveries = list(delivery_projection.deliveries)
    claims = list(delivery_projection.claims)
    states.extend(delivery_projection.states)
    risks.extend(delivery_projection.risks)
    verified = verification.authorizes_verified_projection
    actions = _actions.project_external_actions(
        external_action_ledger,
        job_id,
        verified and verification.external_actions_bound,
    )
    states.extend(text(action.get("state"), "external-action state") for action in actions)
    action_ids = {
        text(action.get("action_id"), "external-action id")
        for action in actions
    }
    for assignment_item in assignments:
        requirement = assignment_item.get("external_action_requirement")
        if requirement is None:
            continue
        if requirement != "core_receipt_required":
            raise PolicyError("assignment has an unsupported external_action_requirement")
        action_id = assignment_item.get("external_action_id")
        worker_id = text(assignment_item.get("worker_id"), "worker_id")
        if not isinstance(action_id, str) or not action_id:
            risk = (
                f"Approval-gated assignment {worker_id} has no deterministic "
                "external_action_id."
            )
        elif action_id not in action_ids:
            risk = (
                f"Approval-gated action {action_id} has no matching Core "
                "external-action receipt."
            )
        else:
            continue
        risks.append(risk)
        states.append("unverified")
    company = _commercial.project_company_commercial(job)
    if company.claim is not None and company.risk is not None:
        claims.append(company.claim)
        risks.append(company.risk)
        states.append("unverified")
    overall = _status.overall_state(states)
    user_decisions = _evidence.project_user_decisions(job.get("uigwe_gate"))
    state_counts = {state: states.count(state) for state in sorted(set(states))}
    report = _evidence.require_safe_report({
        "format": "agent-company.ceo-report/v0.1",
        "job_id": job_id,
        "job_type": text(job.get("job_type"), "job_type"),
        "objective": text(job.get("objective"), "objective"),
        "overall_status": overall,
        "decision_summary": (
            f"Evidence-derived delivery and action states: {state_counts}.{company.summary}"
        ),
        "role_deliveries": _json_array(deliveries),
        "external_actions": _json_array(actions),
        "claims": _json_array(claims),
        "user_decisions": _json_array(user_decisions),
        "risks": _json_array(dict.fromkeys(risks)),
        "next_actions": _json_array(()) if overall == "verified" else _json_array(dict.fromkeys([
            "Resolve failed, blocked, executed, or unverified evidence before claiming completion.",
            *(
                ["Collect byte-bound commercial evidence before claiming profitable business value."]
                if company.needs_evidence else []
            ),
        ])),
    })
    if runtime_capture is not None:
        require_unchanged_runtime_provenance(runtime_capture)
    return report
