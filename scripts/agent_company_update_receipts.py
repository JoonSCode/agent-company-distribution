#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Use through agent_company_update_status.py.
# 2. Tests: python3 scripts/test_doctor_runtime.py.
# 3. Receipt writes are run-id-bound, locked, and atomic.
# ─────────────────

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Literal, final, override

from agent_company_install_types import JsonValue
from agent_company_privacy import PrivacyError, parse_rfc3339


FORMAT: Final[str] = "agent-company.update-status/v0.2"
RUN_ID: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{32}$")
FUTURE_SKEW: Final[timedelta] = timedelta(minutes=5)
STALE_AFTER: Final[timedelta] = timedelta(hours=1)


@final
class UpdateReceiptError(Exception):
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
class UpdateAttempt:
    run_id: str
    attempted_at: str


@dataclass(frozen=True, slots=True)
class UpdateResult:
    run_id: str
    completed_at: str
    exit_code: int
    successful_at: str | None


@dataclass(frozen=True, slots=True)
class UpdateRun:
    run_id: str
    attempted_at: str
    completed_at: str | None
    exit_code: int | None
    successful_at: str | None


@dataclass(frozen=True, slots=True)
class UpdateReceiptState:
    runs: tuple[UpdateRun, ...]
    legacy_successful_at: str | None
    telemetry_warning: JsonValue
    last_doctor_at: str | None


@dataclass(frozen=True, slots=True)
class UpdateProjection:
    state: Literal["none", "legacy-success", "succeeded", "failed", "in-progress", "stale"]
    run_id: str
    attempted_at: str | None
    completed_at: str | None
    exit_code: int | None
    successful_at: str | None


def parsed_time(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise UpdateReceiptError("invalid_timestamp", f"{field} must be finite RFC3339")
    try:
        return parse_rfc3339(value, field)
    except PrivacyError as exc:
        raise UpdateReceiptError("invalid_timestamp", f"{field} must be finite RFC3339") from exc


def validate_run(run: UpdateRun) -> UpdateRun:
    if not isinstance(run.run_id, str) or RUN_ID.fullmatch(run.run_id) is None:
        raise UpdateReceiptError("invalid_run_id", "run_id must be 32 lowercase hex characters")
    attempted = parsed_time(run.attempted_at, "attempted_at")
    if run.completed_at is None:
        if run.exit_code is not None or run.successful_at is not None:
            raise UpdateReceiptError("invalid_order", "incomplete run cannot carry result fields")
        return run
    completed = parsed_time(run.completed_at, "completed_at")
    if type(run.exit_code) is not int:
        raise UpdateReceiptError("invalid_exit", "result exit must be an integer, not bool")
    if completed < attempted:
        raise UpdateReceiptError("invalid_order", "result must follow attempt")
    if run.exit_code == 0:
        if run.successful_at is None or parsed_time(run.successful_at, "successful_at") < completed:
            raise UpdateReceiptError("invalid_order", "successful result timestamp must follow completion")
    elif run.successful_at is not None:
        raise UpdateReceiptError("invalid_order", "failed result cannot carry successful_at")
    return run


def parse_run(value: JsonValue) -> UpdateRun:
    required = {"run_id", "attempted_at", "completed_at", "exit_code", "successful_at"}
    if not isinstance(value, dict) or set(value) != required:
        raise UpdateReceiptError("invalid_receipt", "update run shape is invalid")
    run_id, attempted_at = value.get("run_id"), value.get("attempted_at")
    completed_at, exit_code, successful_at = value.get("completed_at"), value.get("exit_code"), value.get("successful_at")
    if not isinstance(run_id, str) or not isinstance(attempted_at, str):
        raise UpdateReceiptError("invalid_receipt", "run id and attempt timestamp must be text")
    if completed_at is not None and not isinstance(completed_at, str):
        raise UpdateReceiptError("invalid_receipt", "completed_at must be RFC3339 text or null")
    if successful_at is not None and not isinstance(successful_at, str):
        raise UpdateReceiptError("invalid_receipt", "successful_at must be RFC3339 text or null")
    if exit_code is not None and type(exit_code) is not int:
        raise UpdateReceiptError("invalid_exit", "bool is not an exit code")
    return validate_run(UpdateRun(run_id, attempted_at, completed_at, exit_code, successful_at))


def parse_update_status(payload: dict[str, JsonValue]) -> UpdateReceiptState:
    raw_runs = payload.get("runs")
    if raw_runs is None:
        allowed_legacy = {
            "last_update_at", "last_doctor_at", "telemetry_warning",
            "last_attempted_update", "last_successful_update", "last_update_exit",
        }
        if set(payload) - allowed_legacy:
            raise UpdateReceiptError("invalid_receipt", "legacy update status contains unknown fields")
        if set(payload) & {"last_attempted_update", "last_successful_update", "last_update_exit"}:
            raise UpdateReceiptError("invalid_receipt", "legacy update result is not bound to a run id")
        legacy = payload.get("last_update_at")
        if legacy is not None and not isinstance(legacy, str):
            raise UpdateReceiptError("invalid_timestamp", "last_update_at must be RFC3339 text")
        if isinstance(legacy, str):
            _ = parsed_time(legacy, "last_update_at")
        doctor = payload.get("last_doctor_at")
        if doctor is not None and not isinstance(doctor, str):
            raise UpdateReceiptError("invalid_timestamp", "last_doctor_at must be RFC3339 text")
        if isinstance(doctor, str):
            _ = parsed_time(doctor, "last_doctor_at")
        return UpdateReceiptState((), legacy, payload.get("telemetry_warning"), doctor)
    if payload.get("schema_version") != FORMAT or not isinstance(raw_runs, list):
        raise UpdateReceiptError("invalid_receipt", "update status version or runs are invalid")
    allowed = {"schema_version", "runs", "last_update_at", "last_doctor_at", "telemetry_warning"}
    if set(payload) - allowed:
        raise UpdateReceiptError("invalid_receipt", "update status contains ambiguous fields")
    runs = tuple(parse_run(value) for value in raw_runs)
    if len({run.run_id for run in runs}) != len(runs):
        raise UpdateReceiptError("duplicate_run", "update run ids must be unique")
    legacy = payload.get("last_update_at")
    if legacy is not None and not isinstance(legacy, str):
        raise UpdateReceiptError("invalid_timestamp", "last_update_at must be RFC3339 text")
    if isinstance(legacy, str):
        _ = parsed_time(legacy, "last_update_at")
    doctor = payload.get("last_doctor_at")
    if doctor is not None and not isinstance(doctor, str):
        raise UpdateReceiptError("invalid_timestamp", "last_doctor_at must be RFC3339 text")
    if isinstance(doctor, str):
        _ = parsed_time(doctor, "last_doctor_at")
    attempts = tuple(parsed_time(run.attempted_at, "attempted_at") for run in runs)
    if any(later < earlier for earlier, later in zip(attempts, attempts[1:], strict=False)):
        raise UpdateReceiptError("invalid_order", "update attempts must be stored in chronological order")
    return UpdateReceiptState(runs, legacy, payload.get("telemetry_warning"), doctor)


def run_json(run: UpdateRun) -> dict[str, JsonValue]:
    return {
        "run_id": run.run_id,
        "attempted_at": run.attempted_at,
        "completed_at": run.completed_at,
        "exit_code": run.exit_code,
        "successful_at": run.successful_at,
    }


def validate_receipt_state(state: UpdateReceiptState, now: datetime) -> UpdateReceiptState:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise UpdateReceiptError("invalid_clock", "projection clock must be timezone-aware")
    current = now.astimezone(UTC)
    if not isinstance(state.runs, tuple):
        raise UpdateReceiptError("invalid_receipt", "runs must be an immutable tuple")
    if any(not isinstance(run, UpdateRun) for run in state.runs):
        raise UpdateReceiptError("invalid_receipt", "runs must contain update run values")
    validated = tuple(validate_run(run) for run in state.runs)
    if len({run.run_id for run in validated}) != len(validated):
        raise UpdateReceiptError("duplicate_run", "update run ids must be unique")
    attempts = tuple(parsed_time(run.attempted_at, "attempted_at") for run in validated)
    if any(later < earlier for earlier, later in zip(attempts, attempts[1:], strict=False)):
        raise UpdateReceiptError("invalid_order", "update attempts must be chronological")
    for value, field in (
        (state.legacy_successful_at, "last_update_at"),
        (state.last_doctor_at, "last_doctor_at"),
    ):
        if value is not None and parsed_time(value, field) > current + FUTURE_SKEW:
            raise UpdateReceiptError("future_timestamp", f"{field} is forged in the future")
    all_times: list[datetime] = []
    for run in validated:
        all_times.append(parsed_time(run.attempted_at, "attempted_at"))
        for value, field in ((run.completed_at, "completed_at"), (run.successful_at, "successful_at")):
            if value is not None:
                all_times.append(parsed_time(value, field))
    if any(value > current + FUTURE_SKEW for value in all_times):
        raise UpdateReceiptError("future_timestamp", "update receipt timestamp is forged in the future")
    return state


def project_update_status(state: UpdateReceiptState, now: datetime) -> UpdateProjection:
    state = validate_receipt_state(state, now)
    current = now.astimezone(UTC)
    if not state.runs:
        return UpdateProjection("legacy-success" if state.legacy_successful_at else "none", "", None, None, None, state.legacy_successful_at)
    latest = state.runs[-1]
    attempted = parsed_time(latest.attempted_at, "attempted_at")
    if latest.completed_at is None:
        state_name: Literal["in-progress", "stale"] = "stale" if current - attempted > STALE_AFTER else "in-progress"
        return UpdateProjection(state_name, latest.run_id, latest.attempted_at, None, None, None)
    state_name: Literal["succeeded", "failed"] = "succeeded" if latest.exit_code == 0 else "failed"
    return UpdateProjection(
        state_name, latest.run_id, latest.attempted_at, latest.completed_at, latest.exit_code, latest.successful_at
    )
