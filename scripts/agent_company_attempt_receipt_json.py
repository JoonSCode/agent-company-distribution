#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Import from agent_company_telemetry_models.py.
# 2. Pass a validated AttemptReceipt to attempt_receipt_json().
# 3. Test: uv run scripts/test_agent_company_telemetry.py
# ─────────────────

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

from agent_company_attempt_receipt import AttemptReceipt, FORMAT
from agent_company_privacy import JsonObject


def attempt_receipt_json(receipt: AttemptReceipt) -> JsonObject:
    return {
        "format": FORMAT,
        "attempt_id": receipt.attempt_id,
        "routing_mode": receipt.routing_mode,
        "requested_profile": receipt.requested_profile,
        "effective_model": receipt.effective_model,
        "reasoning_effort": receipt.reasoning_effort,
        "service_tier": receipt.service_tier,
        "continuation": {
            "action": receipt.continuation.action,
            "adjacent_work": receipt.continuation.adjacent_work,
            "stable_prefix_reusable": receipt.continuation.stable_prefix_reusable,
            "context_health": receipt.continuation.context_health,
            "model_change_required": receipt.continuation.model_change_required,
            "independent_verification_required": receipt.continuation.independent_verification_required,
            "inherited_context_risk": receipt.continuation.inherited_context_risk,
            "invalidation_reasons": list(receipt.continuation.invalidation_reasons),
            "prior_attempt_id": receipt.continuation.prior_attempt_id,
            "prior_identity_sha256": receipt.continuation.prior_identity_sha256,
        },
        "cache_strategy": receipt.cache_strategy,
        "local_artifact_reuse": {
            "status": receipt.local_artifact_reuse.status,
            "artifact_count": receipt.local_artifact_reuse.artifact_count,
            "artifact_set_sha256": receipt.local_artifact_reuse.artifact_set_sha256,
            "evidence_refs": list(receipt.local_artifact_reuse.evidence_refs),
        },
        "identity": {
            "source_sha256": receipt.identity.source_sha256,
            "decision_sha256": receipt.identity.decision_sha256,
            "capsule_sha256": receipt.identity.capsule_sha256,
            "rules_sha256": receipt.identity.rules_sha256,
            "plugin_set_sha256": receipt.identity.plugin_set_sha256,
            "tool_schema_sha256": receipt.identity.tool_schema_sha256,
            "stable_prefix_sha256": receipt.identity.stable_prefix_sha256,
        },
        "usage": {
            "input_tokens": receipt.usage.input_tokens,
            "cached_input_tokens": receipt.usage.cached_input_tokens,
            "cache_write_input_tokens": receipt.usage.cache_write_input_tokens,
            "output_tokens": receipt.usage.output_tokens,
            "reasoning_tokens": receipt.usage.reasoning_tokens,
        },
        "rework_count": receipt.rework_count,
        "verified_quality_score": receipt.verification.quality_score,
        "critical_verification_regression": receipt.verification.critical_regression,
        "verifier_id": receipt.verification.verifier_id,
        "verified_at": receipt.verification.verified_at,
        "verification_evidence_sha256": receipt.verification.evidence_sha256,
        "verification_evidence_refs": list(receipt.verification.evidence_refs),
    }
