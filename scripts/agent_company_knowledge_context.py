from __future__ import annotations

from datetime import datetime, timezone

from agent_company_expertise_catalog import (
    load_expertise_catalog,
)
from agent_company_expertise_models import ExpertiseCatalog, ReferenceSpec
from agent_company_expertise_resolver import (
    ExpertiseResolution,
    ExpertiseResolutionError,
    resolve_expertise,
)
from agent_company_expertise_selection import (
    ExpertiseSelectionError,
    validate_specialist_selection,
)
from agent_company_knowledge_context_validation import (
    ATTESTATION_SCOPE,
    FORMAT,
    ISSUER,
    KnowledgeContext,
    KnowledgeContextError,
    context_identity,
    digest_text,
    validate_knowledge_context,
)
from agent_company_role_schema import JsonValue


def _materialized(reference: ReferenceSpec) -> dict[str, JsonValue]:
    return {
        "id": reference.id,
        "version": reference.version,
        "ref": reference.ref,
        "sha256": reference.sha256,
    }


def _issue_resolution(
    role: str,
    objective: str,
    resolution: ExpertiseResolution,
    catalog: ExpertiseCatalog,
    now: str | None,
) -> dict[str, JsonValue]:
    materialized: list[JsonValue] = []
    for reference_id in resolution.required_reference_ids:
        reference = catalog.references.get(reference_id)
        if reference is None or reference.status != "active":
            raise KnowledgeContextError("required_reference_unavailable", reference_id)
        materialized.append(_materialized(reference))
    issued_at = now or datetime.now(timezone.utc).replace(
        microsecond=0,
    ).isoformat().replace("+00:00", "Z")
    payload: dict[str, JsonValue] = {
        "format": FORMAT,
        "context_id": "",
        "role": role,
        "task_type": resolution.task_type,
        "objective_sha256": digest_text(objective),
        "decision_questions": list(resolution.decision_questions),
        "registry_sha256": catalog.registry_sha256,
        "manifest_sha256": catalog.manifest_sha256,
        "routing_sha256": resolution.routing_sha256,
        "required_reference_ids": list(resolution.required_reference_ids),
        "specialist_skills": list(resolution.specialist_skills),
        "selection": resolution.selection_payload(),
        "materialized_references": materialized,
        "issued_by": ISSUER,
        "issued_at": issued_at,
        "attestation_scope": ATTESTATION_SCOPE,
    }
    payload["context_id"] = context_identity(payload)
    validate_knowledge_context(role, objective, payload, catalog)
    return payload


def issue_context(
    role: str,
    objective: str,
    task_type: str,
    required_reference_ids: tuple[str, ...],
    decision_questions: tuple[str, ...],
    specialist_skills: tuple[str, ...] = (),
    *,
    catalog: ExpertiseCatalog | None = None,
    now: str | None = None,
) -> dict[str, JsonValue]:
    selected = catalog or load_expertise_catalog()
    role_spec = selected.roles.get(role)
    if role_spec is None or not objective.strip() or not task_type.strip():
        raise KnowledgeContextError(
            "knowledge_context_malformed",
            "role, objective, and task type are required",
        )
    try:
        validate_specialist_selection(
            role_spec,
            task_type,
            specialist_skills,
            selected.default_specialist_limit,
        )
        resolution = resolve_expertise(
            role,
            objective,
            task_hint=task_type,
            catalog=selected,
        )
    except (ExpertiseSelectionError, ExpertiseResolutionError) as exc:
        raise KnowledgeContextError(exc.code, exc.detail) from exc
    requested = (
        required_reference_ids,
        decision_questions,
        specialist_skills,
    )
    expected = (
        resolution.required_reference_ids,
        resolution.decision_questions,
        resolution.specialist_skills,
    )
    if requested != expected:
        raise KnowledgeContextError(
            "expertise_selection_mismatch",
            "manual context differs from deterministic resolver output",
        )
    return _issue_resolution(role, objective, resolution, selected, now)


def issue_default_context(
    role: str,
    objective: str,
    catalog: ExpertiseCatalog | None = None,
    now: str | None = None,
) -> dict[str, JsonValue]:
    selected = catalog or load_expertise_catalog()
    try:
        resolution = resolve_expertise(role, objective, catalog=selected)
    except ExpertiseResolutionError as exc:
        raise KnowledgeContextError(exc.code, exc.detail) from exc
    return _issue_resolution(role, objective, resolution, selected, now)


__all__ = [
    "KnowledgeContext",
    "KnowledgeContextError",
    "issue_context",
    "issue_default_context",
    "validate_knowledge_context",
]
