#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Imported by agent_company_memory_domain.py.
# 3. Test: python3 scripts/test_agent_company_memory.py
# ─────────────────

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

import re
from dataclasses import asdict, dataclass
from typing import Final, final, override

from agent_company_privacy import JsonObject, PrivacyError, ROLES, parse_rfc3339, reject_sensitive


FORMAT: Final[str] = "agent-company.memory-record/v0.2"
RECORD_TYPES: Final = frozenset({"portfolio-decision", "product-decision", "experiment-result", "verification-baseline"})
FIELDS: Final = frozenset({
    "format", "record_id", "record_type", "recorded_at", "summary", "source", "confidence",
    "freshness", "supersedes", "deletion_id", "visible_to_roles",
})
ID_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
REF_PATTERN: Final = re.compile(r"^(?:artifact|observed|user-approved)://[A-Za-z0-9._/-]{1,480}$")


@final
class MemoryContractError(Exception):
    """Typed memory-contract failure."""

    code: str
    detail: str

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)
        self.code = code
        self.detail = detail

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class Source:
    kind: str
    ref: str


@dataclass(frozen=True, slots=True)
class Freshness:
    observed_at: str
    review_after: str


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    record_id: str
    record_type: str
    recorded_at: str
    summary: str
    source: Source
    confidence: float
    freshness: Freshness
    supersedes: tuple[str, ...]
    deletion_id: str
    visible_to_roles: tuple[str, ...]


def _error(exc: PrivacyError) -> MemoryContractError:
    return MemoryContractError(exc.code, exc.detail)


def _text(values: JsonObject, name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or not value:
        raise MemoryContractError("malformed_input", f"{name} must be non-empty text")
    return value


def _identifier(value: str, name: str) -> str:
    if ID_PATTERN.fullmatch(value) is None:
        raise MemoryContractError("malformed_input", f"{name} is invalid")
    return value


def _strings(values: JsonObject, name: str, *, required: bool) -> tuple[str, ...]:
    value = values.get(name)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise MemoryContractError("malformed_input", f"{name} must be a string list")
    result = tuple(item for item in value if isinstance(item, str))
    if (required and not result) or len(set(result)) != len(result):
        raise MemoryContractError("malformed_input", f"{name} must be non-empty and unique")
    return result


def parse_memory_record(payload: JsonObject) -> MemoryRecord:
    try:
        reject_sensitive(payload)
    except PrivacyError as exc:
        raise _error(exc) from exc
    if frozenset(payload) != FIELDS or payload.get("format") != FORMAT:
        raise MemoryContractError("malformed_input", "record fields or format are invalid")
    source = payload.get("source")
    freshness = payload.get("freshness")
    if not isinstance(source, dict) or set(source) != {"kind", "ref"}:
        raise MemoryContractError("malformed_input", "source must contain kind and ref")
    if not isinstance(freshness, dict) or set(freshness) != {"observed_at", "review_after"}:
        raise MemoryContractError("malformed_input", "freshness fields are invalid")
    record_type = _text(payload, "record_type")
    source_kind = _text(source, "kind")
    source_ref = _text(source, "ref")
    summary = _text(payload, "summary")
    confidence = payload.get("confidence")
    supersedes = _strings(payload, "supersedes", required=False)
    roles = _strings(payload, "visible_to_roles", required=True)
    if record_type not in RECORD_TYPES or source_kind not in {"artifact", "observed", "user-approved"}:
        raise MemoryContractError("malformed_input", "record type or source kind is invalid")
    if REF_PATTERN.fullmatch(source_ref) is None or len(summary) > 2000:
        raise MemoryContractError("malformed_input", "source ref or summary is invalid")
    if not set(roles) <= ROLES or not source_ref.startswith(f"{source_kind}://"):
        raise MemoryContractError("malformed_input", "role visibility or source ref kind is invalid")
    if isinstance(confidence, bool) or not isinstance(confidence, int | float) or not 0 <= confidence <= 1:
        raise MemoryContractError("malformed_input", "confidence must be between zero and one")
    try:
        recorded = parse_rfc3339(_text(payload, "recorded_at"), "recorded_at")
        observed = parse_rfc3339(_text(freshness, "observed_at"), "observed_at")
        review = parse_rfc3339(_text(freshness, "review_after"), "review_after")
    except PrivacyError as exc:
        raise _error(exc) from exc
    if observed > review or recorded < observed or recorded > review:
        raise MemoryContractError("malformed_input", "freshness timestamps are out of order")
    return MemoryRecord(
        _identifier(_text(payload, "record_id"), "record_id"), record_type, _text(payload, "recorded_at"), summary,
        Source(source_kind, source_ref), float(confidence),
        Freshness(_text(freshness, "observed_at"), _text(freshness, "review_after")),
        tuple(_identifier(item, "supersedes") for item in supersedes),
        _identifier(_text(payload, "deletion_id"), "deletion_id"), roles,
    )


def memory_json(record: MemoryRecord) -> JsonObject:
    return {"format": FORMAT, **asdict(record)}


def validate_memory_graph(records: list[MemoryRecord]) -> None:
    by_id = {record.record_id: record for record in records}
    if len(by_id) != len(records):
        raise MemoryContractError("semantic_corruption", "duplicate record_id")
    if any(not set(record.supersedes) <= set(by_id) for record in records):
        raise MemoryContractError("semantic_corruption", "supersedes references a missing record")
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(record_id: str) -> None:
        if record_id in visiting:
            raise MemoryContractError("semantic_corruption", "supersession cycle")
        if record_id in visited:
            return
        visiting.add(record_id)
        for parent in by_id[record_id].supersedes:
            walk(parent)
        visiting.remove(record_id)
        visited.add(record_id)

    for record_id in by_id:
        walk(record_id)
