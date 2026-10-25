#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# How to run:
#   python3 scripts/test_doctor_runtime.py --case drift-failed-update-and-recovery-required

from __future__ import annotations

import math

from agent_company_deps import JsonValue
from agent_company_runtime_values import issue
from agent_company_status_models import LaunchdStatus, LogStatus, StatusContractError


KNOWN_LAUNCHD_STATES = frozenset({"running", "waiting", "not running", "exited", "unknown", "unobserved"})


def validate_log_status(log: LogStatus, field: str) -> None:
    if not isinstance(log, LogStatus):
        raise StatusContractError("invalid_status_payload", field)
    if type(log.present) is not bool or type(log.fresh) is not bool:
        raise StatusContractError("invalid_status_payload", field)
    if log.age_seconds is not None and (type(log.age_seconds) is not int or log.age_seconds < 0):
        raise StatusContractError("invalid_status_payload", field)
    if log.mtime_epoch is not None and (
        isinstance(log.mtime_epoch, bool)
        or not isinstance(log.mtime_epoch, int | float)
        or not math.isfinite(log.mtime_epoch)
    ):
        raise StatusContractError("invalid_status_payload", field)
    if log.size_bytes is not None and (type(log.size_bytes) is not int or log.size_bytes < 0):
        raise StatusContractError("invalid_status_payload", field)
    if log.integrity not in {"ok", "missing", "stale", "unsafe", "future", "unobserved"}:
        raise StatusContractError("invalid_status_payload", field)
    if log.integrity == "ok" and not (log.present and log.fresh and log.age_seconds is not None and log.mtime_epoch is not None):
        raise StatusContractError("invalid_status_payload", field)
    if log.integrity == "stale" and not (log.present and not log.fresh and log.age_seconds is not None and log.mtime_epoch is not None):
        raise StatusContractError("invalid_status_payload", field)
    if log.integrity == "missing" and (
        log.present or log.fresh or log.age_seconds is not None or log.mtime_epoch is not None
        or log.size_bytes is not None
    ):
        raise StatusContractError("invalid_status_payload", field)
    if log.integrity == "unobserved" and (
        log.present or log.fresh or log.age_seconds is not None or log.mtime_epoch is not None
        or log.size_bytes is not None
    ):
        raise StatusContractError("invalid_status_payload", field)
    if log.integrity in {"unsafe", "future"} and (not log.present or log.fresh):
        raise StatusContractError("invalid_status_payload", field)


def validate_launchd_status(value: LaunchdStatus) -> LaunchdStatus:
    for field in (
        value.observed, value.user_plist_present, value.loaded, value.running,
        value.calendar_scheduled,
        value.privacy_sanitized, value.logs_fresh,
    ):
        if type(field) is not bool:
            raise StatusContractError("invalid_status_payload", "launchd_boolean")
    if value.last_exit is not None and type(value.last_exit) is not int:
        raise StatusContractError("invalid_status_payload", "last_exit")
    if not isinstance(value.state, str) or value.state not in KNOWN_LAUNCHD_STATES:
        raise StatusContractError("invalid_status_payload", "launchd_state")
    if value.plist_integrity not in {"ok", "missing", "unsafe", "unobserved"}:
        raise StatusContractError("invalid_status_payload", "plist_integrity")
    validate_log_status(value.stdout_log, "stdout_log")
    validate_log_status(value.stderr_log, "stderr_log")
    if value.logs_fresh != (value.stdout_log.fresh and value.stderr_log.fresh):
        raise StatusContractError("invalid_status_payload", "logs_fresh")
    if not value.observed:
        if (
            value.user_plist_present or value.plist_integrity != "unobserved" or value.loaded or value.running
            or value.calendar_scheduled
            or value.privacy_sanitized
            or value.state not in {"unknown", "unobserved"}
            or value.stdout_log.integrity != "unobserved" or value.stderr_log.integrity != "unobserved"
        ):
            raise StatusContractError("invalid_status_payload", "unobserved_launchd")
        return value
    if value.plist_integrity == "unobserved":
        raise StatusContractError("invalid_status_payload", "plist_integrity")
    if value.plist_integrity in {"ok", "unsafe"} and not value.user_plist_present:
        raise StatusContractError("invalid_status_payload", "plist_integrity")
    if value.plist_integrity == "missing" and value.user_plist_present:
        raise StatusContractError("invalid_status_payload", "plist_integrity")
    if value.stdout_log.integrity == "unobserved" or value.stderr_log.integrity == "unobserved":
        raise StatusContractError("invalid_status_payload", "launchd_logs")
    if value.running != (value.loaded and value.state == "running"):
        raise StatusContractError("invalid_status_payload", "launchd_running")
    return value


def project_launchd_status(
    value: LaunchdStatus,
    *,
    allow_stale_empty_stderr: bool = False,
) -> list[JsonValue]:
    try:
        launchd = validate_launchd_status(value)
    except StatusContractError:
        return [issue("launchd_corrupt", "launchd status cross-field contract is invalid")]
    issues: list[JsonValue] = []
    if launchd.last_exit not in {None, 0}:
        issues.append(issue("failed_update", f"last launchd update exited {launchd.last_exit}"))
    if not launchd.observed:
        return issues
    if launchd.plist_integrity == "unsafe":
        issues.append(issue("launchd_corrupt", "launchd observation has an unsafe plist"))
    elif not launchd.user_plist_present:
        issues.append(issue("launchd_plist_drift", "launchd plist is missing"))
    healthy_idle = launchd.calendar_scheduled and launchd.state in {"waiting", "not running", "exited"}
    if (
        not launchd.loaded
        or launchd.state == "unknown"
        or launchd.last_exit is None
        or (launchd.state != "running" and not healthy_idle)
    ):
        issues.append(issue("launchd_observation_drift", "launchd state or last-exit observation is incomplete"))
    for log_name, log in (("stdout", launchd.stdout_log), ("stderr", launchd.stderr_log)):
        if log.integrity in {"unsafe", "future"}:
            issues.append(issue("launchd_corrupt", "launchd log metadata is unsafe"))
        elif log.integrity in {"missing", "stale"}:
            if log_name == "stderr" and log.integrity == "stale" and allow_stale_empty_stderr:
                continue
            issues.append(issue("launchd_log_drift", "launchd logs are missing or stale"))
    return issues
