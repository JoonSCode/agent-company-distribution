from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import re
from dataclasses import dataclass
from typing import Final

from agent_company_role_schema import JsonValue

SHA256: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
BYTE_PROVENANCE_FIELDS: Final[frozenset[str]] = frozenset({
    "delegation_input", "job", "core_run", "worker_artifacts",
})
ARTIFACT_FIELDS: Final[frozenset[str]] = frozenset({"ref", "sha256"})
WORKER_ARTIFACT_FIELDS: Final[frozenset[str]] = frozenset({
    "worker_id", "handoff_ref", "handoff_sha256", "terminal_receipt_id",
    "terminal_receipt_sha256",
})


class KnowledgeProvenanceError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactByteBinding:
    ref: str
    sha256: str


@dataclass(frozen=True, slots=True)
class WorkerArtifactByteBinding:
    worker_id: str
    handoff_ref: str
    handoff_sha256: str
    terminal_receipt_id: str
    terminal_receipt_sha256: str


@dataclass(frozen=True, slots=True)
class KnowledgeByteProvenance:
    delegation_input: ArtifactByteBinding
    job: ArtifactByteBinding
    core_run: ArtifactByteBinding
    worker_artifacts: tuple[WorkerArtifactByteBinding, ...]


def _object(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise KnowledgeProvenanceError(f"{label} must be an object")
    return value


def _objects(
    value: JsonValue | None,
    label: str,
) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list):
        raise KnowledgeProvenanceError(f"{label} must be a list")
    return tuple(
        _object(item, f"{label}[{index}]")
        for index, item in enumerate(value)
    )


def _text(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeProvenanceError(f"{label} must be non-empty text")
    return value


def _exact(
    value: dict[str, JsonValue],
    fields: frozenset[str],
    label: str,
) -> None:
    if frozenset(value) != fields:
        raise KnowledgeProvenanceError(f"{label} has an unexpected shape")


def _sha256(value: JsonValue | None, label: str) -> str:
    digest = _text(value, label)
    if SHA256.fullmatch(digest) is None:
        raise KnowledgeProvenanceError(f"{label} must be a SHA-256 digest")
    return digest


def _artifact_binding(
    value: JsonValue | None,
    label: str,
) -> ArtifactByteBinding:
    raw = _object(value, label)
    _exact(raw, ARTIFACT_FIELDS, label)
    ref = _text(raw.get("ref"), f"{label}.ref")
    if "://" in ref:
        raise KnowledgeProvenanceError(
            f"{label}.ref must be a local artifact path",
        )
    return ArtifactByteBinding(ref, _sha256(raw.get("sha256"), f"{label}.sha256"))


def _worker_binding(
    item: dict[str, JsonValue],
) -> WorkerArtifactByteBinding:
    _exact(item, WORKER_ARTIFACT_FIELDS, "worker artifact")
    handoff_ref = _text(item.get("handoff_ref"), "worker artifact.handoff_ref")
    if "://" in handoff_ref:
        raise KnowledgeProvenanceError(
            "worker artifact.handoff_ref must be a local artifact path",
        )
    return WorkerArtifactByteBinding(
        _text(item.get("worker_id"), "worker artifact.worker_id"),
        handoff_ref,
        _sha256(item.get("handoff_sha256"), "worker artifact.handoff_sha256"),
        _text(item.get("terminal_receipt_id"), "worker artifact.terminal_receipt_id"),
        _sha256(
            item.get("terminal_receipt_sha256"),
            "worker artifact.terminal_receipt_sha256",
        ),
    )


def parse_byte_provenance(value: JsonValue | None) -> KnowledgeByteProvenance:
    raw = _object(value, "byte_provenance")
    _exact(raw, BYTE_PROVENANCE_FIELDS, "byte_provenance")
    workers = tuple(
        _worker_binding(item)
        for item in _objects(
            raw.get("worker_artifacts"),
            "byte_provenance.worker_artifacts",
        )
    )
    worker_ids = tuple(item.worker_id for item in workers)
    if not workers or len(worker_ids) != len(set(worker_ids)):
        raise KnowledgeProvenanceError(
            "byte_provenance worker artifacts must be unique",
        )
    return KnowledgeByteProvenance(
        _artifact_binding(raw.get("delegation_input"), "byte_provenance.delegation_input"),
        _artifact_binding(raw.get("job"), "byte_provenance.job"),
        _artifact_binding(raw.get("core_run"), "byte_provenance.core_run"),
        workers,
    )
