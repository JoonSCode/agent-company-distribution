#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Run the focused delegation tests:
#      uv run scripts/test_agent_company_plan_delegation.py
# ─────────────────

"""Project compact, hash-bound worker contracts from validated plan fields."""

from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import hashlib
import json
import re
from typing import Final

from agent_company_deps import JsonValue
from agent_company_model_routing import (
    CANONICAL_ALGORITHM,
    DECISION_FORMAT,
    FallbackAttempt,
    ModelRoutingDecision,
    RoutingDisposition,
)
from agent_company_plan_delegation_binding import PlanAssignment
from agent_company_projection_validation import PolicyError

JsonObject = dict[str, JsonValue]
SHA256: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}\Z")
WORKER_PACKET_CANONICAL_ALGORITHM: Final[str] = "sha256-canonical-json/v1"


def _require_text(value: str | None, field: str) -> str:
    if type(value) is not str or not value:
        raise PolicyError(f"routed model decision requires {field}")
    return value


def _require_digest(value: str, field: str) -> str:
    text = _require_text(value, field)
    if SHA256.fullmatch(text) is None:
        raise PolicyError(f"routed model decision has invalid {field}")
    return text


def _decision_identity(decision: ModelRoutingDecision) -> str:
    payload = {
        "format": decision.format,
        "algorithm": decision.canonical_algorithm,
        "disposition": decision.disposition.value,
        "requested": decision.requested_profile,
        "selected": decision.selected_profile,
        "model": decision.effective_model_id,
        "effort": decision.effective_reasoning_effort,
        "adapter": decision.effective_adapter,
        "predicate": decision.predicate_id,
        "reason": decision.selection_reason,
        "attempts": tuple(
            {
                "profile": attempt.semantic_profile,
                "cause": attempt.cause.value,
            }
            for attempt in decision.fallback_attempts
        ),
        "request_format": decision.request_format,
        "capacity_format": decision.capacity_format,
        "request_digest": decision.request_digest,
        "registry_digest": decision.registry_digest,
        "registry_projection_digest": decision.registry_projection_digest,
        "policy_digest": decision.policy_digest,
        "policy_projection_digest": decision.policy_projection_digest,
        "rate_card_digest": decision.rate_card_digest,
        "capacity_digest": decision.capacity_digest,
        "validation_errors": decision.validation_errors,
    }
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(),
    ).hexdigest()


def _validated_dispatch_decision(decision: ModelRoutingDecision) -> None:
    if type(decision) is not ModelRoutingDecision:
        raise PolicyError("model routing decision must be a ModelRoutingDecision")
    if decision.format != DECISION_FORMAT:
        raise PolicyError("routed model decision format is unsupported")
    if decision.canonical_algorithm != CANONICAL_ALGORITHM:
        raise PolicyError("routed model decision canonical algorithm is unsupported")
    if decision.disposition is not RoutingDisposition.DISPATCH:
        raise PolicyError("routed model decision must dispatch to a bounded worker")
    for field, value in (
        ("decision_id", decision.decision_id),
        ("request_digest", decision.request_digest),
        ("registry_digest", decision.registry_digest),
        ("registry_projection_digest", decision.registry_projection_digest),
        ("policy_digest", decision.policy_digest),
        ("policy_projection_digest", decision.policy_projection_digest),
        ("rate_card_digest", decision.rate_card_digest),
        ("capacity_digest", decision.capacity_digest),
    ):
        _ = _require_digest(value, field)
    for field, value in (
        ("requested_profile", decision.requested_profile),
        ("selected_profile", decision.selected_profile),
        ("effective_model", decision.effective_model_id),
        ("reasoning_effort", decision.effective_reasoning_effort),
        ("adapter", decision.effective_adapter),
        ("predicate_id", decision.predicate_id),
        ("selection_reason", decision.selection_reason),
    ):
        _ = _require_text(value, field)
    if decision.validation_errors:
        raise PolicyError("routed model decision has validation errors")
    if not decision.fallback_attempts or any(
        type(attempt) is not FallbackAttempt
        or not attempt.semantic_profile
        or not attempt.cause.value
        for attempt in decision.fallback_attempts
    ):
        raise PolicyError("routed model decision requires ordered fallback attempts")
    if decision.decision_id != _decision_identity(decision):
        raise PolicyError("routed model decision identity does not bind its projection")


def model_routing_binding(decision: ModelRoutingDecision) -> JsonObject:
    """Return the complete, non-authoritative routing projection for one worker."""
    _validated_dispatch_decision(decision)
    return {
        "format": decision.format,
        "decision_id": decision.decision_id,
        "disposition": decision.disposition.value,
        "request_digest": decision.request_digest,
        "registry_digest": decision.registry_digest,
        "registry_projection_digest": decision.registry_projection_digest,
        "policy_digest": decision.policy_digest,
        "policy_projection_digest": decision.policy_projection_digest,
        "rate_card_digest": decision.rate_card_digest,
        "capacity_digest": decision.capacity_digest,
        "requested_profile": _require_text(
            decision.requested_profile,
            "requested_profile",
        ),
        "selected_profile": _require_text(
            decision.selected_profile,
            "selected_profile",
        ),
        "effective_model": _require_text(
            decision.effective_model_id,
            "effective_model",
        ),
        "reasoning_effort": _require_text(
            decision.effective_reasoning_effort,
            "reasoning_effort",
        ),
        "adapter": _require_text(decision.effective_adapter, "adapter"),
        "predicate_id": decision.predicate_id,
        "selection_reason": decision.selection_reason,
        "fallback_attempts": [
            {
                "semantic_profile": attempt.semantic_profile,
                "cause": attempt.cause.value,
            }
            for attempt in decision.fallback_attempts
        ],
    }


def project_execution_contract(
    assignment: PlanAssignment,
    decision: ModelRoutingDecision,
) -> JsonObject:
    """Return only the approved worker-packet aliases for one routed assignment."""
    _validated_dispatch_decision(decision)
    if assignment.acceptance_criteria is None or not assignment.acceptance_criteria:
        raise PolicyError(
            f"routed assignment requires acceptance_criteria: {assignment.assignment_id}",
        )
    return {
        "exact_goal": assignment.objective,
        "owned_files_and_scope": {
            "read_scope": list(assignment.read_scope),
            "write_scope": list(assignment.write_scope),
        },
        "forbidden_scope": list(assignment.forbidden_mutations),
        "required_references_and_evidence": list(assignment.inputs),
        "acceptance_criteria": list(assignment.acceptance_criteria),
        "tests": list(assignment.role_local_qa),
        "expected_outputs": list(assignment.outputs),
        "stop_and_escalation_conditions": list(assignment.escalation_triggers),
    }


def worker_packet_sha256(assignment: JsonObject) -> str:
    """Hash final worker bytes, excluding only the self-referential digest field."""
    canonical_payload = {
        key: value
        for key, value in assignment.items()
        if key != "worker_packet_sha256"
    }
    canonical = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
