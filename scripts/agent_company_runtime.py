#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Run through scripts/doctor.py --json.
# 2. Use runtime_report() for read-only status projection.
# 3. Tests inject launchd process and clock adapters.
# ─────────────────

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from agent_company_deps import JsonValue
from agent_company_install_io import read_json, write_json
from agent_company_install_types import InstallError
from agent_company_launchd import LaunchdConfig, LaunchdContractError, launchd_config, launchd_report
from agent_company_runtime_install import installed_report
from agent_company_runtime_source import source_report
from agent_company_runtime_values import (
    RuntimePaths,
    issue,
    map_field,
    runtime_paths,
    status_from_issues,
    text_field,
)
from agent_company_sync_guard import disallowed_sync_files


ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DEFAULT_STALE_SECONDS: Final[int] = 3600


@dataclass(frozen=True, slots=True)
class RuntimeAdapters:
    launchd: LaunchdConfig | None = None


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def lock_report(paths: RuntimePaths) -> tuple[dict[str, JsonValue], list[JsonValue]]:
    lock = paths.state / "install.lock"
    if not lock.exists():
        return {"status": "absent", "path": str(lock), "stale": False}, []
    raw_seconds = os.environ.get("AGENT_COMPANY_LOCK_STALE_SECONDS", str(DEFAULT_STALE_SECONDS))
    try:
        stale_seconds = int(raw_seconds)
        age = int(time.time() - lock.stat().st_mtime)
    except ValueError:
        return {"status": "present", "path": str(lock), "stale": False}, [
            issue("malformed_input", "AGENT_COMPANY_LOCK_STALE_SECONDS must be an integer", lock)
        ]
    except OSError as exc:
        return {"status": "unknown", "path": str(lock), "stale": False}, [
            issue("stale_state", f"could not inspect lock: {exc}", lock)
        ]
    stale = stale_seconds < 0 or age > stale_seconds
    report: dict[str, JsonValue] = {
        "status": "present",
        "path": str(lock),
        "age_seconds": age,
        "stale": stale,
    }
    if stale:
        return report, [issue("stale_lock", f"install lock is stale after {age} seconds", lock)]
    return report, []


def device_identity(paths: RuntimePaths, *, write_file: bool) -> dict[str, JsonValue]:
    device_path = paths.state / "device.json"
    stored: dict[str, JsonValue] | None = None
    if device_path.exists():
        try:
            stored = read_json(device_path)
        except InstallError:
            stored = None
    if stored is not None:
        return stored
    env_id = os.environ.get("AGENT_COMPANY_DEVICE_ID", "")
    source = env_id or str(paths.root)
    payload: dict[str, JsonValue] = {
        "schema_version": "0.1",
        "device_id": hashlib.sha256(source.encode()).hexdigest()[:16],
        "codex_home": str(paths.codex_home),
    }
    if write_file:
        try:
            write_json(device_path, payload)
        except InstallError:
            payload["status_error"] = "unsafe_device_state"
    return payload


def write_timestamp(paths: RuntimePaths, field: str) -> str:
    paths.state.mkdir(parents=True, exist_ok=True)
    status_path = paths.state / "status.json"
    try:
        payload = read_json(status_path) if status_path.exists() else {}
    except InstallError:
        payload = {}
    timestamp = now_iso()
    payload[field] = timestamp
    write_json(status_path, payload)
    return timestamp


def state_timestamps(paths: RuntimePaths) -> tuple[dict[str, JsonValue], list[JsonValue]]:
    status_path = paths.state / "status.json"
    if not status_path.exists():
        return {}, []
    try:
        return read_json(status_path), []
    except InstallError:
        return {}, [issue("unsafe_runtime_state", "runtime status is malformed or unsafe", status_path)]



def rollback_report(paths: RuntimePaths) -> dict[str, JsonValue]:
    current = paths.rollback / "current"
    legacy = paths.rollback / "previous-active.json"
    return {"present": current.exists() or legacy.exists(), "path": str(current if current.exists() else legacy)}


def unavailable_launchd_report() -> dict[str, JsonValue]:
    log: dict[str, JsonValue] = {
        "present": False,
        "fresh": False,
        "age_seconds": None,
        "mtime_epoch": None,
        "size_bytes": None,
        "integrity": "unobserved",
    }
    return {
        "observed": False,
        "user_plist_present": False,
        "plist_integrity": "unobserved",
        "loaded": False,
        "running": False,
        "calendar_scheduled": False,
        "state": "unobserved",
        "last_exit": None,
        "privacy_sanitized": False,
        "logs_fresh": False,
        "stdout_log": dict(log),
        "stderr_log": dict(log),
    }


def runtime_report(
    codex_home: Path | None = None,
    *,
    write_doctor_timestamp: bool,
    adapters: RuntimeAdapters | None = None,
) -> dict[str, JsonValue]:
    paths = runtime_paths(codex_home)
    repo, source_issues = source_report()
    installed, installed_issues = installed_report(paths)
    lock, lock_issues = lock_report(paths)
    timestamps, timestamp_issues = state_timestamps(paths)
    journal = paths.state / "install-transaction.json"
    recovery_issues = [issue("recovery_required", "unfinished install transaction requires recovery", journal)] if journal.exists() else []
    issues = [
        *source_issues,
        *installed_issues,
        *lock_issues,
        *timestamp_issues,
        *recovery_issues,
        *disallowed_sync_files(ROOT, paths.root),
    ]
    if write_doctor_timestamp and not timestamp_issues:
        try:
            timestamps["last_doctor_at"] = write_timestamp(paths, "last_doctor_at")
        except InstallError:
            issues.append(issue("unsafe_runtime_state", "doctor timestamp target is unsafe"))
    selected = adapters if adapters is not None else RuntimeAdapters()
    live_home = paths.codex_home == Path.home() / ".codex"
    selected_launchd = selected.launchd if selected.launchd is not None else launchd_config(observe_live=live_home)
    try:
        launchd = launchd_report(timestamps, config=selected_launchd)
    except LaunchdContractError:
        launchd = unavailable_launchd_report()
        issues.append(issue("launchd_corrupt", "launchd observation contract failed"))
    state: dict[str, JsonValue] = {
        "device": device_identity(paths, write_file=write_doctor_timestamp),
        "timestamps": timestamps,
        "lock": lock,
        "rollback_snapshot": rollback_report(paths),
    }
    agent_ref = text_field(repo, "commit")
    installed_ref = text_field(installed, "installed_ref")
    return {
        "schema_version": "0.2",
        "check": "runtime",
        "status": status_from_issues(issues),
        "agent_company_ref": agent_ref,
        "source_head": agent_ref,
        "source_content_sha256": text_field(repo, "content_sha256"),
        "runtime_contract": text_field(installed, "runtime_contract"),
        "runtime_certification": text_field(installed, "runtime_certification"),
        "installed_ref": installed_ref,
        "installed_manifest_commit": installed_ref,
        "installed_content_sha256": text_field(installed, "installed_content_sha256"),
        "last_attempted_update": text_field(timestamps, "last_attempted_update"),
        "last_successful_update": text_field(timestamps, "last_successful_update")
        or text_field(timestamps, "last_update_at"),
        "repo": repo,
        "external_dependencies": [],
        "install": installed,
        "launchd": launchd,
        "state": state,
        "issues": issues,
    }


__all__ = [
    "JsonValue",
    "RuntimeAdapters",
    "RuntimePaths",
    "issue",
    "map_field",
    "runtime_paths",
    "runtime_report",
    "status_from_issues",
    "text_field",
]
