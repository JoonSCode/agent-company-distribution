#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Inspect through the plan and handoff validators:
#      python3 scripts/test_agent_company_plans.py
#      python3 scripts/test_agent_company_handoff_validation.py
# ─────────────────

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

from agent_company_role_schema import JsonValue

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SHA256: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class OperatingContractSpec:
    ref: str
    sha256: str


@dataclass(frozen=True, slots=True)
class OperatingContractBinding:
    ref: str
    resolved_ref: Path
    sha256: str


@dataclass(frozen=True, slots=True)
class OperatingContractError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


ROLE_OPERATING_CONTRACTS: Final[Mapping[str, OperatingContractSpec | None]] = MappingProxyType(
    {
        "design": OperatingContractSpec(
            "skills/design-operating-system/references/design-contract.json",
            "b93cc233d4d6833e23d0352227f7c82e8be539970b853107c1aa37fe0404ace6",
        ),
        "development": OperatingContractSpec(
            "skills/development-operating-system/references/development-contract.json",
            "e78fdc94b904971f6e7f08e79b9890d78f4de73e7f08fd6db9be87fbb56a5974",
        ),
        "founder": OperatingContractSpec(
            "skills/founder-operating-system/references/founder-contract.json",
            "667f0afaa2bb53154010e05f5b2ba16ff5d02b0cb16525eae68dcf30f5ad7943",
        ),
        "marketing": OperatingContractSpec(
            "skills/marketing-operating-system/references/marketing-contract.json",
            "dbcb8e073280e1e7ef56995545f820af12e92ecf77d0d53c74796189c4a1c889",
        ),
        "planning": OperatingContractSpec(
            "skills/planning-operating-system/references/planning-contract.json",
            "8a76742d7644b13d51ac21e249c9c9017dfb7a54fd38aace9cd59eb021f6d193",
        ),
        "qa-release": OperatingContractSpec(
            "skills/qa-release-operating-system/references/qa-release-contract.json",
            "ebd7858c8e16c4f2386e4a5cb6bc6a249cea05dd2843611909d7ddd1cc7e8b91",
        ),
    }
)


def role_requires_operating_contract(role: str) -> bool:
    return ROLE_OPERATING_CONTRACTS.get(role) is not None


def _pinned_bytes(spec: OperatingContractSpec) -> tuple[Path, bytes]:
    root = ROOT.resolve()
    target = ROOT / spec.ref
    current = ROOT
    for part in Path(spec.ref).parts:
        current /= part
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise OperatingContractError("operating_contract_unavailable", f"canonical contract is unavailable: {spec.ref}") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise OperatingContractError("operating_contract_escape", f"canonical contract contains a symlink: {spec.ref}")
    resolved = target.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise OperatingContractError("operating_contract_escape", f"canonical contract escapes the repository: {spec.ref}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
    except OSError as exc:
        raise OperatingContractError("operating_contract_unavailable", f"cannot open canonical contract: {spec.ref}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise OperatingContractError("operating_contract_escape", f"canonical contract must be one regular file: {spec.ref}")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 65536):
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after:
        raise OperatingContractError("stale_operating_contract", f"canonical contract changed while reading: {spec.ref}")
    return resolved, b"".join(chunks)


def bind_operating_contract(
    role: str,
    reference_value: JsonValue | None,
    digest_value: JsonValue | None,
) -> OperatingContractBinding | None:
    if role not in ROLE_OPERATING_CONTRACTS:
        raise OperatingContractError("malformed_input", f"unsupported role: {role}")
    spec = ROLE_OPERATING_CONTRACTS[role]
    if spec is None:
        if reference_value is not None or digest_value is not None:
            raise OperatingContractError("operating_contract_forbidden", f"{role} has no operating contract")
        return None
    if reference_value is None or digest_value is None:
        raise OperatingContractError("operating_contract_required", f"{role} requires contract path and digest")
    if not isinstance(reference_value, str) or reference_value != spec.ref:
        raise OperatingContractError("operating_contract_mismatch", f"{role} must use its canonical operating contract")
    if not isinstance(digest_value, str) or SHA256.fullmatch(digest_value) is None:
        raise OperatingContractError("malformed_input", "operating contract digest must be lowercase SHA-256")
    if digest_value != spec.sha256:
        raise OperatingContractError("stale_operating_contract", f"{role} contract digest disagrees with the pinned registry")
    resolved, content = _pinned_bytes(spec)
    if hashlib.sha256(content).hexdigest() != spec.sha256:
        raise OperatingContractError("stale_operating_contract", f"canonical {role} contract bytes changed")
    return OperatingContractBinding(spec.ref, resolved, spec.sha256)


def operating_contract_payload(role: str) -> dict[str, JsonValue] | None:
    spec = ROLE_OPERATING_CONTRACTS.get(role)
    if spec is None:
        return None
    return {"ref": spec.ref, "sha256": spec.sha256}
