from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from agent_company_expertise_catalog import ExpertiseCatalog, load_expertise_catalog
from agent_company_knowledge_context import (
    KnowledgeContext,
    KnowledgeContextError,
    validate_knowledge_context,
)
from agent_company_role_schema import JsonValue

FORMAT: Final[str] = "agent-company.knowledge-usage-receipt/v0.2"
REPORTER: Final[str] = "role-worker"
ATTESTATION_SCOPE: Final[str] = "worker_reported_use_independent_verification_required"
FIELDS: Final[frozenset[str]] = frozenset({
    "format", "receipt_id", "context_id", "role", "task_type",
    "objective_sha256", "decision_questions", "registry_sha256",
    "manifest_sha256", "required_reference_ids", "used_references",
    "unused_reference_ids", "specialist_skills", "reported_by",
    "reported_at", "attestation_scope",
})
USED_FIELDS: Final[frozenset[str]] = frozenset(
    {"id", "version", "ref", "sha256", "decisions_supported"}
)


@dataclass(frozen=True, slots=True)
class KnowledgeReceiptError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class KnowledgeReceipt:
    receipt_id: str
    context_id: str
    role: str
    task_type: str
    required_reference_ids: tuple[str, ...]
    specialist_skills: tuple[str, ...]
    reported_at: str


def canonical(value: dict[str, JsonValue]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def receipt_identity(payload: dict[str, JsonValue]) -> str:
    body = {key: value for key, value in payload.items() if key != "receipt_id"}
    return hashlib.sha256(canonical(body)).hexdigest()


def object_value(value: JsonValue | None, field: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise KnowledgeReceiptError("knowledge_receipt_malformed", f"{field} must be an object")
    return value


def _objects(value: JsonValue | None, field: str) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list):
        raise KnowledgeReceiptError("knowledge_receipt_malformed", f"{field} must be a list")
    return tuple(object_value(item, f"{field}[{index}]") for index, item in enumerate(value))


def _text(values: dict[str, JsonValue], field: str) -> str:
    value = values.get(field)
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeReceiptError("knowledge_receipt_malformed", f"{field} must be non-empty text")
    return value


def _texts(
    value: JsonValue | None,
    field: str,
    *,
    nonempty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise KnowledgeReceiptError("knowledge_receipt_malformed", f"{field} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise KnowledgeReceiptError("knowledge_receipt_malformed", f"{field} contains invalid text")
        result.append(item)
    if nonempty and not result:
        raise KnowledgeReceiptError("knowledge_receipt_malformed", f"{field} must not be empty")
    if len(set(result)) != len(result):
        raise KnowledgeReceiptError("knowledge_receipt_malformed", f"{field} must be unique")
    return tuple(result)


def _timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KnowledgeReceiptError("knowledge_receipt_malformed", "reported_at is invalid") from exc
    if parsed.tzinfo is None:
        raise KnowledgeReceiptError("knowledge_receipt_malformed", "reported_at must include a timezone")


def validated_context(
    role: str,
    objective: str,
    context: JsonValue | None,
    catalog: ExpertiseCatalog,
) -> tuple[dict[str, JsonValue], KnowledgeContext]:
    raw = object_value(context, "knowledge_context_binding")
    try:
        parsed = validate_knowledge_context(role, objective, raw, catalog)
    except KnowledgeContextError as exc:
        raise KnowledgeReceiptError(exc.code, exc.detail) from exc
    return raw, parsed


def validate_knowledge_receipt(
    role: str,
    objective: str,
    value: JsonValue | None,
    catalog: ExpertiseCatalog | None = None,
    *,
    expected_context: JsonValue | None,
) -> KnowledgeReceipt:
    payload = object_value(value, "knowledge_usage_receipt")
    if set(payload) != FIELDS or payload.get("format") != FORMAT:
        raise KnowledgeReceiptError("knowledge_receipt_malformed", "unexpected receipt shape or format")
    selected = catalog or load_expertise_catalog()
    raw_context, context = validated_context(role, objective, expected_context, selected)
    if payload.get("role") != role or payload.get("context_id") != context.context_id:
        raise KnowledgeReceiptError("knowledge_context_mismatch", "receipt is not bound to the issued context")
    mirrored_fields = (
        "task_type", "objective_sha256", "decision_questions",
        "registry_sha256", "manifest_sha256", "required_reference_ids",
        "specialist_skills",
    )
    if any(payload.get(field) != raw_context.get(field) for field in mirrored_fields):
        raise KnowledgeReceiptError("knowledge_context_mismatch", "receipt changes issued context fields")
    required = _texts(payload.get("required_reference_ids"), "required_reference_ids", nonempty=True)
    decisions = _texts(payload.get("decision_questions"), "decision_questions", nonempty=True)
    unused = _texts(payload.get("unused_reference_ids"), "unused_reference_ids")
    if set(required) & set(unused):
        raise KnowledgeReceiptError("knowledge_receipt_malformed", "used and unused references overlap")
    used_items = _objects(payload.get("used_references"), "used_references")
    if len(used_items) != len(required):
        raise KnowledgeReceiptError("required_knowledge_missing", "used reference count differs")
    for expected_id, raw in zip(required, used_items, strict=True):
        reference = selected.references.get(expected_id)
        if set(raw) != USED_FIELDS or reference is None or raw.get("id") != expected_id:
            raise KnowledgeReceiptError("knowledge_receipt_malformed", "used reference identity differs")
        expected = (reference.version, reference.ref, reference.sha256)
        if (raw.get("version"), raw.get("ref"), raw.get("sha256")) != expected:
            raise KnowledgeReceiptError("reference_hash_mismatch", expected_id)
        supported = _texts(raw.get("decisions_supported"), "decisions_supported", nonempty=True)
        if not set(supported).issubset(decisions):
            raise KnowledgeReceiptError("knowledge_receipt_malformed", "unsupported decision use")
    reported_at = _text(payload, "reported_at")
    _timestamp(reported_at)
    if payload.get("reported_by") != REPORTER or payload.get("attestation_scope") != ATTESTATION_SCOPE:
        raise KnowledgeReceiptError("knowledge_receipt_malformed", "unsupported reporter or attestation scope")
    receipt_id = _text(payload, "receipt_id")
    if receipt_id != receipt_identity(payload):
        raise KnowledgeReceiptError("knowledge_receipt_identity_mismatch", "receipt content was modified")
    return KnowledgeReceipt(
        receipt_id,
        context.context_id,
        role,
        context.task_type,
        required,
        context.specialist_skills,
        reported_at,
    )
