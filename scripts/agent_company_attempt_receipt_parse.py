#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Import through agent_company_telemetry_models.py.
# 2. Test: uv run scripts/test_agent_company_attempt_receipt.py
# ─────────────────

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

from agent_company_attempt_receipt import (
    CACHE_STRATEGIES,
    CONTEXT_HEALTH,
    CONTINUATION_FIELDS,
    FIELDS,
    FORMAT,
    IDENTITY_FIELDS,
    INVALIDATION_REASONS,
    LOCAL_ARTIFACT_FIELDS,
    PROFILES,
    REASONING_EFFORTS,
    SERVICE_TIERS,
    USAGE_FIELDS,
    AttemptIdentity,
    AttemptReceipt,
    ContinuationDecision,
    LocalArtifactReuse,
    TokenUsage,
    VerificationObservation,
)
from agent_company_attempt_receipt_values import (
    ID,
    SHA256,
    AttemptReceiptError,
    boolean_value,
    choice_value,
    count_value,
    evidence_refs_value,
    exact_fields,
    nullable_boolean_value,
    nullable_count_value,
    nullable_text_value,
    object_value,
    score_value,
    strings_value,
    text_value,
)
from agent_company_privacy import JsonObject, JsonValue, PrivacyError, parse_rfc3339


def _continuation(value: JsonValue) -> ContinuationDecision:
    values = object_value(value, "continuation")
    exact_fields(values, CONTINUATION_FIELDS, "continuation")
    invalidations = strings_value(values, "invalidation_reasons", INVALIDATION_REASONS)
    action = choice_value(values, "action", frozenset({"resume", "start_new"}))
    prior_attempt_id = nullable_text_value(values, "prior_attempt_id", ID)
    prior_identity_sha256 = nullable_text_value(values, "prior_identity_sha256", SHA256)
    if (prior_attempt_id is None) != (prior_identity_sha256 is None):
        raise AttemptReceiptError(
            "malformed_input",
            "prior attempt id and identity digest must appear together",
        )
    decision = ContinuationDecision(
        action,
        boolean_value(values, "adjacent_work"),
        boolean_value(values, "stable_prefix_reusable"),
        choice_value(values, "context_health", CONTEXT_HEALTH),
        boolean_value(values, "model_change_required"),
        boolean_value(values, "independent_verification_required"),
        boolean_value(values, "inherited_context_risk"),
        invalidations,
        prior_attempt_id,
        prior_identity_sha256,
    )
    reusable = (
        decision.adjacent_work
        and decision.stable_prefix_reusable
        and decision.context_health == "healthy"
        and not decision.model_change_required
        and not decision.independent_verification_required
        and not decision.inherited_context_risk
        and not decision.invalidation_reasons
        and decision.prior_attempt_id is not None
        and decision.prior_identity_sha256 is not None
    )
    expected = "resume" if reusable else "start_new"
    if decision.action != expected:
        raise AttemptReceiptError(
            "malformed_input",
            f"continuation action must be {expected}",
        )
    return decision


def _local_artifact_reuse(value: JsonValue) -> LocalArtifactReuse:
    values = object_value(value, "local_artifact_reuse")
    exact_fields(values, LOCAL_ARTIFACT_FIELDS, "local_artifact_reuse")
    reuse = LocalArtifactReuse(
        choice_value(values, "status", frozenset({"none", "observed"})),
        count_value(values, "artifact_count"),
        nullable_text_value(values, "artifact_set_sha256", SHA256),
        evidence_refs_value(values, "evidence_refs", allow_empty=True),
    )
    observed = (
        reuse.artifact_count > 0
        and reuse.artifact_set_sha256 is not None
        and bool(reuse.evidence_refs)
    )
    if (reuse.status == "observed") != observed:
        raise AttemptReceiptError(
            "malformed_input",
            "local artifact status contradicts its observed evidence",
        )
    return reuse


def _identity(value: JsonValue) -> AttemptIdentity:
    values = object_value(value, "identity")
    exact_fields(values, IDENTITY_FIELDS, "identity")
    return AttemptIdentity(*(text_value(values, field, SHA256) for field in (
        "source_sha256", "decision_sha256", "capsule_sha256", "rules_sha256",
        "plugin_set_sha256", "tool_schema_sha256", "stable_prefix_sha256",
    )))


def _usage(value: JsonValue) -> TokenUsage:
    values = object_value(value, "usage")
    exact_fields(values, USAGE_FIELDS, "usage")
    usage = TokenUsage(
        count_value(values, "input_tokens"),
        nullable_count_value(values, "cached_input_tokens"),
        nullable_count_value(values, "cache_write_input_tokens"),
        count_value(values, "output_tokens"),
        count_value(values, "reasoning_tokens"),
    )
    if (
        usage.cached_input_tokens is not None
        and usage.cached_input_tokens > usage.input_tokens
    ):
        raise AttemptReceiptError(
            "malformed_input",
            "cached_input_tokens cannot exceed input_tokens",
        )
    if (
        usage.cache_write_input_tokens is not None
        and usage.cache_write_input_tokens > usage.input_tokens
    ):
        raise AttemptReceiptError(
            "malformed_input",
            "cache_write_input_tokens cannot exceed input_tokens",
        )
    if usage.reasoning_tokens > usage.output_tokens:
        raise AttemptReceiptError(
            "malformed_input",
            "reasoning_tokens cannot exceed output_tokens",
        )
    return usage


def _verification(values: JsonObject) -> VerificationObservation:
    quality_score = score_value(values, "verified_quality_score")
    critical_regression = nullable_boolean_value(
        values,
        "critical_verification_regression",
    )
    verifier_id = nullable_text_value(values, "verifier_id", ID)
    verified_at_value = values.get("verified_at")
    if verified_at_value is not None and not isinstance(verified_at_value, str):
        raise AttemptReceiptError("malformed_input", "verified_at is invalid")
    verified_at = verified_at_value if isinstance(verified_at_value, str) else None
    if verified_at is not None:
        try:
            _ = parse_rfc3339(verified_at, "verified_at")
        except PrivacyError as exc:
            raise AttemptReceiptError(exc.code, exc.detail) from exc
    evidence_sha256 = nullable_text_value(
        values,
        "verification_evidence_sha256",
        SHA256,
    )
    evidence_refs = evidence_refs_value(
        values,
        "verification_evidence_refs",
        allow_empty=True,
    )
    observed = all(
        item is not None
        for item in (
            quality_score,
            critical_regression,
            verifier_id,
            verified_at,
            evidence_sha256,
        )
    ) and bool(evidence_refs)
    unavailable = all(
        item is None
        for item in (
            quality_score,
            critical_regression,
            verifier_id,
            verified_at,
            evidence_sha256,
        )
    ) and not evidence_refs
    if not observed and not unavailable:
        raise AttemptReceiptError(
            "malformed_input",
            "verification observation is incomplete",
        )
    return VerificationObservation(
        quality_score,
        critical_regression,
        verifier_id,
        verified_at,
        evidence_sha256,
        evidence_refs,
    )


def parse_attempt_receipt(value: JsonValue) -> AttemptReceipt:
    values = object_value(value, "attempt_receipt")
    exact_fields(values, FIELDS, "attempt_receipt")
    if values.get("format") != FORMAT or values.get("routing_mode") != "shadow":
        raise AttemptReceiptError(
            "malformed_input",
            "attempt receipt format or routing mode is invalid",
        )
    return AttemptReceipt(
        text_value(values, "attempt_id", ID),
        "shadow",
        choice_value(values, "requested_profile", PROFILES),
        text_value(values, "effective_model"),
        choice_value(values, "reasoning_effort", REASONING_EFFORTS),
        choice_value(values, "service_tier", SERVICE_TIERS),
        _continuation(values.get("continuation")),
        choice_value(values, "cache_strategy", CACHE_STRATEGIES),
        _local_artifact_reuse(values.get("local_artifact_reuse")),
        _identity(values.get("identity")),
        _usage(values.get("usage")),
        count_value(values, "rework_count"),
        _verification(values),
    )
