from __future__ import annotations

from datetime import datetime, timezone

from agent_company_expertise_catalog import (
    load_expertise_catalog,
)
from agent_company_expertise_models import ExpertiseCatalog, ReferenceSpec
from agent_company_knowledge_context import issue_context, issue_default_context
from agent_company_knowledge_receipt_validation import (
    ATTESTATION_SCOPE,
    FORMAT,
    REPORTER,
    KnowledgeReceipt,
    KnowledgeReceiptError,
    digest_text,
    receipt_identity,
    validate_knowledge_receipt,
    validated_context,
)
from agent_company_role_schema import JsonValue


def _used_reference(reference: ReferenceSpec, decisions: tuple[str, ...]) -> dict[str, JsonValue]:
    return {
        "id": reference.id,
        "version": reference.version,
        "ref": reference.ref,
        "sha256": reference.sha256,
        "decisions_supported": list(decisions),
    }


def build_receipt(
    role: str,
    objective: str,
    task_type: str,
    required_reference_ids: tuple[str, ...],
    decision_questions: tuple[str, ...],
    specialist_skills: tuple[str, ...] = (),
    unused_reference_ids: tuple[str, ...] = (),
    *,
    context: JsonValue | None = None,
    catalog: ExpertiseCatalog | None = None,
    now: str | None = None,
) -> dict[str, JsonValue]:
    selected = catalog or load_expertise_catalog()
    issued = context or issue_context(
        role,
        objective,
        task_type,
        required_reference_ids,
        decision_questions,
        specialist_skills,
        catalog=selected,
    )
    raw_context, parsed_context = validated_context(role, objective, issued, selected)
    requested = (
        task_type,
        required_reference_ids,
        decision_questions,
        specialist_skills,
    )
    bound = (
        parsed_context.task_type,
        parsed_context.required_reference_ids,
        parsed_context.decision_questions,
        parsed_context.specialist_skills,
    )
    if requested != bound:
        raise KnowledgeReceiptError("knowledge_context_mismatch", "receipt request differs from issued context")
    if set(required_reference_ids) & set(unused_reference_ids):
        raise KnowledgeReceiptError("knowledge_receipt_malformed", "used and unused references overlap")
    used: list[JsonValue] = []
    for reference_id in required_reference_ids:
        reference = selected.references.get(reference_id)
        if reference is None or reference.status != "active":
            raise KnowledgeReceiptError("required_reference_unavailable", reference_id)
        used.append(_used_reference(reference, decision_questions))
    reported_at = now or datetime.now(timezone.utc).replace(
        microsecond=0,
    ).isoformat().replace("+00:00", "Z")
    payload: dict[str, JsonValue] = {
        "format": FORMAT,
        "receipt_id": "",
        "context_id": parsed_context.context_id,
        "role": role,
        "task_type": task_type,
        "objective_sha256": digest_text(objective),
        "decision_questions": list(decision_questions),
        "registry_sha256": raw_context["registry_sha256"],
        "manifest_sha256": raw_context["manifest_sha256"],
        "required_reference_ids": list(required_reference_ids),
        "used_references": used,
        "unused_reference_ids": list(unused_reference_ids),
        "specialist_skills": list(specialist_skills),
        "reported_by": REPORTER,
        "reported_at": reported_at,
        "attestation_scope": ATTESTATION_SCOPE,
    }
    payload["receipt_id"] = receipt_identity(payload)
    validate_knowledge_receipt(
        role,
        objective,
        payload,
        expected_context=raw_context,
        catalog=selected,
    )
    return payload


def build_default_receipt(
    role: str,
    objective: str,
    catalog: ExpertiseCatalog | None = None,
    now: str | None = None,
    *,
    context: JsonValue | None = None,
) -> dict[str, JsonValue]:
    selected = catalog or load_expertise_catalog()
    issued = context or issue_default_context(role, objective, selected)
    _, parsed = validated_context(role, objective, issued, selected)
    return build_receipt(
        role,
        objective,
        parsed.task_type,
        parsed.required_reference_ids,
        parsed.decision_questions,
        parsed.specialist_skills,
        context=issued,
        catalog=selected,
        now=now,
    )


__all__ = [
    "KnowledgeReceipt", "KnowledgeReceiptError", "build_default_receipt",
    "build_receipt", "issue_default_context", "validate_knowledge_receipt",
]
