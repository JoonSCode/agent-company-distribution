from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import os
from dataclasses import dataclass
from pathlib import Path

from agent_company_deps import JsonValue
from agent_company_job_policy import PolicyError, object_list, string_list, text
from agent_company_knowledge_verification import (
    KnowledgeVerificationBinding,
    TrustedVerificationAuthority,
)
from agent_company_knowledge_verification_provenance import (
    KnowledgeByteProvenance,
)
from agent_company_report_byte_provenance import (
    VerificationByteChain,
    authorize_current_verification,
)
from agent_company_report_status import TerminalStatus, enum_value
from agent_company_report_verification_artifact import (
    require_unchanged_verification_artifacts,
)
from agent_company_report_verification_projection import (
    project_verification_evidence,
)


@dataclass(frozen=True, slots=True)
class VerificationBindings:
    job_ref: str
    core_run_ref: str
    verification_run_ref: str | None
    core_run: dict[str, JsonValue]
    terminals: dict[str, dict[str, JsonValue]]
    assignments: dict[str, dict[str, JsonValue]]
    external_action_ledger_ref: str | None
    external_action_ledger_sha256: str | None
    runtime_byte_provenance: KnowledgeByteProvenance | None = None


@dataclass(frozen=True, slots=True)
class VerificationEvidence:
    refs: list[str]
    external_actions_bound: bool
    knowledge_verified: dict[str, KnowledgeVerificationBinding]
    authorizes_verified_projection: bool = False


def _canonical_ref(value: str) -> str:
    return (
        value
        if "://" in value
        else os.path.abspath(Path(value).expanduser())
    )


def _trusted_authority(bindings: VerificationBindings) -> TrustedVerificationAuthority:
    if bindings.verification_run_ref is None:
        raise PolicyError("completed verification requires a local verification run ref")
    issuer_ref = _canonical_ref(bindings.verification_run_ref)
    qa_refs = frozenset(
        text(receipt.get("backend_worker_ref"), "qa-release verifier ref")
        for worker_id, receipt in bindings.terminals.items()
        if (
            bindings.assignments.get(worker_id, {}).get("role") == "qa-release"
            and receipt.get("terminal_status") == TerminalStatus.COMPLETED.value
        )
    )
    return TrustedVerificationAuthority(
        issuer_role="seungjeongwon",
        issuer_ref=issuer_ref,
        reviewer_refs={
            "seungjeongwon": frozenset({issuer_ref}),
            "company-lead": frozenset({issuer_ref}),
            "qa-release": frozenset({issuer_ref, *qa_refs}),
        },
    )


def verification_evidence(
    verification_run: dict[str, JsonValue] | None,
    bindings: VerificationBindings,
) -> VerificationEvidence:
    if verification_run is None:
        return VerificationEvidence([], False, {})
    if verification_run.get("format") != "sejong.seungjeongwon-run/v0.1-draft":
        raise PolicyError("verification run has an unexpected format")
    if verification_run.get("status") != "completed":
        return VerificationEvidence([], False, {})
    provenance = verification_run.get("provenance")
    if not isinstance(provenance, dict):
        raise PolicyError("completed verification provenance must be an object")
    if provenance.get("created_by") != "seungjeongwon":
        raise PolicyError("completed verification was not issued by Seungjeongwon")
    input_refs = {
        _canonical_ref(text(ref, "verification input_ref"))
        for ref in string_list(provenance.get("input_refs"), "verification input_refs")
    }
    required_refs = {
        _canonical_ref(text(bindings.job_ref, "job_ref")),
        _canonical_ref(text(bindings.core_run_ref, "core_run_ref")),
    }
    if not required_refs.issubset(input_refs):
        raise PolicyError("completed verification input_refs do not bind the job and Core run")
    verification_refs = {
        _canonical_ref(text(ref, "verification provenance ref"))
        for ref in string_list(
            provenance.get("verification_refs"),
            "verification provenance refs",
        )
    }
    delegation_run_refs = {
        _canonical_ref(text(ref, "verification delegation_run_ref"))
        for ref in string_list(
            verification_run.get("delegation_run_refs"),
            "verification delegation_run_refs",
        )
    }
    if _canonical_ref(bindings.core_run_ref) not in delegation_run_refs:
        raise PolicyError("completed verification does not bind its fan-ins to the Core run")
    evidence = string_list(
        verification_run.get("verification_evidence"),
        "verification_evidence",
    )
    fan_in_refs = string_list(
        verification_run.get("delegation_fan_in_refs"),
        "delegation_fan_in_refs",
    )
    waves = object_list(bindings.core_run.get("waves"), "Core waves")
    if not evidence or not waves or len(fan_in_refs) != len(waves):
        raise PolicyError("completed verification lacks evidence or worker coverage")
    projected, knowledge_verified, knowledge_artifacts, captures = (
        project_verification_evidence(
        evidence,
        bindings.assignments,
        bindings.terminals,
        input_refs,
        verification_refs,
        _trusted_authority(bindings),
        )
    )
    covered_workers = {
        worker
        for wave in waves
        for worker in string_list(wave.get("required_worker_ids"), "wave required_worker_ids")
    }
    completed = {
        worker
        for worker, receipt in bindings.terminals.items()
        if enum_value(
            TerminalStatus,
            receipt.get("terminal_status"),
            "terminal_status",
        ) is TerminalStatus.COMPLETED
    }
    if covered_workers != set(bindings.assignments) or completed != set(bindings.assignments):
        raise PolicyError("completed verification lacks completed receipt coverage")
    authorizes_verified_projection = False
    if bindings.runtime_byte_provenance is not None:
        authorizes_verified_projection = authorize_current_verification(
            VerificationByteChain(
                runtime=bindings.runtime_byte_provenance,
                expected_worker_ids=frozenset(bindings.assignments),
                verified_worker_ids=frozenset(knowledge_verified),
                knowledge_provenances=tuple(
                    item.byte_provenance
                    for item in knowledge_verified.values()
                ),
                knowledge_artifacts=knowledge_artifacts,
                input_refs=frozenset(input_refs),
                verification_refs=frozenset(verification_refs),
            ),
        )
    ledger_bound = (
        bindings.external_action_ledger_ref is not None
        and _canonical_ref(bindings.external_action_ledger_ref) in input_refs
        and bindings.external_action_ledger_sha256 is not None
        and (
            "sha256://external-action-ledger/"
            f"{bindings.external_action_ledger_sha256}"
        ) in input_refs
    )
    require_unchanged_verification_artifacts(captures)
    return VerificationEvidence(
        projected,
        ledger_bound,
        knowledge_verified,
        authorizes_verified_projection,
    )
