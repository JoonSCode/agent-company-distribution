#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Run through the report suites:
#      uv run scripts/test_agent_company_report_hardening.py
# 2. This module owns report status parsing and projection.
# ─────────────────

from __future__ import annotations

from enum import StrEnum
from typing import Final, TypeVar

from agent_company_deps import JsonValue
from agent_company_job_policy import PolicyError, text


EnumValue = TypeVar("EnumValue", bound=StrEnum)


class TerminalStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    BLOCKED = "blocked"


class ExternalStatus(StrEnum):
    AUTHORIZED = "authorized"
    DISPATCHED = "dispatched"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CleanupStatus(StrEnum):
    RELEASED = "released"
    PRESERVED = "preserved"
    FAILED = "failed"
    AUDIT_ONLY = "audit_only"


TERMINAL_STATES: Final[dict[TerminalStatus, str]] = {
    TerminalStatus.COMPLETED: "executed",
    TerminalStatus.FAILED: "failed",
    TerminalStatus.TIMED_OUT: "failed",
    TerminalStatus.BLOCKED: "blocked",
}
EXTERNAL_STATES: Final[dict[ExternalStatus, str]] = {
    ExternalStatus.AUTHORIZED: "unverified",
    ExternalStatus.DISPATCHED: "unverified",
    ExternalStatus.COMPLETED: "executed",
    ExternalStatus.FAILED: "failed",
    ExternalStatus.CANCELLED: "blocked",
}
CLEANUP_STATES: Final[dict[CleanupStatus, str | None]] = {
    CleanupStatus.RELEASED: None,
    CleanupStatus.PRESERVED: "blocked",
    CleanupStatus.FAILED: "failed",
    CleanupStatus.AUDIT_ONLY: "blocked",
}


def overall_state(states: list[str]) -> str:
    if not states:
        return "unverified"
    unique = set(states)
    return next(iter(unique)) if len(unique) == 1 else "mixed"


def enum_value(
    enum_type: type[EnumValue], value: JsonValue, label: str,
) -> EnumValue:
    try:
        return enum_type(text(value, label))
    except ValueError as exc:
        raise PolicyError(f"{label} has an unsupported value") from exc


def terminal_state(status: TerminalStatus) -> str:
    return TERMINAL_STATES[status]


def external_state(status: ExternalStatus, verified: bool) -> str:
    return "verified" if status == ExternalStatus.COMPLETED and verified else EXTERNAL_STATES[status]


def cleanup_state(status: CleanupStatus) -> str | None:
    return CLEANUP_STATES[status]
