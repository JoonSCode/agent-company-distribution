#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Import this generated runtime/schema safety contract.
# ─────────────────

"""Load the exhaustive pinned Unicode and EvidenceRef contract."""

from __future__ import annotations
# pyright: reportAny=false, reportImplicitRelativeImport=false

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypedDict, override

from agent_company_deps import JsonValue


ROOT: Final[Path] = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final[Path] = ROOT / "policies" / "compact-unicode-safety.json"
EXPECTED_FORMAT: Final[str] = "agent-company.compact-unicode-safety/v0.2"
EXPECTED_UNICODE_VERSION: Final[str] = "16.0.0"
EXPECTED_CATEGORIES: Final[list[str]] = ["Cc", "Cf", "Cn", "Co", "Cs"]
EXPECTED_NONCHARACTER_POLICY: Final[str] = "U+FDD0-FDEF and every plane FFFE-FFFF"
EXPECTED_RANGE_COUNT: Final[int] = 736
EXPECTED_CODEPOINT_COUNT: Final[int] = 959_284
EXPECTED_ARTIFACT_SHA256: Final[str] = (
    "d18f5be8dddd668734f50c436a5f93acd01ad0f2d9da252502e34c4c63254a28"
)
EXPECTED_PATTERN_SHA256: Final[str] = (
    "c4f9ba76f9acd79c212781d57ee3af8e16bc38c844673e25de1d9336c8e7eb96"
)


class ContractBase(TypedDict):
    format: str
    unicode_version: str
    forbidden_categories: list[str]
    noncharacter_policy: str
    forbidden_ranges: list[list[int]]
    safe_text_pattern: str
    evidence_ref_pattern: str


class Contract(ContractBase):
    sha256: str


@dataclass(frozen=True, slots=True)
class ContractError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return self.detail


def _text(root: dict[str, JsonValue], field: str) -> str:
    value = root.get(field)
    if not isinstance(value, str) or not value:
        raise ContractError(f"compact Unicode contract {field} must be text")
    return value


def _texts(root: dict[str, JsonValue], field: str) -> list[str]:
    value = root.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ContractError(f"compact Unicode contract {field} must be a text list")
    return [item for item in value if isinstance(item, str)]


def _ranges(root: dict[str, JsonValue]) -> list[list[int]]:
    value = root.get("forbidden_ranges")
    if not isinstance(value, list):
        raise ContractError("compact Unicode contract forbidden_ranges must be a list")
    ranges: list[list[int]] = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            raise ContractError("compact Unicode contract contains a malformed range")
        start, end = item
        if not isinstance(start, int) or isinstance(start, bool):
            raise ContractError("compact Unicode contract contains a malformed range")
        if not isinstance(end, int) or isinstance(end, bool):
            raise ContractError("compact Unicode contract contains a malformed range")
        ranges.append([start, end])
    return ranges


def load_contract(path: Path = CONTRACT_PATH) -> Contract:
    try:
        parsed: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read compact Unicode contract: {exc}") from exc
    value = parsed
    if not isinstance(value, dict):
        raise ContractError("compact Unicode contract must be an object")
    required = {
        "format",
        "unicode_version",
        "forbidden_categories",
        "forbidden_ranges",
        "noncharacter_policy",
        "safe_text_pattern",
        "evidence_ref_pattern",
        "sha256",
    }
    if set(value) != required:
        raise ContractError("compact Unicode contract keys differ from runtime")
    base: ContractBase = {
        "format": _text(value, "format"),
        "unicode_version": _text(value, "unicode_version"),
        "forbidden_categories": _texts(value, "forbidden_categories"),
        "noncharacter_policy": _text(value, "noncharacter_policy"),
        "forbidden_ranges": _ranges(value),
        "safe_text_pattern": _text(value, "safe_text_pattern"),
        "evidence_ref_pattern": _text(value, "evidence_ref_pattern"),
    }
    encoded = json.dumps(
        base, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    sha256 = _text(value, "sha256")
    calculated = hashlib.sha256(encoded).hexdigest()
    if sha256 != calculated or sha256 != EXPECTED_ARTIFACT_SHA256:
        raise ContractError("compact Unicode contract digest mismatch")
    if base["format"] != EXPECTED_FORMAT:
        raise ContractError("compact Unicode contract format differs from code pin")
    if base["unicode_version"] != EXPECTED_UNICODE_VERSION:
        raise ContractError("compact Unicode version differs from code pin")
    if base["forbidden_categories"] != EXPECTED_CATEGORIES:
        raise ContractError("compact Unicode categories differ from code pin")
    if base["noncharacter_policy"] != EXPECTED_NONCHARACTER_POLICY:
        raise ContractError("compact Unicode noncharacter policy differs from code pin")
    ranges = base["forbidden_ranges"]
    if len(ranges) != EXPECTED_RANGE_COUNT:
        raise ContractError("compact Unicode range count differs from code pin")
    previous = -1
    codepoint_count = 0
    for start, end in ranges:
        if start <= previous or start > end or end > 0x10FFFF:
            raise ContractError("compact Unicode ranges are not canonical and disjoint")
        previous = end
        codepoint_count += end - start + 1
    if codepoint_count != EXPECTED_CODEPOINT_COUNT:
        raise ContractError("compact Unicode codepoint count differs from code pin")
    pattern_digest = hashlib.sha256(
        f"{base['safe_text_pattern']}\0{base['evidence_ref_pattern']}".encode()
    ).hexdigest()
    if pattern_digest != EXPECTED_PATTERN_SHA256:
        raise ContractError("compact Unicode pattern digest differs from code pin")
    return {
        "format": base["format"],
        "unicode_version": base["unicode_version"],
        "forbidden_categories": base["forbidden_categories"],
        "noncharacter_policy": base["noncharacter_policy"],
        "forbidden_ranges": base["forbidden_ranges"],
        "safe_text_pattern": base["safe_text_pattern"],
        "evidence_ref_pattern": base["evidence_ref_pattern"],
        "sha256": sha256,
    }


CONTRACT: Final[Contract] = load_contract()
CONTRACT_VERSION: Final[str] = CONTRACT["format"]
UNICODE_VERSION: Final[str] = CONTRACT["unicode_version"]
CONTRACT_SHA256: Final[str] = CONTRACT["sha256"]
FORBIDDEN_RANGES: Final = tuple(
    (item[0], item[1]) for item in CONTRACT["forbidden_ranges"]
)
SAFE_TEXT_PATTERN: Final[str] = CONTRACT["safe_text_pattern"]
EVIDENCE_REF_PATTERN: Final[str] = CONTRACT["evidence_ref_pattern"]
SAFE_TEXT_RE: Final = re.compile(SAFE_TEXT_PATTERN)
EVIDENCE_REF_RE: Final = re.compile(EVIDENCE_REF_PATTERN)


def safe_text_is_valid(value: str) -> bool:
    return SAFE_TEXT_RE.fullmatch(value) is not None


def evidence_ref_is_valid(value: str) -> bool:
    return EVIDENCE_REF_RE.fullmatch(value) is not None
