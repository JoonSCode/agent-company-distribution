from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import os
from dataclasses import dataclass

from agent_company_job_policy import PolicyError
from agent_company_knowledge_verification_provenance import (
    ArtifactByteBinding,
    KnowledgeByteProvenance,
    WorkerArtifactByteBinding,
)


@dataclass(frozen=True, slots=True)
class VerificationByteChain:
    runtime: KnowledgeByteProvenance
    expected_worker_ids: frozenset[str]
    verified_worker_ids: frozenset[str]
    knowledge_provenances: tuple[KnowledgeByteProvenance | None, ...]
    knowledge_artifacts: tuple[ArtifactByteBinding, ...]
    input_refs: frozenset[str]
    verification_refs: frozenset[str]


def _local_ref(value: str) -> str:
    return os.path.abspath(os.path.normpath(os.path.expanduser(value)))


def _artifact(value: ArtifactByteBinding) -> ArtifactByteBinding:
    return ArtifactByteBinding(_local_ref(value.ref), value.sha256)


def _worker(value: WorkerArtifactByteBinding) -> WorkerArtifactByteBinding:
    return WorkerArtifactByteBinding(
        value.worker_id,
        _local_ref(value.handoff_ref),
        value.handoff_sha256,
        value.terminal_receipt_id,
        value.terminal_receipt_sha256,
    )


def _provenance(value: KnowledgeByteProvenance) -> KnowledgeByteProvenance:
    return KnowledgeByteProvenance(
        _artifact(value.delegation_input),
        _artifact(value.job),
        _artifact(value.core_run),
        tuple(_worker(item) for item in value.worker_artifacts),
    )


def _runtime_refs(value: KnowledgeByteProvenance) -> frozenset[str]:
    refs = {
        value.delegation_input.ref,
        value.job.ref,
        value.core_run.ref,
        f"sha256://delegation-input/{value.delegation_input.sha256}",
        f"sha256://job/{value.job.sha256}",
        f"sha256://core-run/{value.core_run.sha256}",
    }
    for worker in value.worker_artifacts:
        refs.update({
            worker.handoff_ref,
            f"sha256://worker-handoff/{worker.handoff_sha256}",
            f"sha256://terminal-receipt/{worker.terminal_receipt_sha256}",
        })
    return frozenset(refs)


def _refs(values: frozenset[str]) -> frozenset[str]:
    return frozenset(
        value if "://" in value else _local_ref(value)
        for value in values
    )


def runtime_provenance_input_refs(
    value: KnowledgeByteProvenance,
) -> tuple[str, ...]:
    return tuple(sorted(_runtime_refs(_provenance(value))))


def authorize_current_verification(chain: VerificationByteChain) -> bool:
    if not chain.knowledge_provenances or any(
        item is None
        for item in chain.knowledge_provenances
    ):
        return False
    runtime = _provenance(chain.runtime)
    actual_workers = frozenset(
        item.worker_id
        for item in runtime.worker_artifacts
    )
    if (
        actual_workers != chain.expected_worker_ids
        or chain.verified_worker_ids != chain.expected_worker_ids
    ):
        return False
    for recorded in chain.knowledge_provenances:
        if recorded is None:
            return False
        if _provenance(recorded) != runtime:
            raise PolicyError(
                "knowledge verification byte provenance differs from runtime artifacts",
            )
    input_refs = _refs(chain.input_refs)
    required = _runtime_refs(runtime)
    if not required.issubset(input_refs):
        raise PolicyError(
            "verification input_refs do not bind current runtime byte provenance",
        )
    verification_refs = _refs(chain.verification_refs)
    if not chain.knowledge_artifacts:
        return False
    for artifact in chain.knowledge_artifacts:
        normalized = _artifact(artifact)
        if (
            normalized.ref not in verification_refs
            or f"sha256://verification/{normalized.sha256}" not in input_refs
        ):
            raise PolicyError(
                "knowledge verification artifact is not byte-bound to its trusted run",
            )
    return True


__all__ = [
    "VerificationByteChain",
    "authorize_current_verification",
    "runtime_provenance_input_refs",
]
