from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
from dataclasses import dataclass

from agent_company_deps import JsonValue
from agent_company_handoff import (
    EXECUTION_HANDOFF_VERSION,
    LEGACY_EXECUTION_HANDOFF_VERSION,
    QA_EXECUTION_HANDOFF_VERSION,
)
from agent_company_knowledge_context import (
    KnowledgeContext,
    KnowledgeContextError,
    validate_knowledge_context,
)
from agent_company_knowledge_receipt import (
    KnowledgeReceiptError,
    validate_knowledge_receipt,
)
from agent_company_operating_contracts import (
    OperatingContractError,
    bind_operating_contract,
)


@dataclass(frozen=True, slots=True)
class HandoffKnowledgeError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


def _object(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise HandoffKnowledgeError(f"{label} must be an object")
    return value


def _text(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HandoffKnowledgeError(f"{label} must be a non-empty string")
    return value


def validate_execution_knowledge(
    assignment: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> tuple[
    str | None,
    str | None,
    tuple[str, ...],
    KnowledgeContext | None,
]:
    role = _text(assignment.get("role"), "assignment role")
    raw_binding = payload.get("operating_contract_binding")
    raw_context = payload.get("knowledge_context_binding")
    raw_receipt = payload.get("knowledge_usage_receipt")
    execution_version = payload.get("execution_handoff_version")
    if execution_version is None:
        if raw_binding is not None:
            raise HandoffKnowledgeError(
                "legacy worker handoff cannot carry an unversioned operating contract"
            )
        if raw_context is not None:
            raise HandoffKnowledgeError(
                "legacy worker handoff cannot carry an unversioned knowledge context"
            )
        if raw_receipt is not None:
            raise HandoffKnowledgeError(
                "legacy worker handoff cannot carry an unversioned knowledge receipt"
            )
        return None, None, (), None
    if execution_version == LEGACY_EXECUTION_HANDOFF_VERSION:
        raise HandoffKnowledgeError(
            "legacy v0.2 worker handoff is readable but lacks parent-issued knowledge evidence"
        )
    expected_version = (
        QA_EXECUTION_HANDOFF_VERSION
        if role == "qa-release"
        else EXECUTION_HANDOFF_VERSION
    )
    if role == "qa-release" and execution_version == EXECUTION_HANDOFF_VERSION:
        raise HandoffKnowledgeError(
            "qa-release v0.3 worker handoff is historical-only and cannot authorize current completion"
        )
    if execution_version != expected_version:
        raise HandoffKnowledgeError("worker handoff has unsupported execution_handoff_version")
    reference: JsonValue | None = None
    digest: JsonValue | None = None
    if raw_binding is not None:
        binding = _object(raw_binding, "worker handoff operating_contract_binding")
        if set(binding) != {"ref", "sha256"}:
            raise HandoffKnowledgeError(
                "worker handoff operating contract must contain only ref and sha256"
            )
        reference, digest = binding.get("ref"), binding.get("sha256")
    try:
        bind_operating_contract(role, reference, digest)
    except OperatingContractError as exc:
        raise HandoffKnowledgeError(
            f"worker handoff operating contract is invalid: {exc}"
        ) from exc
    expected_context = assignment.get("knowledge_context_binding")
    if expected_context is None:
        raise HandoffKnowledgeError(
            "assignment knowledge context is required for current worker evidence"
        )
    if raw_context != expected_context:
        raise HandoffKnowledgeError(
            "worker handoff knowledge context differs from the parent assignment"
        )
    objective = _text(payload.get("objective"), "worker handoff objective")
    try:
        parsed_context = validate_knowledge_context(role, objective, raw_context)
    except KnowledgeContextError as exc:
        raise HandoffKnowledgeError(
            f"worker handoff knowledge context is invalid: {exc}"
        ) from exc
    if raw_receipt is None:
        raise HandoffKnowledgeError(
            "knowledge_receipt_required: worker handoff requires a Knowledge Usage Receipt"
        )
    try:
        parsed_receipt = validate_knowledge_receipt(
            role,
            objective,
            raw_receipt,
            expected_context=expected_context,
        )
    except KnowledgeReceiptError as exc:
        raise HandoffKnowledgeError(
            f"worker handoff knowledge receipt is invalid: {exc}"
        ) from exc
    return (
        parsed_context.context_id,
        parsed_receipt.receipt_id,
        parsed_receipt.required_reference_ids,
        parsed_context,
    )
