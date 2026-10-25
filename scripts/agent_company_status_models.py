#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Imported by agent_company_status_checks.py.
# 2. Tests: python3 scripts/test_doctor_runtime.py.
# 3. Untrusted runtime JSON is parsed once into frozen values.
# ─────────────────

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Final, Literal, final, override

from agent_company_deps import JsonValue
from agent_company_update_receipts import UpdateReceiptError, UpdateReceiptState, parse_update_status


COMMIT: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
DIGEST: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


@final
class StatusContractError(Exception):
    code: str
    field: str

    def __init__(self, code: str, field: str) -> None:
        super().__init__(code, field)
        self.code = code
        self.field = field

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.field}"


@dataclass(frozen=True, slots=True)
class RepoStatus:
    commit: str
    content_sha256: str
    worktree_status: Literal["clean", "dirty"]


@dataclass(frozen=True, slots=True)
class InstallStatus:
    installed_ref: str
    installed_content_sha256: str
    hash_status: Literal["ok", "fail"]
    managed_agent_count: int


@dataclass(frozen=True, slots=True)
class LogStatus:
    present: bool
    fresh: bool
    age_seconds: int | None
    mtime_epoch: float | None
    integrity: Literal["ok", "missing", "stale", "unsafe", "future", "unobserved"]
    size_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class LaunchdStatus:
    observed: bool
    user_plist_present: bool
    plist_integrity: Literal["ok", "missing", "unsafe", "unobserved"]
    loaded: bool
    running: bool
    calendar_scheduled: bool
    state: str
    last_exit: int | None
    privacy_sanitized: bool
    logs_fresh: bool
    stdout_log: LogStatus
    stderr_log: LogStatus


@dataclass(frozen=True, slots=True)
class IssueStatus:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class RuntimeStatusInput:
    repo: RepoStatus
    install: InstallStatus
    launchd: LaunchdStatus
    updates: UpdateReceiptState
    issues: tuple[IssueStatus, ...]


def mapping(value: JsonValue, field: str) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return value
    raise StatusContractError("invalid_status_payload", field)


def text(values: dict[str, JsonValue], field: str) -> str:
    value = values.get(field)
    if isinstance(value, str) and value:
        return value
    raise StatusContractError("invalid_status_payload", field)


def boolean(values: dict[str, JsonValue], field: str) -> bool:
    value = values.get(field)
    if type(value) is bool:
        return value
    raise StatusContractError("invalid_status_payload", field)


def integer(values: dict[str, JsonValue], field: str, *, optional: bool = False) -> int | None:
    value = values.get(field)
    if optional and value is None:
        return None
    if type(value) is int:
        return value
    raise StatusContractError("invalid_status_payload", field)


def worktree_status(value: str) -> Literal["clean", "dirty"]:
    if value == "clean":
        return "clean"
    if value == "dirty":
        return "dirty"
    raise StatusContractError("invalid_status_payload", "worktree_status")


def hash_status_value(value: str) -> Literal["ok", "fail"]:
    if value == "ok":
        return "ok"
    if value == "fail":
        return "fail"
    raise StatusContractError("invalid_status_payload", "hash_status")


def log_integrity(value: str) -> Literal["ok", "missing", "stale", "unsafe", "future", "unobserved"]:
    if value == "ok":
        return "ok"
    if value == "missing":
        return "missing"
    if value == "stale":
        return "stale"
    if value == "unsafe":
        return "unsafe"
    if value == "future":
        return "future"
    if value == "unobserved":
        return "unobserved"
    raise StatusContractError("invalid_status_payload", "log_integrity")


def plist_integrity_value(value: str) -> Literal["ok", "missing", "unsafe", "unobserved"]:
    if value == "ok":
        return "ok"
    if value == "missing":
        return "missing"
    if value == "unsafe":
        return "unsafe"
    if value == "unobserved":
        return "unobserved"
    raise StatusContractError("invalid_status_payload", "plist_integrity")


def parse_repo(payload: dict[str, JsonValue]) -> RepoStatus:
    values = mapping(payload.get("repo"), "repo")
    commit, digest = text(values, "commit"), text(values, "content_sha256")
    if COMMIT.fullmatch(commit) is None or DIGEST.fullmatch(digest) is None:
        raise StatusContractError("invalid_status_payload", "repo")
    return RepoStatus(commit, digest, worktree_status(text(values, "worktree_status")))


def parse_install(payload: dict[str, JsonValue]) -> InstallStatus:
    values = mapping(payload.get("install"), "install")
    installed_ref = text(values, "installed_ref")
    digest = text(values, "installed_content_sha256")
    count = integer(values, "managed_agent_count")
    if COMMIT.fullmatch(installed_ref) is None or DIGEST.fullmatch(digest) is None or count is None:
        raise StatusContractError("invalid_status_payload", "install")
    return InstallStatus(installed_ref, digest, hash_status_value(text(values, "hash_status")), count)


def number(values: dict[str, JsonValue], field: str) -> float | None:
    value = values.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise StatusContractError("invalid_status_payload", field)
    return float(value)


def parse_log(value: JsonValue, field: str) -> LogStatus:
    values = mapping(value, field)
    present, fresh = boolean(values, "present"), boolean(values, "fresh")
    age = integer(values, "age_seconds", optional=True)
    modified = number(values, "mtime_epoch")
    size = integer(values, "size_bytes", optional=True)
    if age is not None and age < 0:
        raise StatusContractError("invalid_status_payload", field)
    if size is not None and size < 0:
        raise StatusContractError("invalid_status_payload", field)
    return LogStatus(present, fresh, age, modified, log_integrity(text(values, "integrity")), size)


def parse_launchd(payload: dict[str, JsonValue]) -> LaunchdStatus:
    values = mapping(payload.get("launchd"), "launchd")
    observed = boolean(values, "observed")
    present = boolean(values, "user_plist_present")
    plist_integrity = plist_integrity_value(text(values, "plist_integrity"))
    loaded, running = boolean(values, "loaded"), boolean(values, "running")
    calendar_scheduled = boolean(values, "calendar_scheduled")
    state = text(values, "state")
    last_exit = integer(values, "last_exit", optional=True)
    privacy_sanitized = boolean(values, "privacy_sanitized")
    logs_fresh = boolean(values, "logs_fresh")
    stdout_log = parse_log(values.get("stdout_log"), "stdout_log")
    stderr_log = parse_log(values.get("stderr_log"), "stderr_log")
    if running and not loaded:
        raise StatusContractError("invalid_status_payload", "launchd")
    return LaunchdStatus(
        observed, present, plist_integrity, loaded, running, calendar_scheduled, state, last_exit,
        privacy_sanitized, logs_fresh, stdout_log, stderr_log,
    )


def parse_issues(payload: dict[str, JsonValue]) -> tuple[IssueStatus, ...]:
    raw = payload.get("issues")
    if not isinstance(raw, list):
        raise StatusContractError("invalid_status_payload", "issues")
    issues: list[IssueStatus] = []
    for item in raw:
        values = mapping(item, "issue_entry")
        inner = mapping(values.get("issue"), "issue")
        issues.append(IssueStatus(text(inner, "code"), text(inner, "message")))
    return tuple(issues)


def parse_runtime_status(payload: dict[str, JsonValue]) -> RuntimeStatusInput:
    if payload.get("schema_version") != "0.2" or payload.get("check") != "runtime":
        raise StatusContractError("invalid_status_payload", "schema_version")
    state = mapping(payload.get("state"), "state")
    timestamps = mapping(state.get("timestamps"), "timestamps")
    try:
        updates = parse_update_status(timestamps)
    except UpdateReceiptError as exc:
        raise StatusContractError(exc.code, "timestamps") from exc
    return RuntimeStatusInput(parse_repo(payload), parse_install(payload), parse_launchd(payload), updates, parse_issues(payload))
