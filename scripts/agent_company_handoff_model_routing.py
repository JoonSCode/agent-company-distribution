"""Validate the optional S3 routing receipt binding at the handoff seam."""

from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
from dataclasses import dataclass
from pathlib import Path
from typing import Final, override

from agent_company_deps import JsonValue
from agent_company_evidence_digest import (
    EvidenceDigestError,
    read_stable_json_evidence,
    require_matching_evidence_digest,
)
from agent_company_execution_contract import (
    WORKER_PACKET_CANONICAL_ALGORITHM,
    model_routing_binding,
    worker_packet_sha256,
)
from agent_company_model_routing import (
    CAPACITY_FORMAT,
    REQUEST_FORMAT,
    FallbackAttempt,
    FallbackCause,
    ModelRoutingDecision,
    RoutingDisposition,
)
from agent_company_model_routing_receipt import (
    ModelRoutingReceiptError,
    validate_model_routing_receipt,
)
from agent_company_projection_validation import PolicyError

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
ROUTING_FIELDS: Final[frozenset[str]] = frozenset({
    "format", "decision_id", "disposition", "request_digest",
    "registry_digest", "registry_projection_digest", "policy_digest",
    "policy_projection_digest", "rate_card_digest", "capacity_digest",
    "requested_profile", "selected_profile", "effective_model",
    "reasoning_effort", "adapter", "predicate_id", "selection_reason",
    "fallback_attempts",
})
RECEIPT_BINDING_FIELDS: Final[frozenset[str]] = frozenset({
    "ref", "sha256", "receipt_id", "decision_id", "worker_id",
})


@dataclass(frozen=True, slots=True)
class ModelRoutingHandoffError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class ModelRoutingHandoffEvidence:
    reference: str
    sha256: str
    receipt_id: str


def _error(detail: str) -> ModelRoutingHandoffError:
    return ModelRoutingHandoffError(detail)


def _object(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise _error(f"{label} must be an object")
    return value


def _exact(
    value: dict[str, JsonValue],
    fields: frozenset[str],
    label: str,
) -> None:
    if frozenset(value) != fields:
        raise _error(f"{label} fields are not exact")


def _text(value: JsonValue, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(f"{label} must be non-empty text")
    return value


def _attempts(value: JsonValue) -> tuple[FallbackAttempt, ...]:
    if not isinstance(value, list) or not value:
        raise _error("model_routing_binding fallback_attempts must be non-empty")
    result: list[FallbackAttempt] = []
    for item in value:
        row = _object(item, "model routing fallback attempt")
        _exact(
            row,
            frozenset({"semantic_profile", "cause"}),
            "model routing fallback attempt",
        )
        try:
            cause = FallbackCause(_text(row.get("cause"), "fallback cause"))
        except ValueError as exc:
            raise _error("model routing fallback cause is unsupported") from exc
        result.append(FallbackAttempt(
            _text(row.get("semantic_profile"), "fallback semantic_profile"),
            cause,
        ))
    return tuple(result)


def _decision(value: JsonValue) -> ModelRoutingDecision:
    routing = _object(value, "assignment model_routing_binding")
    _exact(routing, ROUTING_FIELDS, "assignment model_routing_binding")
    if routing.get("disposition") != RoutingDisposition.DISPATCH.value:
        raise _error("assignment model routing must be a dispatch decision")
    decision = ModelRoutingDecision(
        _text(routing.get("format"), "routing format"),
        WORKER_PACKET_CANONICAL_ALGORITHM,
        RoutingDisposition.DISPATCH,
        _text(routing.get("requested_profile"), "requested profile"),
        _text(routing.get("selected_profile"), "selected profile"),
        _text(routing.get("effective_model"), "effective model"),
        _text(routing.get("reasoning_effort"), "reasoning effort"),
        _text(routing.get("adapter"), "adapter"),
        _text(routing.get("predicate_id"), "predicate id"),
        _text(routing.get("selection_reason"), "selection reason"),
        _attempts(routing.get("fallback_attempts")),
        REQUEST_FORMAT,
        CAPACITY_FORMAT,
        _text(routing.get("request_digest"), "request digest"),
        _text(routing.get("registry_digest"), "registry digest"),
        _text(routing.get("registry_projection_digest"), "registry projection digest"),
        _text(routing.get("policy_digest"), "policy digest"),
        _text(routing.get("policy_projection_digest"), "policy projection digest"),
        _text(routing.get("rate_card_digest"), "rate card digest"),
        _text(routing.get("capacity_digest"), "capacity digest"),
        (),
        _text(routing.get("decision_id"), "decision id"),
    )
    try:
        projected = model_routing_binding(decision)
    except PolicyError as exc:
        raise _error(f"assignment model routing is invalid: {exc}") from exc
    if projected != routing:
        raise _error("assignment model routing projection is not canonical")
    return decision


def validate_model_routing_handoff(
    assignment: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> ModelRoutingHandoffEvidence | None:
    """Bind routed assignments to one stable, independently observed receipt."""
    raw_routing = assignment.get("model_routing_binding")
    raw_receipt_binding = payload.get("model_routing_receipt_binding")
    if raw_routing is None:
        if raw_receipt_binding is not None:
            raise _error("legacy assignment carries an unbound routing receipt")
        return None
    if raw_receipt_binding is None:
        raise _error("model routing receipt binding is required")
    if assignment.get("worker_packet_canonical_algorithm") != WORKER_PACKET_CANONICAL_ALGORITHM:
        raise _error("routed worker packet canonical algorithm is invalid")
    expected_packet_sha = _text(
        assignment.get("worker_packet_sha256"),
        "worker packet sha256",
    )
    try:
        actual_packet_sha = worker_packet_sha256(assignment)
    except (TypeError, ValueError) as exc:
        raise _error("routed worker packet cannot be canonicalized") from exc
    if expected_packet_sha != actual_packet_sha:
        raise _error("routed worker packet digest does not match assignment bytes")
    decision = _decision(raw_routing)
    binding = _object(raw_receipt_binding, "model routing receipt binding")
    _exact(binding, RECEIPT_BINDING_FIELDS, "model routing receipt binding")
    reference = _text(binding.get("ref"), "routing receipt ref")
    expected_receipt_sha = _text(binding.get("sha256"), "routing receipt sha256")
    try:
        evidence = read_stable_json_evidence(reference, ROOT)
        require_matching_evidence_digest(evidence, expected_receipt_sha)
        receipt = validate_model_routing_receipt(
            evidence.payload,
            decision,
            _text(assignment.get("worker_id"), "assignment worker_id"),
            expected_packet_sha,
            evidence.path.parent,
        )
    except (EvidenceDigestError, ModelRoutingReceiptError) as exc:
        raise _error(f"model routing receipt is invalid: {exc}") from exc
    context = _object(
        assignment.get("knowledge_context_binding"),
        "assignment knowledge_context_binding",
    )
    expected_role = _text(assignment.get("role"), "assignment role")
    expected_task = _text(context.get("task_type"), "assignment task_type")
    expected_binding = (
        receipt.receipt_id,
        receipt.decision_id,
        receipt.worker_id,
    )
    actual_binding = (
        binding.get("receipt_id"),
        binding.get("decision_id"),
        binding.get("worker_id"),
    )
    if expected_binding != actual_binding:
        raise _error("model routing receipt binding differs from validated content")
    if (receipt.role, receipt.task_type) != (expected_role, expected_task):
        raise _error("model routing receipt role or task differs from assignment")
    return ModelRoutingHandoffEvidence(
        evidence.reference,
        str(evidence.sha256),
        receipt.receipt_id,
    )
