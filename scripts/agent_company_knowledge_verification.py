from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final

from agent_company_expertise_catalog import load_expertise_catalog
from agent_company_expertise_models import ExpertiseCatalog
from agent_company_knowledge_verification_provenance import (
    SHA256,
    KnowledgeByteProvenance,
    KnowledgeProvenanceError,
    parse_byte_provenance,
)
from agent_company_role_schema import JsonValue

FORMAT: Final[str] = "agent-company.knowledge-use-verification/v0.3"
LEGACY_FORMAT: Final[str] = "agent-company.knowledge-use-verification/v0.2"
ATTESTATION_SCOPE: Final[str] = "independent_knowledge_application_review"
TOP_FIELDS: Final[frozenset[str]] = frozenset({
    "format", "verification_id", "issuer_role", "issuer_ref", "reviews",
    "verified_at", "attestation_scope",
})
CURRENT_TOP_FIELDS: Final[frozenset[str]] = TOP_FIELDS | {"byte_provenance"}
REVIEW_FIELDS: Final[frozenset[str]] = frozenset({
    "worker_id", "role", "executor_ref", "reviewer_role", "reviewer_ref",
    "context_id", "knowledge_receipt_id", "required_reference_ids",
    "application_findings", "verdict",
})
FINDING_FIELDS: Final[frozenset[str]] = frozenset({
    "reference_id", "decision_question", "outcome", "evidence_refs",
})


class KnowledgeVerificationError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class KnowledgeVerificationBinding:
    worker_id: str
    context_id: str
    knowledge_receipt_id: str
    required_reference_ids: tuple[str, ...]
    verification_id: str
    byte_provenance: KnowledgeByteProvenance | None = None


@dataclass(frozen=True, slots=True)
class TrustedVerificationAuthority:
    issuer_role: str
    issuer_ref: str
    reviewer_refs: dict[str, frozenset[str]]


def _object(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise KnowledgeVerificationError(f"{label} must be an object")
    return value


def _objects(value: JsonValue | None, label: str) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list):
        raise KnowledgeVerificationError(f"{label} must be a list")
    return tuple(_object(item, f"{label}[{index}]") for index, item in enumerate(value))


def _text(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeVerificationError(f"{label} must be non-empty text")
    return value


def _texts(
    value: JsonValue | None,
    label: str,
    *,
    nonempty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise KnowledgeVerificationError(f"{label} must be a list")
    result = tuple(_text(item, label) for item in value)
    if nonempty and not result:
        raise KnowledgeVerificationError(f"{label} must not be empty")
    if len(result) != len(set(result)):
        raise KnowledgeVerificationError(f"{label} must be unique")
    return result


def _exact(value: dict[str, JsonValue], fields: frozenset[str], label: str) -> None:
    if frozenset(value) != fields:
        raise KnowledgeVerificationError(f"{label} has an unexpected shape")


def _canonical(value: dict[str, JsonValue]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def knowledge_verification_identity(value: dict[str, JsonValue]) -> str:
    body = {key: item for key, item in value.items() if key != "verification_id"}
    return hashlib.sha256(_canonical(body)).hexdigest()


def _timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KnowledgeVerificationError("verified_at is invalid") from exc
    if parsed.tzinfo is None:
        raise KnowledgeVerificationError("verified_at must include a timezone")


def _review_binding(
    raw: dict[str, JsonValue],
    authority: TrustedVerificationAuthority,
    assignments: dict[str, dict[str, JsonValue]],
    terminals: dict[str, dict[str, JsonValue]],
    catalog: ExpertiseCatalog,
    verification_id: str,
) -> KnowledgeVerificationBinding | None:
    _exact(raw, REVIEW_FIELDS, "knowledge verification review")
    worker_id = _text(raw.get("worker_id"), "review.worker_id")
    assignment = assignments.get(worker_id)
    terminal = terminals.get(worker_id)
    if assignment is None or terminal is None:
        raise KnowledgeVerificationError(f"review names unknown worker {worker_id}")
    role = _text(raw.get("role"), "review.role")
    if role != assignment.get("role") or role not in catalog.roles:
        raise KnowledgeVerificationError(f"review role mismatch for {worker_id}")
    reviewer_role = _text(raw.get("reviewer_role"), "review.reviewer_role")
    if reviewer_role != catalog.roles[role].default_verifier:
        raise KnowledgeVerificationError(f"review uses the wrong independent verifier for {role}")
    reviewer_ref = _text(raw.get("reviewer_ref"), "review.reviewer_ref")
    executor_ref = _text(raw.get("executor_ref"), "review.executor_ref")
    if executor_ref != terminal.get("backend_worker_ref") or executor_ref == reviewer_ref:
        raise KnowledgeVerificationError(f"review is not independent from {worker_id}")
    if reviewer_ref not in authority.reviewer_refs.get(reviewer_role, frozenset()):
        raise KnowledgeVerificationError(f"reviewer is not bound to trusted execution for {role}")
    context_id = _text(raw.get("context_id"), "review.context_id")
    receipt_id = _text(raw.get("knowledge_receipt_id"), "review.knowledge_receipt_id")
    if SHA256.fullmatch(context_id) is None or SHA256.fullmatch(receipt_id) is None:
        raise KnowledgeVerificationError(f"review ids are malformed for {worker_id}")
    required = _texts(
        raw.get("required_reference_ids"),
        "review.required_reference_ids",
        nonempty=True,
    )
    findings = _objects(raw.get("application_findings"), "review.application_findings")
    finding_ids: list[str] = []
    applied = True
    for finding in findings:
        _exact(finding, FINDING_FIELDS, "knowledge application finding")
        reference_id = _text(finding.get("reference_id"), "finding.reference_id")
        finding_ids.append(reference_id)
        _ = _text(finding.get("decision_question"), "finding.decision_question")
        outcome = _text(finding.get("outcome"), "finding.outcome")
        evidence = _texts(finding.get("evidence_refs"), "finding.evidence_refs")
        if outcome not in {"applied", "misapplied", "unobserved"}:
            raise KnowledgeVerificationError(f"finding outcome is invalid for {worker_id}")
        applied = applied and outcome == "applied" and bool(evidence)
    if tuple(finding_ids) != required:
        raise KnowledgeVerificationError(f"review findings do not cover required refs for {worker_id}")
    verdict = _text(raw.get("verdict"), "review.verdict")
    if verdict not in {"verified", "rejected", "unverified"}:
        raise KnowledgeVerificationError(f"review verdict is invalid for {worker_id}")
    if verdict == "verified" and not applied:
        raise KnowledgeVerificationError(f"verified review lacks applied evidence for {worker_id}")
    if verdict != "verified":
        return None
    return KnowledgeVerificationBinding(
        worker_id,
        context_id,
        receipt_id,
        required,
        verification_id,
    )


def validate_knowledge_verification(
    value: JsonValue,
    assignments: dict[str, dict[str, JsonValue]],
    terminals: dict[str, dict[str, JsonValue]],
    authority: TrustedVerificationAuthority,
    catalog: ExpertiseCatalog | None = None,
) -> dict[str, KnowledgeVerificationBinding]:
    payload = _object(value, "knowledge verification")
    artifact_format = payload.get("format")
    if artifact_format == FORMAT:
        _exact(payload, CURRENT_TOP_FIELDS, "knowledge verification")
        try:
            byte_provenance = parse_byte_provenance(payload.get("byte_provenance"))
        except KnowledgeProvenanceError as exc:
            raise KnowledgeVerificationError(str(exc)) from exc
    elif artifact_format == LEGACY_FORMAT:
        _exact(payload, TOP_FIELDS, "knowledge verification")
        byte_provenance = None
    else:
        raise KnowledgeVerificationError("knowledge verification format is unsupported")
    if payload.get("attestation_scope") != ATTESTATION_SCOPE:
        raise KnowledgeVerificationError("knowledge verification format or scope is unsupported")
    verification_id = _text(payload.get("verification_id"), "verification_id")
    if verification_id != knowledge_verification_identity(payload):
        raise KnowledgeVerificationError("knowledge verification identity mismatch")
    issuer_role = _text(payload.get("issuer_role"), "issuer_role")
    issuer_ref = _text(payload.get("issuer_ref"), "issuer_ref")
    if issuer_role != authority.issuer_role or issuer_ref != authority.issuer_ref:
        raise KnowledgeVerificationError("knowledge verification issuer is not trusted")
    verified_at = _text(payload.get("verified_at"), "verified_at")
    _timestamp(verified_at)
    selected = catalog or load_expertise_catalog()
    result: dict[str, KnowledgeVerificationBinding] = {}
    reviewed_workers: list[str] = []
    for raw in _objects(payload.get("reviews"), "reviews"):
        binding = _review_binding(
            raw,
            authority,
            assignments,
            terminals,
            selected,
            verification_id,
        )
        worker_id = _text(raw.get("worker_id"), "review.worker_id")
        reviewed_workers.append(worker_id)
        if worker_id in result:
            raise KnowledgeVerificationError(f"duplicate review for {worker_id}")
        if binding is not None:
            result[worker_id] = replace(binding, byte_provenance=byte_provenance)
    if (
        byte_provenance is not None
        and tuple(item.worker_id for item in byte_provenance.worker_artifacts)
        != tuple(reviewed_workers)
    ):
        raise KnowledgeVerificationError(
            "byte_provenance worker artifacts do not match reviewed workers",
        )
    return result
