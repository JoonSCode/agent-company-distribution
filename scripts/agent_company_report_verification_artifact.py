from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from agent_company_evidence_digest import (
    EvidenceDigestError,
    StableJsonEvidence,
    read_stable_json_evidence,
    require_unchanged_evidence,
)
from agent_company_job_policy import PolicyError

MAX_VERIFICATION_BYTES: Final[int] = 32_768


def capture_verification_artifact(reference: str) -> StableJsonEvidence:
    try:
        return read_stable_json_evidence(
            reference,
            Path.cwd(),
            MAX_VERIFICATION_BYTES,
        )
    except EvidenceDigestError as exc:
        raise PolicyError(
            f"cannot capture stable verification evidence: {reference}",
        ) from exc


def require_unchanged_verification_artifacts(
    captures: Iterable[StableJsonEvidence],
) -> None:
    for capture in captures:
        try:
            require_unchanged_evidence(capture)
        except EvidenceDigestError as exc:
            raise PolicyError(
                f"verification evidence changed after capture: {capture.reference}",
            ) from exc


__all__ = [
    "StableJsonEvidence",
    "capture_verification_artifact",
    "require_unchanged_verification_artifacts",
]
