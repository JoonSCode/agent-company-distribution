from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import hashlib
import json
from dataclasses import dataclass
from typing import Final

from agent_company_evidence_digest import (
    EvidenceDigestError,
    StableJsonEvidence,
    read_stable_json_evidence,
    require_matching_evidence_digest,
    require_unchanged_evidence,
)
from agent_company_job_policy import PolicyError, object_list, text
from agent_company_knowledge_verification_provenance import (
    ArtifactByteBinding,
    KnowledgeByteProvenance,
    WorkerArtifactByteBinding,
)
from agent_company_report_byte_authorization import (
    VerificationByteChain,
    authorize_current_verification,
    runtime_provenance_input_refs,
)

MAX_HANDOFF_BYTES: Final[int] = 32_768
ORDINARY_ROLES: Final[frozenset[str]] = frozenset({
    "founder",
    "planning",
    "marketing",
    "design",
    "development",
    "qa-release",
})


@dataclass(frozen=True, slots=True)
class ReportRuntimeEvidenceSources:
    delegation_input: StableJsonEvidence
    job: StableJsonEvidence
    core_run: StableJsonEvidence


@dataclass(frozen=True, slots=True)
class ReportRuntimeByteCapture:
    provenance: KnowledgeByteProvenance
    sources: tuple[StableJsonEvidence, ...]


def capture_report_runtime_provenance(
    sources: ReportRuntimeEvidenceSources,
) -> ReportRuntimeByteCapture:
    captured: list[StableJsonEvidence] = [
        sources.delegation_input,
        sources.job,
        sources.core_run,
    ]
    worker_artifacts: list[WorkerArtifactByteBinding] = []
    worker_ids: set[str] = set()
    receipt_ids: set[str] = set()
    ordinary_worker_ids: set[str] = set()
    for assignment in object_list(
        sources.delegation_input.payload.get("assignments"),
        "delegation assignments",
    ):
        worker_id = text(assignment.get("worker_id"), "assignment worker_id")
        role = text(assignment.get("role"), "assignment role")
        if role in ORDINARY_ROLES:
            ordinary_worker_ids.add(worker_id)
        elif role != "specialist":
            raise PolicyError(f"unsupported assignment role for {worker_id}")
    receipts = object_list(
        sources.core_run.payload.get("receipts"),
        "Core receipts",
    )
    for receipt in receipts:
        if (
            receipt.get("receipt_type") != "worker_terminal"
            or receipt.get("terminal_status") != "completed"
        ):
            continue
        worker_id = text(receipt.get("worker_id"), "terminal worker_id")
        if worker_id not in ordinary_worker_ids:
            continue
        receipt_id = text(receipt.get("receipt_id"), "terminal receipt_id")
        if worker_id in worker_ids or receipt_id in receipt_ids:
            raise PolicyError("Core terminal byte provenance is duplicated")
        worker_ids.add(worker_id)
        receipt_ids.add(receipt_id)
        output_ref = text(
            receipt.get("worker_output_ref"),
            "terminal worker_output_ref",
        )
        try:
            output = read_stable_json_evidence(
                output_ref,
                sources.core_run.path.parent,
                MAX_HANDOFF_BYTES,
            )
            require_matching_evidence_digest(
                output,
                text(
                    receipt.get("worker_output_sha256"),
                    "terminal worker_output_sha256",
                ),
            )
        except EvidenceDigestError as exc:
            raise PolicyError(
                f"invalid worker output byte provenance for {worker_id}: {exc}",
            ) from exc
        captured.append(output)
        terminal_sha256 = hashlib.sha256(json.dumps(
            receipt,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()).hexdigest()
        worker_artifacts.append(WorkerArtifactByteBinding(
            worker_id,
            str(output.path),
            str(output.sha256),
            receipt_id,
            terminal_sha256,
        ))
    provenance = KnowledgeByteProvenance(
        ArtifactByteBinding(
            str(sources.delegation_input.path),
            str(sources.delegation_input.sha256),
        ),
        ArtifactByteBinding(
            str(sources.job.path),
            str(sources.job.sha256),
        ),
        ArtifactByteBinding(
            str(sources.core_run.path),
            str(sources.core_run.sha256),
        ),
        tuple(worker_artifacts),
    )
    return ReportRuntimeByteCapture(provenance, tuple(captured))


def require_unchanged_runtime_provenance(
    capture: ReportRuntimeByteCapture,
) -> None:
    try:
        for source in capture.sources:
            require_unchanged_evidence(source)
    except EvidenceDigestError as exc:
        raise PolicyError(f"report runtime byte provenance changed: {exc}") from exc


__all__ = [
    "ReportRuntimeByteCapture",
    "ReportRuntimeEvidenceSources",
    "VerificationByteChain",
    "authorize_current_verification",
    "capture_report_runtime_provenance",
    "require_unchanged_runtime_provenance",
    "runtime_provenance_input_refs",
]
