from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_company_deps import JsonValue
from agent_company_evidence_digest import (
    EvidenceDigestError,
    read_stable_json_evidence,
    require_matching_evidence_digest,
)
from agent_company_handoff_errors import HandoffError
from agent_company_handoff_parser import validate_handoff_payload

ROOT = Path(__file__).resolve().parents[1]


class HandoffArtifactError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class HandoffArtifact:
    reference: str
    sha256: str
    payload: dict[str, JsonValue]
    receipt_digest_bound: bool


def read_receipt_handoff(
    assignment: dict[str, JsonValue],
    receipt: dict[str, JsonValue],
) -> HandoffArtifact:
    raw_reference = receipt.get("worker_output_ref")
    if not isinstance(raw_reference, str) or not raw_reference.strip():
        raise HandoffArtifactError("worker_output_ref must be a non-empty string")
    try:
        evidence = read_stable_json_evidence(raw_reference, ROOT)
        payload = validate_handoff_payload(
            evidence.payload,
            expected_role_evidence_context_binding=assignment.get(
                "role_evidence_context_binding"
            ),
        )
    except (EvidenceDigestError, HandoffError) as exc:
        raise HandoffArtifactError(str(exc)) from exc
    raw_digest = receipt.get("worker_output_sha256")
    if raw_digest is None:
        digest_bound = False
    elif isinstance(raw_digest, str):
        try:
            require_matching_evidence_digest(evidence, raw_digest)
        except EvidenceDigestError as exc:
            raise HandoffArtifactError(str(exc)) from exc
        digest_bound = True
    else:
        raise HandoffArtifactError(
            "worker_output_sha256 must be a lowercase SHA-256 string"
        )
    return HandoffArtifact(
        evidence.reference,
        str(evidence.sha256),
        payload,
        digest_bound,
    )
