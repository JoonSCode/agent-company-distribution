#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Run directly: python3 scripts/agent_company_launchd.py
# 2. Runtime callers inject process and clock adapters in tests.
# 3. This surface only observes launchd and log metadata.
# ─────────────────

from __future__ import annotations

import os
import math
import plistlib
import stat
from pathlib import Path
from typing import Final

from agent_company_deps import JsonValue
from agent_company_install_types import InstallError
from agent_company_launchd_contract import (
    LAUNCHD_LABEL,
    Clock,
    CommandResult,
    LaunchdConfig,
    LaunchdContractError,
    LaunchdPaths,
    LaunchdTarget,
    ProcessAdapter,
    ProcessOutput,
    SystemClock,
    SystemProcess,
    validated_clock,
)
from agent_company_launchd_install import rendered_plist
from agent_company_launchd_output import LaunchdOutputError, parse_launchctl
from agent_company_runtime_values import int_field


ROOT: Final[Path] = Path(__file__).resolve().parents[1]
LAUNCHD_TEMPLATE: Final[Path] = ROOT / "launchd" / f"{LAUNCHD_LABEL}.plist"
DEFAULT_STALE_SECONDS: Final[int] = 25 * 60 * 60
FUTURE_SKEW_SECONDS: Final[int] = 5 * 60
__all__ = [
    "Clock",
    "CommandResult",
    "LaunchdConfig",
    "LaunchdContractError",
    "LaunchdPaths",
    "LaunchdTarget",
    "ProcessAdapter",
    "ProcessOutput",
    "launchd_report",
]


def default_paths() -> LaunchdPaths:
    return LaunchdPaths(
        Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist",
        Path("/private/tmp/agent-company-update.out.log"),
        Path("/private/tmp/agent-company-update.err.log"),
    )


def launchd_config(*, observe_live: bool = True) -> LaunchdConfig:
    return LaunchdConfig(default_paths(), SystemProcess(), SystemClock(), DEFAULT_STALE_SECONDS, observe_live)


def log_report(path: Path, *, now: float, stale_seconds: float) -> dict[str, JsonValue]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {
            "path": str(path), "present": False, "fresh": False, "age_seconds": None,
            "mtime_epoch": None, "integrity": "missing",
        }
    except OSError:
        return {
            "path": str(path), "present": True, "fresh": False, "age_seconds": None,
            "mtime_epoch": None, "integrity": "unsafe",
        }
    mode = stat.S_IMODE(metadata.st_mode)
    if (
        stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid() or metadata.st_nlink != 1 or mode != 0o600
    ):
        return {
            "path": str(path), "present": True, "fresh": False, "age_seconds": None,
            "mtime_epoch": None, "integrity": "unsafe",
        }
    modified = metadata.st_mtime
    if not math.isfinite(modified) or modified > now + FUTURE_SKEW_SECONDS:
        return {
            "path": str(path), "present": True, "fresh": False, "age_seconds": None,
            "mtime_epoch": modified if math.isfinite(modified) else None, "integrity": "future",
        }
    age = max(0, int(now - modified))
    fresh = age <= stale_seconds
    return {
        "path": str(path), "present": True, "fresh": fresh, "age_seconds": age,
        "mtime_epoch": modified, "integrity": "ok" if fresh else "stale",
    }


def calendar_contract(content: bytes) -> bool:
    try:
        parsed = plistlib.loads(content)
    except plistlib.InvalidFileException:
        return False
    if not isinstance(parsed, dict):
        return False
    interval = parsed.get("StartCalendarInterval")
    return (
        isinstance(interval, dict)
        and type(interval.get("Hour")) is int
        and type(interval.get("Minute")) is int
    )


def plist_report(path: Path) -> tuple[bool, str, bool]:
    try:
        expected = rendered_plist()
    except InstallError:
        return True, "unsafe", False
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return False, "missing", False
    except OSError:
        return True, "unsafe", False
    try:
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            content = stream.read()
    except OSError:
        return True, "unsafe", False
    mode = stat.S_IMODE(metadata.st_mode)
    safe = (
        stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode)
        and metadata.st_uid == os.geteuid() and metadata.st_nlink == 1 and mode in {0o600, 0o644}
        and content == expected
    )
    return True, "ok" if safe else "unsafe", safe and calendar_contract(content)


def run_process(config: LaunchdConfig) -> ProcessOutput:
    try:
        return config.process.run(("launchctl", "print", config.target.reference))
    except (AttributeError, TypeError) as exc:
        raise LaunchdContractError("invalid_process", "launchd process observation failed") from exc


def launchd_report(
    persisted: dict[str, JsonValue] | None = None,
    *,
    config: LaunchdConfig | None = None,
) -> dict[str, JsonValue]:
    selected = config if config is not None else launchd_config()
    now, stale_seconds = validated_clock(selected)
    observed_paths = selected.paths
    output = (
        run_process(selected)
        if selected.observe_live
        else CommandResult(1, "", "live launchd observation skipped for isolated CODEX_HOME")
    )
    try:
        returncode, stdout, stderr = output.returncode, output.stdout, output.stderr
    except AttributeError as exc:
        raise LaunchdContractError("invalid_process_output", "process output fields are missing") from exc
    if type(returncode) is not int or not isinstance(stdout, str) or not isinstance(stderr, str):
        raise LaunchdContractError("invalid_process_output", "process output types are invalid")
    try:
        parsed = parse_launchctl(stdout, stderr, selected.target)
    except LaunchdOutputError as exc:
        raise LaunchdContractError(
            "invalid_process_output",
            "launchd process output must be bounded UTF-8 text",
        ) from exc
    state, live_exit = parsed.state, parsed.last_exit
    safe_stderr, privacy_sanitized = parsed.safe_stderr, parsed.privacy_sanitized
    if persisted is None:
        stored: dict[str, JsonValue] = {}
    elif type(persisted) is dict:
        stored = persisted
    else:
        raise LaunchdContractError("invalid_persisted", "persisted state must be an exact mapping")
    raw_stored_exit = stored.get("last_update_exit")
    if raw_stored_exit is not None and type(raw_stored_exit) is not int:
        raise LaunchdContractError("invalid_persisted_exit", "persisted exit must be an integer")
    stored_exit = int_field(stored, "last_update_exit")
    failed_stored_exit = stored_exit if stored_exit not in {None, 0} else None
    if failed_stored_exit is not None:
        last_exit = failed_stored_exit
    elif live_exit is not None:
        last_exit = live_exit
    elif selected.observe_live and returncode == 0:
        last_exit = None
    else:
        last_exit = stored_exit
    plist_present, plist_integrity, calendar_scheduled = (
        plist_report(observed_paths.user_plist)
        if selected.observe_live
        else (False, "unobserved", False)
    )
    if selected.observe_live:
        stdout_log = log_report(
            observed_paths.stdout_log,
            now=now,
            stale_seconds=stale_seconds,
        )
        stderr_log = log_report(
            observed_paths.stderr_log,
            now=now,
            stale_seconds=stale_seconds,
        )
    else:
        stdout_log = {
            "path": str(observed_paths.stdout_log), "present": False, "fresh": False,
            "age_seconds": None, "mtime_epoch": None, "integrity": "unobserved",
        }
        stderr_log = {
            "path": str(observed_paths.stderr_log), "present": False, "fresh": False,
            "age_seconds": None, "mtime_epoch": None, "integrity": "unobserved",
        }
    logs_fresh = bool(stdout_log["fresh"]) and bool(stderr_log["fresh"])
    return {
        "label": LAUNCHD_LABEL,
        "template": str(LAUNCHD_TEMPLATE),
        "template_present": LAUNCHD_TEMPLATE.exists(),
        "user_plist": str(observed_paths.user_plist),
        "user_plist_present": plist_present,
        "plist_integrity": plist_integrity,
        "observed": selected.observe_live,
        "loaded": returncode == 0,
        "running": returncode == 0 and state == "running",
        "calendar_scheduled": calendar_scheduled,
        "state": state,
        "last_exit": last_exit,
        "last_exit_source": "persisted" if failed_stored_exit is not None else "live" if live_exit is not None else "persisted",
        "logs_fresh": logs_fresh,
        "stdout_log": stdout_log,
        "stderr_log": stderr_log,
        "observation_error": safe_stderr.strip() if returncode != 0 or privacy_sanitized else "",
        "privacy_sanitized": privacy_sanitized,
    }


def main() -> int:
    import json

    print(json.dumps(launchd_report(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
