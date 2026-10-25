#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Use through doctor.py or sync-status.py.
# 2. Run focused coverage: python3 scripts/test_doctor_runtime.py.
# 3. Runtime JSON is parsed into frozen models before projection.
# ─────────────────

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Final, Literal, assert_never

from agent_company_deps import JsonValue
from agent_company_privacy import PrivacyError, reject_sensitive
from agent_company_runtime_values import issue
from agent_company_status_models import RuntimeStatusInput, StatusContractError, parse_runtime_status
from agent_company_status_validation import project_launchd_status
from agent_company_update_receipts import UpdateProjection, UpdateReceiptError, project_update_status


type Severity = Literal["fresh", "drifted", "dirty-derived", "failed-update", "corrupt"]

EXPECTED_MANAGED_AGENTS: Final[int] = 6
FUTURE_SKEW: Final[timedelta] = timedelta(minutes=5)
CORRUPT_CODES: Final = frozenset(
    {
        "corrupt_hash", "dependency_resolution_failed", "disallowed_sync_file", "hash_mismatch",
        "invalid_status_payload", "invalid_timestamp", "future_timestamp", "invalid_order", "invalid_exit",
        "launchd_corrupt", "malformed_hashes", "malformed_index", "malformed_input", "malformed_status",
        "managed_agent_count", "managed_agent_drift", "managed_drift", "missing_hashes", "missing_installed_file",
        "missing_managed_agent", "missing_managed_index", "missing_manifest", "mixed_generation", "not_installed",
        "recovery_required", "source_unavailable", "stale_lock", "stale_state", "unexpected_managed_agent",
        "unsafe_runtime_state",
    }
)
DRIFT_CODES: Final = frozenset(
    {
        "content_drift", "launchd_log_drift", "launchd_observation_drift", "launchd_plist_drift",
        "ref_drift", "update_in_progress", "update_receipt_missing", "version_drift",
    }
)


def append_issue(issues: list[JsonValue], code: str, message: str) -> None:
    existing = {
        nested.get("code")
        for value in issues
        if isinstance(value, dict) and isinstance(nested := value.get("issue"), dict)
    }
    if code not in existing:
        issues.append(issue(code, message))


def base_issues(parsed: RuntimeStatusInput) -> list[JsonValue]:
    return [issue(value.code, value.message) for value in parsed.issues]


def provenance_issues(parsed: RuntimeStatusInput) -> list[JsonValue]:
    issues: list[JsonValue] = []
    if parsed.repo.commit != parsed.install.installed_ref:
        append_issue(issues, "version_drift", "installed manifest commit differs from source HEAD")
    if parsed.repo.content_sha256 != parsed.install.installed_content_sha256:
        append_issue(issues, "content_drift", "installed content digest differs from source content digest")
    return issues


def integrity_issues(parsed: RuntimeStatusInput) -> list[JsonValue]:
    issues: list[JsonValue] = []
    if parsed.install.hash_status != "ok":
        append_issue(issues, "corrupt_hash", "installed content hash verification failed")
    if parsed.install.managed_agent_count != EXPECTED_MANAGED_AGENTS:
        append_issue(
            issues,
            "managed_agent_count",
            f"expected {EXPECTED_MANAGED_AGENTS} verified managed agents, observed {parsed.install.managed_agent_count}",
        )
    return issues


def update_issues(projection: UpdateProjection) -> list[JsonValue]:
    match projection.state:
        case "failed":
            return [issue("failed_update", f"last scheduled update exited {projection.exit_code}")]
        case "stale":
            return [issue("failed_update", "latest scheduled update attempt is stale and incomplete")]
        case "in-progress":
            return [issue("update_in_progress", "latest scheduled update attempt has no matching result")]
        case "none":
            return [issue("update_receipt_missing", "no successful update receipt is available")]
        case "legacy-success" | "succeeded":
            return []
        case unreachable:
            assert_never(unreachable)


def temporal_log_issues(parsed: RuntimeStatusInput, projection: UpdateProjection, now: datetime) -> list[JsonValue]:
    if not parsed.launchd.observed or projection.attempted_at is None:
        return []
    attempted = datetime.fromisoformat(projection.attempted_at.replace("Z", "+00:00")).astimezone(UTC)
    issues: list[JsonValue] = []
    modified_logs: list[datetime] = []
    for log in (parsed.launchd.stdout_log, parsed.launchd.stderr_log):
        if log.mtime_epoch is None:
            continue
        modified = datetime.fromtimestamp(log.mtime_epoch, UTC)
        modified_logs.append(modified)
        if modified > now + FUTURE_SKEW:
            append_issue(issues, "launchd_corrupt", "launchd log timestamp is forged in the future")
    if modified_logs and max(modified_logs) < attempted:
        append_issue(issues, "launchd_log_drift", "launchd logs predate the latest update attempt")
    return issues


def allow_stale_empty_stderr(parsed: RuntimeStatusInput, projection: UpdateProjection) -> bool:
    if (
        projection.state != "succeeded"
        or projection.exit_code != 0
        or projection.attempted_at is None
        or parsed.launchd.last_exit != 0
    ):
        return False
    stdout_log = parsed.launchd.stdout_log
    stderr_log = parsed.launchd.stderr_log
    if (
        not stdout_log.present
        or not stdout_log.fresh
        or stdout_log.integrity != "ok"
        or stdout_log.mtime_epoch is None
        or stdout_log.size_bytes is None
        or stdout_log.size_bytes == 0
        or not stderr_log.present
        or stderr_log.integrity != "stale"
        or stderr_log.size_bytes != 0
    ):
        return False
    attempted = datetime.fromisoformat(projection.attempted_at.replace("Z", "+00:00")).astimezone(UTC)
    return datetime.fromtimestamp(stdout_log.mtime_epoch, UTC) >= attempted


def sanitized_warnings(
    parsed: RuntimeStatusInput,
    *,
    allow_stale_empty_stderr_log: bool = False,
) -> list[JsonValue]:
    warning = parsed.updates.telemetry_warning
    result: list[JsonValue] = []
    if warning is not None:
        try:
            reject_sensitive(warning)
        except PrivacyError:
            result.append("telemetry warning: sanitized unsafe warning")
        else:
            result.append(warning if isinstance(warning, str) else "telemetry warning: sanitized malformed warning")
    if (
        parsed.launchd.observed
        and not parsed.launchd.logs_fresh
        and not allow_stale_empty_stderr_log
    ):
        result.append("launchd warning: update logs are stale or incomplete")
    return result


def severity_for(parsed: RuntimeStatusInput, issues: list[JsonValue]) -> Severity:
    codes = {
        nested.get("code")
        for value in issues
        if isinstance(value, dict) and isinstance(nested := value.get("issue"), dict)
    }
    if codes & CORRUPT_CODES:
        return "corrupt"
    if "failed_update" in codes:
        return "failed-update"
    if codes & DRIFT_CODES:
        return "drifted"
    return "dirty-derived" if parsed.repo.worktree_status == "dirty" else "fresh"


def status_for(severity: Severity) -> str:
    match severity:
        case "fresh":
            return "ok"
        case "dirty-derived":
            return "warning"
        case "drifted" | "failed-update" | "corrupt":
            return "fail"
        case unreachable:
            assert_never(unreachable)


def remediation_for(severity: Severity) -> str:
    match severity:
        case "fresh":
            return "none"
        case "dirty-derived":
            return "commit or restore a clean source, then run update"
        case "drifted":
            return "run scripts/update.sh and recheck sync-status"
        case "failed-update":
            return "run agent_company_installer.py recover, then scripts/update.sh"
        case "corrupt":
            return "run agent_company_installer.py recover before reinstall or rollback"
        case unreachable:
            assert_never(unreachable)


def corrupt_projection(error: StatusContractError, payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    safe_issues: list[JsonValue] = [issue(error.code, f"runtime status contract rejected {error.field}")]
    raw_issues = payload.get("issues")
    if isinstance(raw_issues, list):
        for value in raw_issues:
            if not isinstance(value, dict) or not isinstance(inner := value.get("issue"), dict):
                continue
            code = inner.get("code")
            if isinstance(code, str) and code in CORRUPT_CODES | DRIFT_CODES | {"failed_update"}:
                append_issue(safe_issues, code, f"runtime reported {code}")
    return {
        "schema_version": "0.2", "check": "runtime", "status": "fail", "severity": "corrupt",
        "material_failure": True, "reproducible": False, "dirty_derived": False,
        "issues": safe_issues, "warnings": [],
        "remediation": "run agent_company_installer.py recover before reinstall or rollback",
    }


def enrich_runtime_status(
    payload: dict[str, JsonValue],
    *,
    now: datetime | None = None,
) -> dict[str, JsonValue]:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        parsed = parse_runtime_status(payload)
        projection = project_update_status(parsed.updates, current)
    except StatusContractError as exc:
        return corrupt_projection(exc, payload)
    except UpdateReceiptError as exc:
        return corrupt_projection(StatusContractError(exc.code, "timestamps"), payload)
    stale_empty_stderr_allowed = allow_stale_empty_stderr(parsed, projection)
    issues = [
        *base_issues(parsed), *provenance_issues(parsed), *integrity_issues(parsed),
        *project_launchd_status(
            parsed.launchd,
            allow_stale_empty_stderr=stale_empty_stderr_allowed,
        ),
        *update_issues(projection),
        *temporal_log_issues(parsed, projection, current),
    ]
    severity = severity_for(parsed, issues)
    enriched = dict(payload)
    safe_warnings = sanitized_warnings(
        parsed,
        allow_stale_empty_stderr_log=stale_empty_stderr_allowed,
    )
    state = payload.get("state")
    if isinstance(state, dict):
        safe_state = dict(state)
        timestamps = state.get("timestamps")
        if isinstance(timestamps, dict) and "telemetry_warning" in timestamps:
            safe_timestamps = dict(timestamps)
            safe_timestamps["telemetry_warning"] = safe_warnings[0] if safe_warnings else "telemetry warning: sanitized warning"
            safe_state["timestamps"] = safe_timestamps
        enriched["state"] = safe_state
    enriched.update(
        {
            "issues": issues, "warnings": safe_warnings, "severity": severity,
            "status": status_for(severity), "reproducible": severity == "fresh",
            "dirty_derived": severity == "dirty-derived",
            "material_failure": severity in {"drifted", "failed-update", "corrupt"},
            "remediation": remediation_for(severity),
            "last_attempted_update": projection.attempted_at or "",
            "last_successful_update": projection.successful_at or "",
        }
    )
    return enriched


def main() -> int:
    print(json.dumps({"status": "ok", "module": "agent_company_status_checks"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
