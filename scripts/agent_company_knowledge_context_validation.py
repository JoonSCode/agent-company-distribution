from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from agent_company_expertise_catalog import ExpertiseCatalog, load_expertise_catalog
from agent_company_expertise_resolver import (
    ExpertiseResolution,
    ExpertiseResolutionError,
    resolve_expertise,
)
from agent_company_role_schema import JsonValue

FORMAT: Final[str] = "agent-company.knowledge-context/v0.2"
ISSUER: Final[str] = "agent-company-expertise-resolver/v0.2"
ATTESTATION_SCOPE: Final[str] = "resolver_materialized_selection"
FIELDS: Final[frozenset[str]] = frozenset({
    "format", "context_id", "role", "task_type", "objective_sha256",
    "decision_questions", "registry_sha256", "manifest_sha256",
    "routing_sha256", "required_reference_ids", "specialist_skills",
    "selection", "materialized_references", "issued_by", "issued_at",
    "attestation_scope",
})
MATERIALIZED_FIELDS: Final[frozenset[str]] = frozenset(
    {"id", "version", "ref", "sha256"}
)


@dataclass(frozen=True, slots=True)
class KnowledgeContextError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class KnowledgeContext:
    context_id: str
    role: str
    task_type: str
    task_pack_id: str
    decision_questions: tuple[str, ...]
    required_reference_ids: tuple[str, ...]
    specialist_skills: tuple[str, ...]
    issued_at: str


def canonical(value: dict[str, JsonValue]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def context_identity(payload: dict[str, JsonValue]) -> str:
    body = {key: value for key, value in payload.items() if key != "context_id"}
    return hashlib.sha256(canonical(body)).hexdigest()


def _object(value: JsonValue | None, field: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise KnowledgeContextError("knowledge_context_malformed", f"{field} must be an object")
    return value


def _objects(value: JsonValue | None, field: str) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list):
        raise KnowledgeContextError("knowledge_context_malformed", f"{field} must be a list")
    return tuple(_object(item, f"{field}[{index}]") for index, item in enumerate(value))


def _text(values: dict[str, JsonValue], field: str) -> str:
    value = values.get(field)
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeContextError("knowledge_context_malformed", f"{field} must be text")
    return value


def _texts(
    value: JsonValue | None,
    field: str,
    *,
    nonempty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise KnowledgeContextError("knowledge_context_malformed", f"{field} must be a list")
    result = tuple(
        item
        for item in value
        if isinstance(item, str) and item.strip()
    )
    if len(result) != len(value) or (nonempty and not result) or len(result) != len(set(result)):
        raise KnowledgeContextError("knowledge_context_malformed", f"{field} is invalid")
    return result


def _timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KnowledgeContextError("knowledge_context_malformed", "issued_at is invalid") from exc
    if parsed.tzinfo is None:
        raise KnowledgeContextError("knowledge_context_malformed", "issued_at needs timezone")


def _expected_resolution(
    role: str,
    objective: str,
    payload: dict[str, JsonValue],
    catalog: ExpertiseCatalog,
) -> ExpertiseResolution:
    selection = _object(payload.get("selection"), "selection")
    basis = selection.get("classification_basis")
    hint = _text(payload, "task_type") if basis == "explicit_hint" else None
    try:
        return resolve_expertise(
            role,
            objective,
            task_hint=hint,
            catalog=catalog,
        )
    except ExpertiseResolutionError as exc:
        raise KnowledgeContextError(exc.code, exc.detail) from exc


def validate_knowledge_context(
    role: str,
    objective: str,
    value: JsonValue | None,
    catalog: ExpertiseCatalog | None = None,
) -> KnowledgeContext:
    payload = _object(value, "knowledge_context_binding")
    if set(payload) != FIELDS or payload.get("format") != FORMAT:
        raise KnowledgeContextError("knowledge_context_malformed", "unexpected context shape or format")
    selected = catalog or load_expertise_catalog()
    if role not in selected.roles or payload.get("role") != role:
        raise KnowledgeContextError("knowledge_context_role_mismatch", role)
    if payload.get("objective_sha256") != digest_text(objective):
        raise KnowledgeContextError("knowledge_context_objective_mismatch", "context has another objective")
    if payload.get("registry_sha256") != selected.registry_sha256:
        raise KnowledgeContextError("stale_expertise_registry", "context registry digest is stale")
    if payload.get("manifest_sha256") != selected.manifest_sha256:
        raise KnowledgeContextError("stale_reference_manifest", "context manifest digest is stale")
    resolution = _expected_resolution(role, objective, payload, selected)
    if payload.get("routing_sha256") != resolution.routing_sha256:
        raise KnowledgeContextError("stale_expertise_routing", "context routing digest is stale")
    task_type = _text(payload, "task_type")
    decisions = _texts(payload.get("decision_questions"), "decision_questions", nonempty=True)
    required = _texts(payload.get("required_reference_ids"), "required_reference_ids", nonempty=True)
    specialists = _texts(payload.get("specialist_skills"), "specialist_skills")
    expected = (
        resolution.task_type,
        resolution.decision_questions,
        resolution.required_reference_ids,
        resolution.specialist_skills,
        resolution.selection_payload(),
    )
    actual = (task_type, decisions, required, specialists, payload.get("selection"))
    if actual != expected:
        raise KnowledgeContextError("expertise_selection_mismatch", "context differs from resolver")
    materialized = _objects(payload.get("materialized_references"), "materialized_references")
    if len(materialized) != len(required):
        raise KnowledgeContextError("required_knowledge_missing", "materialized count differs")
    for expected_id, raw in zip(required, materialized, strict=True):
        reference = selected.references.get(expected_id)
        if set(raw) != MATERIALIZED_FIELDS or reference is None or reference.status != "active":
            raise KnowledgeContextError("required_reference_unavailable", expected_id)
        expected_ref = (reference.id, reference.version, reference.ref, reference.sha256)
        actual_ref = (raw.get("id"), raw.get("version"), raw.get("ref"), raw.get("sha256"))
        if actual_ref != expected_ref:
            raise KnowledgeContextError("reference_hash_mismatch", expected_id)
    issued_at = _text(payload, "issued_at")
    _timestamp(issued_at)
    if payload.get("issued_by") != ISSUER or payload.get("attestation_scope") != ATTESTATION_SCOPE:
        raise KnowledgeContextError("knowledge_context_malformed", "unsupported issuer or scope")
    context_id = _text(payload, "context_id")
    if context_id != context_identity(payload):
        raise KnowledgeContextError("knowledge_context_identity_mismatch", "context changed")
    return KnowledgeContext(
        context_id,
        role,
        task_type,
        resolution.task_pack_id,
        decisions,
        required,
        specialists,
        issued_at,
    )
