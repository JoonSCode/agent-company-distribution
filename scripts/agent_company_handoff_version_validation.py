from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
from typing import Final

from agent_company_deps import JsonValue
from agent_company_handoff_errors import HandoffError
from agent_company_handoff_role_evidence import (
    RoleEvidenceError,
    validate_role_evidence,
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
from agent_company_qa_handoff import QaHandoffError, parse_qa_verification

EXECUTION_HANDOFF_VERSION: Final = "agent-company.execution-handoff/v0.3"
QA_EXECUTION_HANDOFF_VERSION: Final = "agent-company.execution-handoff/v0.4"
LEGACY_EXECUTION_HANDOFF_VERSION: Final = "agent-company.execution-handoff/v0.2"
LEGACY_V02_CONTRACT_ROLES: Final = frozenset(
    {"marketing", "design", "development", "qa-release"}
)


def _current_knowledge(
    role: str,
    raw_context: JsonValue | None,
    raw_receipt: JsonValue | None,
    objective: str,
) -> KnowledgeContext:
    if raw_context is None:
        raise HandoffError(
            "knowledge_context_required",
            f"{role} requires a parent-issued knowledge context",
        )
    try:
        context = validate_knowledge_context(role, objective, raw_context)
    except KnowledgeContextError as exc:
        raise HandoffError(exc.code, f"knowledge context: {exc.detail}") from exc
    if raw_receipt is None:
        raise HandoffError(
            "knowledge_receipt_required",
            f"{role} requires a Knowledge Usage Receipt",
        )
    try:
        validate_knowledge_receipt(
            role,
            objective,
            raw_receipt,
            expected_context=raw_context,
        )
    except KnowledgeReceiptError as exc:
        raise HandoffError(exc.code, f"knowledge receipt: {exc.detail}") from exc
    return context


def _contract(role: str, raw_binding: JsonValue | None) -> None:
    reference: JsonValue | None = None
    digest: JsonValue | None = None
    if raw_binding is not None:
        if not isinstance(raw_binding, dict):
            raise HandoffError(
                "malformed_input",
                "operating_contract_binding must be an object",
            )
        if set(raw_binding) != {"ref", "sha256"}:
            raise HandoffError(
                "malformed_input",
                "invalid operating_contract_binding",
            )
        reference, digest = raw_binding.get("ref"), raw_binding.get("sha256")
    try:
        bind_operating_contract(role, reference, digest)
    except OperatingContractError as exc:
        raise HandoffError(exc.code, f"operating contract: {exc.detail}") from exc


def validate_versioned_handoff(
    payload: dict[str, JsonValue],
    role: str,
    objective: str,
    *,
    expected_role_evidence_context_binding: JsonValue | None = None,
) -> None:
    raw_binding = payload.get("operating_contract_binding")
    raw_context = payload.get("knowledge_context_binding")
    raw_receipt = payload.get("knowledge_usage_receipt")
    raw_qa = payload.get("qa_verification")
    raw_role_evidence = payload.get("role_evidence")
    execution_version = payload.get("execution_handoff_version")
    if execution_version is None:
        if any(
            item is not None
            for item in (
                raw_binding,
                raw_context,
                raw_receipt,
                raw_qa,
                raw_role_evidence,
            )
        ):
            raise HandoffError(
                "malformed_input",
                "legacy handoff carries versioned evidence",
            )
        return
    if execution_version == LEGACY_EXECUTION_HANDOFF_VERSION:
        if any(
            item is not None
            for item in (raw_context, raw_receipt, raw_qa, raw_role_evidence)
        ):
            raise HandoffError(
                "malformed_input",
                "legacy v0.2 cannot carry v0.3 evidence",
            )
        if role not in LEGACY_V02_CONTRACT_ROLES:
            if raw_binding is not None:
                raise HandoffError(
                    "malformed_input",
                    "historical role cannot carry a contract",
                )
            return
    elif execution_version not in {
        EXECUTION_HANDOFF_VERSION,
        QA_EXECUTION_HANDOFF_VERSION,
    }:
        raise HandoffError(
            "malformed_input",
            "unsupported execution_handoff_version",
        )
    if execution_version == QA_EXECUTION_HANDOFF_VERSION and role != "qa-release":
        raise HandoffError("malformed_input", "v0.4 is reserved for qa-release")
    _contract(role, raw_binding)
    if execution_version not in {
        EXECUTION_HANDOFF_VERSION,
        QA_EXECUTION_HANDOFF_VERSION,
    }:
        return
    context = _current_knowledge(
        role,
        raw_context,
        raw_receipt,
        objective,
    )
    if role == "qa-release":
        try:
            parse_qa_verification(raw_qa, execution_version)
        except QaHandoffError as exc:
            raise HandoffError("malformed_input", str(exc)) from exc
    elif raw_qa is not None:
        raise HandoffError(
            "malformed_input",
            "qa_verification is reserved for qa-release",
        )
    try:
        validate_role_evidence(
            role=role,
            context=context,
            value=raw_role_evidence,
            expected_context_binding=expected_role_evidence_context_binding,
            receipt_ingress=True,
        )
    except RoleEvidenceError as exc:
        raise HandoffError("malformed_input", str(exc)) from exc
