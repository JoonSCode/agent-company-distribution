from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
from agent_company_deps import JsonValue
from agent_company_job_policy import PolicyError
from agent_company_knowledge_verification import (
    FORMAT as KNOWLEDGE_VERIFICATION_FORMAT,
)
from agent_company_knowledge_verification import (
    LEGACY_FORMAT as LEGACY_KNOWLEDGE_VERIFICATION_FORMAT,
)
from agent_company_knowledge_verification import (
    KnowledgeVerificationBinding,
    KnowledgeVerificationError,
    TrustedVerificationAuthority,
    validate_knowledge_verification,
)
from agent_company_knowledge_verification_provenance import ArtifactByteBinding
from agent_company_report_verification_artifact import (
    StableJsonEvidence,
    capture_verification_artifact,
)


def _knowledge_bindings(
    parsed: dict[str, JsonValue],
    assignments: dict[str, dict[str, JsonValue]],
    terminals: dict[str, dict[str, JsonValue]],
    authority: TrustedVerificationAuthority,
) -> dict[str, KnowledgeVerificationBinding]:
    artifact_format = parsed.get("format")
    if artifact_format in {
        KNOWLEDGE_VERIFICATION_FORMAT,
        LEGACY_KNOWLEDGE_VERIFICATION_FORMAT,
    }:
        try:
            return validate_knowledge_verification(
                parsed,
                assignments,
                terminals,
                authority,
            )
        except KnowledgeVerificationError as exc:
            raise PolicyError(f"invalid knowledge verification: {exc}") from exc
    if (
        isinstance(artifact_format, str)
        and artifact_format.startswith("agent-company.knowledge-use-verification/")
    ):
        raise PolicyError("knowledge verification has an unsupported format")
    return {}


def project_verification_evidence(
    evidence: list[str],
    assignments: dict[str, dict[str, JsonValue]],
    terminals: dict[str, dict[str, JsonValue]],
    input_refs: set[str],
    verification_refs: set[str],
    authority: TrustedVerificationAuthority,
) -> tuple[
    list[str],
    dict[str, KnowledgeVerificationBinding],
    tuple[ArtifactByteBinding, ...],
    tuple[StableJsonEvidence, ...],
]:
    projected: list[str] = []
    knowledge_verified: dict[str, KnowledgeVerificationBinding] = {}
    knowledge_artifacts: list[ArtifactByteBinding] = []
    captures: list[StableJsonEvidence] = []
    for evidence_ref in evidence:
        capture = capture_verification_artifact(evidence_ref)
        captures.append(capture)
        digest = str(capture.sha256)
        canonical_ref = str(capture.path)
        digest_ref = f"sha256://verification/{digest}"
        if canonical_ref not in verification_refs or digest_ref not in input_refs:
            raise PolicyError(
                "verification evidence is not byte-bound to its trusted run",
            )
        projected.append(digest_ref)
        artifact_bindings = _knowledge_bindings(
            capture.payload,
            assignments,
            terminals,
            authority,
        )
        if artifact_bindings:
            knowledge_artifacts.append(ArtifactByteBinding(canonical_ref, digest))
        overlap = set(knowledge_verified) & set(artifact_bindings)
        if overlap:
            raise PolicyError(
                f"duplicate knowledge verification for workers: {sorted(overlap)}",
            )
        knowledge_verified.update(artifact_bindings)
    return (
        list(dict.fromkeys(projected)),
        knowledge_verified,
        tuple(knowledge_artifacts),
        tuple(captures),
    )


__all__ = ["project_verification_evidence"]
