from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NewType, TypeAlias

from agent_company_role_schema import JsonValue

JsonObject: TypeAlias = dict[str, JsonValue]
Sha256Digest = NewType("Sha256Digest", str)


class EvidenceDigestErrorCode(StrEnum):
    INVALID_REFERENCE = "evidence_digest_invalid_reference"
    UNAVAILABLE_SOURCE = "evidence_digest_unavailable_source"
    UNSAFE_SOURCE = "evidence_digest_unsafe_source"
    UNSTABLE_SOURCE = "evidence_digest_unstable_source"
    OVERSIZED_SOURCE = "evidence_digest_oversized_source"
    INVALID_JSON = "evidence_digest_invalid_json"
    INVALID_DIGEST = "evidence_digest_invalid_digest"
    DIGEST_MISMATCH = "evidence_digest_mismatch"


@dataclass(frozen=True, slots=True)
class StableFileIdentity:
    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True, slots=True)
class StableJsonEvidence:
    reference: str
    path: Path
    content: bytes
    sha256: Sha256Digest
    payload: JsonObject
    identity: StableFileIdentity


class EvidenceDigestError(Exception):
    def __init__(
        self,
        code: EvidenceDigestErrorCode,
        reference: str,
        detail: str,
    ) -> None:
        self.code = code
        self.reference = reference
        self.detail = detail
        super().__init__(code, reference, detail)

    def __str__(self) -> str:
        return f"{self.code.value}: {self.detail} ({self.reference})"
