#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeAlias, final, override

from agent_company_deps import JsonValue


JsonObject: TypeAlias = dict[str, JsonValue]


@final
class CycleError(Exception):
    __slots__ = ("code", "detail")

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class Mutation:
    state: JsonObject | None
    result: JsonObject


@dataclass(frozen=True, slots=True)
class InitiativeRequest:
    initiative_id: str
    origin: str
    app_id: str | None
    job_type: str
    priority: int
    objective: str
    commercial_hypothesis: str
    success_metrics: tuple[str, ...]
    failure_metrics: tuple[str, ...]
    guardrails: tuple[str, ...]
    now: str


@dataclass(frozen=True, slots=True)
class TickRequest:
    now: str
    tick_key: str
    handoff_dir: str


@dataclass(frozen=True, slots=True)
class AdvanceRequest:
    cycle_id: str
    phase: str
    now: str
    evidence_ref: str
    plan_sha256: str | None


@dataclass(frozen=True, slots=True)
class CloseRequest:
    cycle_id: str
    outcome: str
    now: str
    next_tick_at: str
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class AppRequest:
    app_id: str
    name: str
    kind: str
    lifecycle: str
    repository_ref: str | None


@dataclass(frozen=True, slots=True)
class ObservationRequest:
    app_id: str
    observation_id: str
    captured_at: str
    source_ref: str
    source_sha256: str
    evidence_status: str
    currency: str
    attribution: str
    confidence: float
    freshness: str
    limitations: tuple[str, ...]
    metrics: tuple[tuple[str, float], ...]


def required_text(value: JsonValue, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CycleError("malformed_input", f"{label} must be non-empty text")
    return value


def unique_texts(values: tuple[str, ...], label: str) -> list[str]:
    if not values or len(values) != len(set(values)):
        raise CycleError(
            "malformed_input", f"{label} must contain unique non-empty text",
        )
    return [required_text(value, label) for value in values]


def json_array(values: Iterable[JsonValue]) -> list[JsonValue]:
    return list(values)


def parse_time(value: str, label: str) -> datetime:
    _ = required_text(value, label)
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CycleError("malformed_input", f"{label} must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise CycleError("malformed_input", f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def canonical_time(value: str, label: str) -> str:
    return parse_time(value, label).isoformat().replace("+00:00", "Z")
