"""Immutable receipt validation for observed Agent Company model routing."""

from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportUnnecessaryComparison=false, reportUnusedCallResult=false
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, assert_never, override

from agent_company_deps import JsonValue
from agent_company_evidence_digest import (
    EvidenceDigestError,
    read_stable_json_evidence,
    require_matching_evidence_digest,
)
from agent_company_model_routing import ModelRoutingDecision, RoutingDisposition

FORMAT: Final[str] = "agent-company.model-routing-receipt/v0.1"
ALGORITHM: Final[str] = "sha256-canonical-json/v1"
SHA256: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
SLUG: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9-]*$")
TOP_FIELDS: Final[frozenset[str]] = frozenset({"format", "canonical_algorithm", "receipt_id", "worker", "worker_packet", "decision_binding", "observed_effective", "changed_files", "tests", "failed_or_unverified", "credit_usage", "elapsed_seconds", "residual_risk", "final_status"})
LINEAGE_FIELDS: Final[tuple[str, ...]] = (
    "request_digest", "registry_digest", "registry_projection_digest",
    "policy_digest", "policy_projection_digest", "rate_card_digest",
    "capacity_digest",
)
PROFILES: Final[frozenset[str]] = frozenset({"mechanical", "standard-implementation", "bounded-deep", "integration", "specialist-reasoning", "role-lead-judgment", "company-judgment"})
ROLES: Final[frozenset[str]] = frozenset({"founder", "planning", "marketing", "design", "development", "qa-release"})
type CreditProvenance = Literal["actual", "estimated", "unknown"]
CREDIT_PROVENANCE: Final[dict[str, CreditProvenance]] = {"actual": "actual", "estimated": "estimated", "unknown": "unknown"}
HOST_OBSERVATION_FORMAT: Final[str] = "agent-company.host-runtime-observation/v0.1"
ACTUAL_CREDIT_FORMAT: Final[str] = "agent-company.actual-credit-usage/v0.1"


@dataclass(frozen=True, slots=True)
class ModelRoutingReceiptError(Exception):
    code: str
    detail: str

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class ModelRoutingReceipt:
    receipt_id: str
    worker_id: str
    role: str
    task_type: str
    worker_packet_sha256: str
    decision_id: str
    effective_model_id: str
    effective_reasoning_effort: str
    credit_provenance: CreditProvenance


@dataclass(frozen=True, slots=True)
class ModelRoutingReceiptIdentity:
    """Canonical self-identifying fields available before route revalidation."""

    receipt_id: str
    decision_id: str
    worker_id: str


def _error(detail: str) -> ModelRoutingReceiptError:
    return ModelRoutingReceiptError("model_routing_receipt_invalid", detail)


def _object(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise _error(f"{label} must be an object")
    return value


def _exact(value: dict[str, JsonValue], fields: frozenset[str], label: str) -> None:
    if frozenset(value) != fields:
        raise _error(f"{label} fields are not exact")


def _text(value: JsonValue, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(f"{label} must be non-empty text")
    return value


def _sha(value: JsonValue, label: str) -> str:
    selected = _text(value, label)
    if SHA256.fullmatch(selected) is None:
        raise _error(f"{label} must be lowercase SHA-256")
    return selected


def _number(value: JsonValue, label: str) -> float:
    if (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        raise _error(f"{label} must be a non-negative number")
    return float(value)


def _string_list(value: JsonValue, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _error(f"{label} must be an array")
    result = tuple(_text(item, label) for item in value)
    if len(result) != len(set(result)):
        raise _error(f"{label} must not contain duplicates")
    return result


def model_routing_receipt_identity(value: dict[str, JsonValue]) -> str:
    """Hash exact canonical receipt content without the self-identity field."""
    content = {key: item for key, item in value.items() if key != "receipt_id"}
    encoded = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_model_routing_receipt_self_identity(
    value: JsonValue,
) -> ModelRoutingReceiptIdentity:
    """Validate receipt envelope identity without accepting a routing decision."""
    values = _object(value, "model routing receipt")
    _exact(values, TOP_FIELDS, "model routing receipt")
    if values.get("format") != FORMAT or values.get("canonical_algorithm") != ALGORITHM:
        raise _error("receipt format or canonical algorithm is unsupported")
    receipt_id = _sha(values.get("receipt_id"), "receipt_id")
    if receipt_id != model_routing_receipt_identity(values):
        raise _error("receipt identity does not match canonical content")
    worker = _object(values.get("worker"), "worker")
    _exact(worker, frozenset({"worker_id", "role", "task_type"}), "worker")
    decision = _object(values.get("decision_binding"), "decision_binding")
    return ModelRoutingReceiptIdentity(
        receipt_id,
        _sha(decision.get("decision_id"), "decision_binding.decision_id"),
        _text(worker.get("worker_id"), "worker.worker_id"),
    )


def _verified_evidence(
    reference: str,
    expected_sha256: str,
    base_dir: Path,
    label: str,
) -> dict[str, JsonValue]:
    try:
        evidence = read_stable_json_evidence(reference, base_dir)
        require_matching_evidence_digest(evidence, expected_sha256)
    except EvidenceDigestError as exc:
        raise _error(f"{label} evidence is invalid: {exc}") from exc
    return evidence.payload


def _validate_credit(value: JsonValue, evidence_base_dir: Path) -> CreditProvenance:
    credit = _object(value, "credit_usage")
    raw_provenance = _text(credit.get("provenance"), "credit_usage.provenance")
    try:
        provenance = CREDIT_PROVENANCE[raw_provenance]
    except KeyError as exc:
        raise _error("credit_usage provenance is unsupported") from exc
    match provenance:
        case "actual":
            _exact(credit, frozenset({"provenance", "credits", "evidence_ref", "evidence_sha256"}), "credit_usage")
            credits = _number(credit.get("credits"), "credit_usage.credits")
            reference = _text(credit.get("evidence_ref"), "credit_usage.evidence_ref")
            digest = _sha(credit.get("evidence_sha256"), "credit_usage.evidence_sha256")
            evidence = _verified_evidence(
                reference,
                digest,
                evidence_base_dir,
                "actual credit usage",
            )
            _exact(evidence, frozenset({"format", "credits"}), "actual credit evidence")
            if evidence.get("format") != ACTUAL_CREDIT_FORMAT:
                raise _error("actual credit evidence format is unsupported")
            if _number(evidence.get("credits"), "actual credit evidence.credits") != credits:
                raise _error("actual credit evidence differs from receipt credits")
        case "estimated":
            _exact(credit, frozenset({"provenance", "credits", "basis"}), "credit_usage")
            _number(credit.get("credits"), "credit_usage.credits")
            _text(credit.get("basis"), "credit_usage.basis")
        case "unknown":
            _exact(credit, frozenset({"provenance", "reason"}), "credit_usage")
            _text(credit.get("reason"), "credit_usage.reason")
        case unreachable:
            assert_never(unreachable)
    return provenance


def _validate_outcomes(values: dict[str, JsonValue]) -> None:
    changes = values.get("changed_files")
    tests = values.get("tests")
    if not isinstance(changes, list) or not isinstance(tests, list) or not tests:
        raise _error("changed_files and non-empty tests must be arrays")
    paths: list[str] = []
    for item in changes:
        row = _object(item, "changed_files item")
        _exact(row, frozenset({"path", "summary"}), "changed_files item")
        paths.append(_text(row.get("path"), "changed_files.path"))
        _text(row.get("summary"), "changed_files.summary")
    commands: list[str] = []
    for item in tests:
        row = _object(item, "tests item")
        _exact(row, frozenset({"command", "status", "actual_result"}), "tests item")
        commands.append(_text(row.get("command"), "tests.command"))
        if row.get("status") not in {"passed", "failed", "unverified"}:
            raise _error("tests.status is unsupported")
        _text(row.get("actual_result"), "tests.actual_result")
    if len(paths) != len(set(paths)) or len(commands) != len(set(commands)):
        raise _error("changed files and test commands must be unique")
    _string_list(values.get("failed_or_unverified"), "failed_or_unverified")
    _string_list(values.get("residual_risk"), "residual_risk")
    _number(values.get("elapsed_seconds"), "elapsed_seconds")
    if values.get("final_status") not in {"completed", "failed", "blocked", "unverified"}:
        raise _error("final_status is unsupported")


def _validate_attempts(
    value: JsonValue,
    expected: ModelRoutingDecision,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise _error("ordered attempts must be a non-empty array")
    observed: list[tuple[int, str, str]] = []
    for item in value:
        row = _object(item, "ordered attempt")
        _exact(row, frozenset({"sequence", "semantic_profile", "cause"}), "ordered attempt")
        sequence = row.get("sequence")
        profile = _text(row.get("semantic_profile"), "attempt semantic_profile")
        cause = _text(row.get("cause"), "attempt cause")
        if not isinstance(sequence, int) or isinstance(sequence, bool):
            raise _error("attempt sequence must be an integer")
        observed.append((sequence, profile, cause))
    expected_rows = tuple(
        (index, attempt.semantic_profile, attempt.cause.value)
        for index, attempt in enumerate(expected.fallback_attempts, start=1)
    )
    if tuple(observed) != expected_rows:
        raise _error("ordered attempts differ from the routing decision")
    return tuple(row[1] for row in observed)


def _validate_expected_decision(expected: ModelRoutingDecision) -> None:
    if type(expected) is not ModelRoutingDecision:
        raise _error("expected routing decision has an invalid runtime type")
    if (
        expected.format != "agent-company.model-routing-decision/v0.2"
        or expected.canonical_algorithm != ALGORITHM
        or expected.disposition is not RoutingDisposition.DISPATCH
        or expected.validation_errors
        or expected.requested_profile not in PROFILES
        or expected.selected_profile not in PROFILES
        or expected.effective_model_id is None
        or expected.effective_reasoning_effort is None
    ):
        raise _error("expected routing decision is not a valid dispatch decision")
    for field in (expected.decision_id, expected.request_digest, expected.registry_digest, expected.registry_projection_digest, expected.policy_digest, expected.policy_projection_digest, expected.rate_card_digest, expected.capacity_digest):
        _sha(field, "expected routing lineage")


def validate_model_routing_receipt(
    value: JsonValue,
    expected_decision: ModelRoutingDecision,
    expected_worker_id: str,
    expected_packet_sha256: str,
    evidence_base_dir: Path,
) -> ModelRoutingReceipt:
    """Validate content identity, routing lineage, and observed execution."""
    values = _object(value, "model routing receipt")
    identity = validate_model_routing_receipt_self_identity(values)
    receipt_id = identity.receipt_id
    _validate_expected_decision(expected_decision)
    worker = _object(values.get("worker"), "worker")
    _exact(worker, frozenset({"worker_id", "role", "task_type"}), "worker")
    worker_id = identity.worker_id
    role = _text(worker.get("role"), "worker.role")
    task_type = _text(worker.get("task_type"), "worker.task_type")
    if role not in ROLES or SLUG.fullmatch(task_type) is None:
        raise _error("receipt role or task type is unsupported")
    if worker_id != expected_worker_id:
        raise _error("receipt worker differs from the routed worker")
    packet = _object(values.get("worker_packet"), "worker_packet")
    _exact(packet, frozenset({"ref", "sha256"}), "worker_packet")
    packet_ref = _text(packet.get("ref"), "worker_packet.ref")
    packet_sha = _sha(packet.get("sha256"), "worker_packet.sha256")
    if packet_sha != expected_packet_sha256:
        raise _error("receipt packet differs from the routed packet")
    binding = _object(values.get("decision_binding"), "decision_binding")
    expected_fields = frozenset({"ref", "decision_id", *LINEAGE_FIELDS, "requested_profile", "selected_profile", "selection_reason", "ordered_attempts"})
    _exact(binding, expected_fields, "decision_binding")
    decision_ref = _text(binding.get("ref"), "decision_binding.ref")
    for field in ("decision_id", *LINEAGE_FIELDS):
        _sha(binding.get(field), f"decision_binding.{field}")
    if binding.get("requested_profile") not in PROFILES or binding.get("selected_profile") not in PROFILES:
        raise _error("receipt requested or selected profile is unsupported")
    binding_values = tuple(binding.get(key) for key in ("decision_id", *LINEAGE_FIELDS, "requested_profile", "selected_profile", "selection_reason"))
    expected_values = (expected_decision.decision_id, expected_decision.request_digest, expected_decision.registry_digest, expected_decision.registry_projection_digest, expected_decision.policy_digest, expected_decision.policy_projection_digest, expected_decision.rate_card_digest, expected_decision.capacity_digest, expected_decision.requested_profile, expected_decision.selected_profile, expected_decision.selection_reason)
    if binding_values != expected_values:
        raise _error("receipt decision or routing lineage differs from the decision")
    _validate_attempts(binding.get("ordered_attempts"), expected_decision)
    observed = _object(values.get("observed_effective"), "observed_effective")
    _exact(observed, frozenset({"source_kind", "model_id", "reasoning_effort", "evidence_ref", "evidence_sha256"}), "observed_effective")
    if observed.get("source_kind") != "host_runtime_observation":
        raise _error("effective model must come from a host runtime observation")
    model = _text(observed.get("model_id"), "observed_effective.model_id")
    effort = _text(observed.get("reasoning_effort"), "observed_effective.reasoning_effort")
    observation_ref = _text(observed.get("evidence_ref"), "observed_effective.evidence_ref")
    observation_digest = _sha(
        observed.get("evidence_sha256"), "observed_effective.evidence_sha256"
    )
    if (model, effort) != (expected_decision.effective_model_id, expected_decision.effective_reasoning_effort):
        raise _error("observed effective model or effort differs from the decision")
    if observation_ref in {packet_ref, decision_ref}:
        raise _error("runtime observation must be independent from request artifacts")
    observation = _verified_evidence(
        observation_ref,
        observation_digest,
        evidence_base_dir,
        "host runtime observation",
    )
    _exact(
        observation,
        frozenset({"format", "model_id", "reasoning_effort"}),
        "host runtime observation",
    )
    if observation.get("format") != HOST_OBSERVATION_FORMAT:
        raise _error("host runtime observation format is unsupported")
    if (
        _text(observation.get("model_id"), "host runtime observation.model_id"),
        _text(
            observation.get("reasoning_effort"),
            "host runtime observation.reasoning_effort",
        ),
    ) != (model, effort):
        raise _error("host runtime observation differs from receipt effective model")
    _validate_outcomes(values)
    credit_provenance = _validate_credit(
        values.get("credit_usage"), evidence_base_dir
    )
    return ModelRoutingReceipt(receipt_id, worker_id, role, task_type, packet_sha, expected_decision.decision_id, model, effort, credit_provenance)
