#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Import the immutable attempt-receipt types.
# 3. Test: uv run scripts/test_agent_company_attempt_receipt.py
# ─────────────────

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

from dataclasses import dataclass
from typing import Final


FORMAT: Final[str] = "agent-company.attempt-cost-receipt/v0.1"
FIELDS: Final = frozenset({
    "format", "attempt_id", "routing_mode", "requested_profile", "effective_model",
    "reasoning_effort", "service_tier", "continuation", "cache_strategy", "identity",
    "local_artifact_reuse", "usage", "rework_count", "verified_quality_score",
    "critical_verification_regression", "verifier_id", "verified_at",
    "verification_evidence_sha256", "verification_evidence_refs",
})
CONTINUATION_FIELDS: Final = frozenset({
    "action", "adjacent_work", "stable_prefix_reusable", "context_health",
    "model_change_required", "independent_verification_required",
    "inherited_context_risk", "invalidation_reasons", "prior_attempt_id",
    "prior_identity_sha256",
})
LOCAL_ARTIFACT_FIELDS: Final = frozenset({
    "status", "artifact_count", "artifact_set_sha256", "evidence_refs",
})
IDENTITY_FIELDS: Final = frozenset({
    "source_sha256", "decision_sha256", "capsule_sha256", "rules_sha256",
    "plugin_set_sha256", "tool_schema_sha256", "stable_prefix_sha256",
})
USAGE_FIELDS: Final = frozenset({
    "input_tokens", "cached_input_tokens", "cache_write_input_tokens",
    "output_tokens", "reasoning_tokens",
})
PROFILES: Final = frozenset({
    "exploration-high", "execution-low", "execution-medium", "execution-high",
    "verification-high",
})
REASONING_EFFORTS: Final = frozenset({"none", "low", "medium", "high", "xhigh"})
SERVICE_TIERS: Final = frozenset({"default", "fast", "flex", "priority"})
CONTEXT_HEALTH: Final = frozenset({"healthy", "degraded", "bloated"})
CACHE_STRATEGIES: Final = frozenset({"none", "implicit", "explicit"})
INVALIDATION_REASONS: Final = frozenset({
    "source_changed", "decision_changed", "capsule_changed", "rules_changed",
    "plugin_changed", "tool_schema_changed", "model_contract_changed",
    "verification_contradiction",
})
@dataclass(frozen=True, slots=True)
class ContinuationDecision:
    action: str
    adjacent_work: bool
    stable_prefix_reusable: bool
    context_health: str
    model_change_required: bool
    independent_verification_required: bool
    inherited_context_risk: bool
    invalidation_reasons: tuple[str, ...]
    prior_attempt_id: str | None
    prior_identity_sha256: str | None


@dataclass(frozen=True, slots=True)
class AttemptIdentity:
    source_sha256: str
    decision_sha256: str
    capsule_sha256: str
    rules_sha256: str
    plugin_set_sha256: str
    tool_schema_sha256: str
    stable_prefix_sha256: str


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int
    cached_input_tokens: int | None
    cache_write_input_tokens: int | None
    output_tokens: int
    reasoning_tokens: int


@dataclass(frozen=True, slots=True)
class LocalArtifactReuse:
    status: str
    artifact_count: int
    artifact_set_sha256: str | None
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VerificationObservation:
    quality_score: float | None
    critical_regression: bool | None
    verifier_id: str | None
    verified_at: str | None
    evidence_sha256: str | None
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AttemptReceipt:
    attempt_id: str
    routing_mode: str
    requested_profile: str
    effective_model: str
    reasoning_effort: str
    service_tier: str
    continuation: ContinuationDecision
    cache_strategy: str
    local_artifact_reuse: LocalArtifactReuse
    identity: AttemptIdentity
    usage: TokenUsage
    rework_count: int
    verification: VerificationObservation
