from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Final

from agent_company_evidence_digest_models import (
    EvidenceDigestError,
    EvidenceDigestErrorCode,
    Sha256Digest,
    StableFileIdentity,
    StableJsonEvidence,
)

DEFAULT_MAX_BYTES: Final[int] = 32_768
SHA256: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


def _error(
    code: EvidenceDigestErrorCode,
    reference: str,
    detail: str,
) -> EvidenceDigestError:
    return EvidenceDigestError(code, reference, detail)


def _path(reference: str, base_dir: Path) -> Path:
    if not reference.strip() or "://" in reference or "\x00" in reference:
        raise _error(
            EvidenceDigestErrorCode.INVALID_REFERENCE,
            reference,
            "reference must be bounded local text",
        )
    raw = Path(reference).expanduser()
    base = Path(os.path.abspath(base_dir)).resolve()
    path = Path(os.path.abspath(raw if raw.is_absolute() else base / raw))
    if not raw.is_absolute() and not path.is_relative_to(base):
        raise _error(
            EvidenceDigestErrorCode.INVALID_REFERENCE,
            reference,
            "relative reference escapes its base directory",
        )
    for ancestor in (*reversed(path.parents[:-1]), path.parent):
        try:
            if stat.S_ISLNK(ancestor.lstat().st_mode):
                raise _error(
                    EvidenceDigestErrorCode.UNSAFE_SOURCE,
                    reference,
                    "source path contains a symlink ancestor",
                )
        except OSError as exc:
            raise _error(
                EvidenceDigestErrorCode.UNAVAILABLE_SOURCE,
                reference,
                "source ancestor is unavailable",
            ) from exc
    return path


def _identity(metadata: os.stat_result) -> StableFileIdentity:
    return StableFileIdentity(
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _lstat(path: Path, reference: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise _error(
            EvidenceDigestErrorCode.UNAVAILABLE_SOURCE,
            reference,
            "source is unavailable",
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise _error(
            EvidenceDigestErrorCode.UNSAFE_SOURCE,
            reference,
            "source must be a non-symlink regular file",
        )
    return metadata


def _read(descriptor: int, reference: str, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while chunk := os.read(descriptor, min(65_536, max_bytes + 1)):
        chunks.append(chunk)
        size += len(chunk)
        if size > max_bytes:
            raise _error(
                EvidenceDigestErrorCode.OVERSIZED_SOURCE,
                reference,
                f"source exceeds {max_bytes} bytes",
            )
    return b"".join(chunks)


def _open_nofollow(path: Path, reference: str) -> int:
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path.anchor, directory_flags)
    try:
        for component in path.parts[1:-1]:
            next_descriptor = os.open(
                component,
                directory_flags,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        result = os.open(path.name, file_flags, dir_fd=descriptor)
    except OSError as exc:
        raise _error(
            EvidenceDigestErrorCode.UNSAFE_SOURCE,
            reference,
            "source path could not be traversed without following links",
        ) from exc
    finally:
        os.close(descriptor)
    return result


def read_stable_json_evidence(
    reference: str,
    base_dir: Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> StableJsonEvidence:
    if max_bytes < 1:
        raise _error(
            EvidenceDigestErrorCode.INVALID_REFERENCE,
            reference,
            "max_bytes must be positive",
        )
    path = _path(reference, base_dir)
    before_path = _lstat(path, reference)
    descriptor = _open_nofollow(path, reference)
    try:
        before_fd = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before_fd.st_mode)
            or _identity(before_fd) != _identity(before_path)
        ):
            raise _error(
                EvidenceDigestErrorCode.UNSTABLE_SOURCE,
                reference,
                "opened source differs from the inspected path",
            )
        content = _read(descriptor, reference, max_bytes)
        after_fd = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after_path = _lstat(path, reference)
    identity = _identity(before_fd)
    if (
        _identity(after_fd) != identity
        or _identity(after_path) != identity
        or len(content) != identity.size
    ):
        raise _error(
            EvidenceDigestErrorCode.UNSTABLE_SOURCE,
            reference,
            "source changed while being read",
        )
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error(
            EvidenceDigestErrorCode.INVALID_JSON,
            reference,
            "source must contain one JSON object",
        ) from exc
    if not isinstance(value, dict):
        raise _error(
            EvidenceDigestErrorCode.INVALID_JSON,
            reference,
            "source must contain one JSON object",
        )
    return StableJsonEvidence(
        reference,
        path,
        content,
        Sha256Digest(hashlib.sha256(content).hexdigest()),
        value,
        identity,
    )


def require_matching_evidence_digest(
    evidence: StableJsonEvidence,
    expected_sha256: str,
) -> None:
    if SHA256.fullmatch(expected_sha256) is None:
        raise _error(
            EvidenceDigestErrorCode.INVALID_DIGEST,
            evidence.reference,
            "expected digest must be lowercase SHA-256",
        )
    if evidence.sha256 != expected_sha256:
        raise _error(
            EvidenceDigestErrorCode.DIGEST_MISMATCH,
            evidence.reference,
            "captured bytes differ from the expected digest",
        )


def require_unchanged_evidence(evidence: StableJsonEvidence) -> None:
    current = read_stable_json_evidence(
        str(evidence.path),
        evidence.path.parent,
        max(len(evidence.content), 1),
    )
    if (
        current.identity != evidence.identity
        or current.content != evidence.content
        or current.sha256 != evidence.sha256
    ):
        raise _error(
            EvidenceDigestErrorCode.UNSTABLE_SOURCE,
            evidence.reference,
            "source changed after capture",
        )


__all__ = [
    "DEFAULT_MAX_BYTES",
    "EvidenceDigestError",
    "StableJsonEvidence",
    "read_stable_json_evidence",
    "require_matching_evidence_digest",
    "require_unchanged_evidence",
]
