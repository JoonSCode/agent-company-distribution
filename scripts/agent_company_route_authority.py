#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# Import from scripts/agent_company_routing.py.
# ─────────────────

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final

from agent_company_core_external_action import validate_external_action_ledger
from agent_company_job_policy import PolicyError
from agent_company_route_contract import (
    ApprovalEvidence,
    JsonObject,
    JsonValue,
    RoutingError,
    parse_object,
    parse_text,
)


OPEN_DIR: Final[int] = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
OPEN_FILE: Final[int] = os.O_RDONLY | os.O_NOFOLLOW
MAX_APPROVAL_AGE: Final[timedelta] = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class TrustedJson:
    value: JsonObject
    reference: str
    sha256: str


@dataclass(frozen=True, slots=True)
class RouteAuthorityRequest:
    core_path: Path
    core_sha256: str
    sejong_home: Path
    external_mutation: bool
    approval_required: bool
    ledger_path: Path | None = None
    ledger_sha256: str | None = None
    action_id: str | None = None


@dataclass(frozen=True, slots=True)
class RouteAuthority:
    core: TrustedJson
    approval: ApprovalEvidence | None


def _identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _sha256(value: str, label: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise RoutingError("malformed_input", f"{label} must be a lowercase SHA-256")
    return value


def _relative_trusted_path(path: Path, root: Path, label: str) -> tuple[Path, Path]:
    candidate = path.expanduser()
    configured_root = root.expanduser()
    if not candidate.is_absolute() or not configured_root.is_absolute():
        raise RoutingError("untrusted_path", f"{label} and SEJONG_HOME must be absolute")
    if ".." in candidate.parts or ".." in configured_root.parts:
        raise RoutingError("untrusted_path", f"{label} must not contain traversal")
    try:
        relative = candidate.relative_to(configured_root)
        trusted_root = configured_root.resolve(strict=True)
    except ValueError as exc:
        raise RoutingError("untrusted_path", f"{label} must be contained by SEJONG_HOME") from exc
    except OSError as exc:
        raise RoutingError("untrusted_path", "SEJONG_HOME cannot be resolved") from exc
    if not relative.parts:
        raise RoutingError("untrusted_path", f"{label} must name a regular file")
    return trusted_root, relative


def _require_owned(metadata: os.stat_result, label: str, *, directory: bool) -> None:
    kind_matches = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not kind_matches or metadata.st_uid != os.getuid():
        raise RoutingError("untrusted_path", f"{label} has unsafe kind or ownership")
    if not directory and metadata.st_nlink != 1:
        raise RoutingError("untrusted_path", f"{label} must not be hard-linked")


def _read_anchored(path: Path, root: Path, label: str) -> tuple[bytes, str]:
    trusted_root, relative = _relative_trusted_path(path, root, label)
    descriptors: list[int] = []
    try:
        current = os.open(trusted_root, OPEN_DIR)
        descriptors.append(current)
        _require_owned(os.fstat(current), "SEJONG_HOME", directory=True)
        for component in relative.parts[:-1]:
            current = os.open(component, OPEN_DIR, dir_fd=current)
            descriptors.append(current)
            _require_owned(os.fstat(current), label, directory=True)
        file_fd = os.open(relative.parts[-1], OPEN_FILE, dir_fd=current)
        descriptors.append(file_fd)
        before = os.fstat(file_fd)
        _require_owned(before, label, directory=False)
        with os.fdopen(os.dup(file_fd), "rb") as handle:
            payload = handle.read()
        after = os.fstat(file_fd)
        if _identity(before) != _identity(after):
            raise RoutingError("stale_state", f"{label} changed while it was read")
    except OSError as exc:
        raise RoutingError("untrusted_path", f"cannot securely read {label}") from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    return payload, str(trusted_root / relative)


def read_trusted_json(
    path: Path, expected_sha256: str, sejong_home: Path, label: str,
) -> TrustedJson:
    expected = _sha256(expected_sha256, f"{label} sha256")
    payload, reference = _read_anchored(path, sejong_home, label)
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise RoutingError("stale_state", f"{label} bytes differ from the expected SHA-256")
    try:
        value: JsonValue = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RoutingError("malformed_input", f"{label} is not valid JSON") from exc
    return TrustedJson(parse_object(value, label), reference, actual)


def _timestamp(value: JsonValue, label: str) -> datetime:
    raw = parse_text(value, label)
    normalized = f"{raw[:-1]}+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RoutingError("invalid_approval_receipt", f"{label} is not ISO 8601") from exc
    if parsed.tzinfo is None:
        raise RoutingError("invalid_approval_receipt", f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def approval_evidence(
    ledger: TrustedJson,
    action_id: str,
    core_sha256: str,
    now: datetime | None = None,
) -> ApprovalEvidence:
    try:
        validate_external_action_ledger(ledger.value)
    except PolicyError as exc:
        raise RoutingError("invalid_approval_receipt", "Core rejected the external-action receipt") from exc
    receipts = ledger.value.get("receipts")
    if not isinstance(receipts, list):
        raise RoutingError("invalid_approval_receipt", "external-action receipts must be a list")
    matches = [item for item in receipts if isinstance(item, dict) and item.get("action_id") == action_id]
    if len(matches) != 1:
        raise RoutingError("approval_receipt_missing", "exact external-action approval receipt was not found")
    receipt = matches[0]
    approval = parse_object(receipt.get("approval"), "external-action approval")
    if receipt.get("status") != "authorized":
        raise RoutingError("invalid_approval_receipt", "external action must be authorized and not yet dispatched")
    if receipt.get("input_sha256") != core_sha256:
        raise RoutingError("wrong_approval_decision", "approval receipt is bound to different Core decision bytes")
    if approval.get("issuer_authority") not in {"user", "host"}:
        raise RoutingError("invalid_approval_receipt", "approval issuer must be the CEO/user or host")
    issued_at = _timestamp(approval.get("issued_at"), "approval issued_at")
    expires_at = _timestamp(approval.get("expires_at"), "approval expires_at")
    current = now or datetime.now(timezone.utc)
    if issued_at > current or expires_at < current or current - issued_at > MAX_APPROVAL_AGE:
        raise RoutingError("stale_approval_receipt", "external-action approval receipt is not fresh")
    return ApprovalEvidence(
        ledger.reference,
        ledger.sha256,
        action_id,
        parse_text(approval.get("source_user_decision_ref"), "source_user_decision_ref"),
    )


def load_route_authority(request: RouteAuthorityRequest) -> RouteAuthority:
    core = read_trusted_json(
        request.core_path,
        request.core_sha256,
        request.sejong_home,
        "Core decision",
    )
    receipt_fields = (request.ledger_path, request.ledger_sha256, request.action_id)
    if request.external_mutation:
        if not request.approval_required:
            raise RoutingError("approval_gate_missing", "external mutation requires an approval gate")
        if (
            request.ledger_path is None
            or request.ledger_sha256 is None
            or request.action_id is None
        ):
            raise RoutingError(
                "approval_receipt_missing",
                "external mutation requires ledger path, SHA-256, and action id",
            )
        ledger = read_trusted_json(
            request.ledger_path,
            request.ledger_sha256,
            request.sejong_home,
            "external-action ledger",
        )
        approval = approval_evidence(ledger, request.action_id, core.sha256)
        return RouteAuthority(core, approval)
    if any(receipt_fields):
        raise RoutingError(
            "malformed_input",
            "external-action receipt inputs require --external-mutation",
        )
    return RouteAuthority(core, None)


__all__ = [
    "RouteAuthority",
    "RouteAuthorityRequest",
    "TrustedJson",
    "load_route_authority",
    "read_trusted_json",
]
