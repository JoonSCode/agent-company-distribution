#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Run: python3 scripts/sync-status.py --json.
# 2. Pass repeated --device-home for bounded local comparisons.
# 3. This module never mutates registry or launchd state.
# ─────────────────

from __future__ import annotations

from pathlib import Path
from typing import Final

from agent_company_deps import JsonValue
from agent_company_runtime import runtime_paths, runtime_report
from agent_company_runtime_values import issue, list_field, map_field, text_field
from agent_company_status_checks import enrich_runtime_status


SEVERITY_ORDER: Final[tuple[str, ...]] = ("fresh", "dirty-derived", "drifted", "failed-update", "corrupt")


def device_report(codex_home: Path) -> dict[str, JsonValue]:
    payload = enrich_runtime_status(runtime_report(codex_home, write_doctor_timestamp=False))
    state = map_field(payload, "state")
    device = map_field(state, "device")
    install = map_field(payload, "install")
    return {
        "device_id": text_field(device, "device_id"),
        "codex_home": str(codex_home),
        "status": text_field(payload, "status"),
        "severity": text_field(payload, "severity"),
        "material_failure": payload.get("material_failure") is True,
        "reproducible": payload.get("reproducible") is True,
        "source_head": text_field(payload, "source_head"),
        "source_content_sha256": text_field(payload, "source_content_sha256"),
        "installed_ref": text_field(install, "installed_ref"),
        "installed_manifest_commit": text_field(payload, "installed_manifest_commit"),
        "installed_content_sha256": text_field(install, "installed_content_sha256"),
        "last_attempted_update": text_field(payload, "last_attempted_update"),
        "last_successful_update": text_field(payload, "last_successful_update"),
        "resolved_king_sejong_ref": text_field(install, "resolved_king_sejong_ref")
        or text_field(payload, "resolved_king_sejong_ref"),
        "king_sejong_dependency_mode": text_field(install, "king_sejong_dependency_mode")
        or text_field(payload, "king_sejong_dependency_mode"),
        "managed_agent_count": install.get("managed_agent_count"),
        "launchd": map_field(payload, "launchd"),
        "timestamps": map_field(state, "timestamps"),
        "warnings": list_field(payload, "warnings"),
        "issues": list_field(payload, "issues"),
        "remediation": text_field(payload, "remediation"),
    }


def drift_issues(devices: list[dict[str, JsonValue]]) -> list[JsonValue]:
    issues: list[JsonValue] = []
    for field in ("installed_ref", "installed_content_sha256", "resolved_king_sejong_ref"):
        values = {text_field(device, field) for device in devices if text_field(device, field)}
        if len(values) > 1:
            issues.append(issue("version_drift", f"{field} differs across devices"))
    return issues


def highest_severity(devices: list[dict[str, JsonValue]], *, cross_device_drift: bool) -> str:
    severities = {text_field(device, "severity") for device in devices}
    if cross_device_drift:
        severities.add("drifted")
    return max((value for value in severities if value in SEVERITY_ORDER), key=SEVERITY_ORDER.index, default="fresh")


def sync_status(codex_homes: list[Path]) -> dict[str, JsonValue]:
    homes = codex_homes or [runtime_paths().codex_home]
    devices = [device_report(home) for home in homes]
    cross_issues = drift_issues(devices)
    issues = [*cross_issues]
    warnings: list[JsonValue] = []
    for device in devices:
        issues.extend(list_field(device, "issues"))
        warnings.extend(list_field(device, "warnings"))
    severity = highest_severity(devices, cross_device_drift=bool(cross_issues))
    material = severity in {"drifted", "failed-update", "corrupt"}
    status = "fail" if material else "ok"
    return {
        "schema_version": "0.2",
        "report": "agent_company_sync_status",
        "status": status,
        "severity": severity,
        "material_failure": material,
        "device_count": len(devices),
        "devices": devices,
        "issues": issues,
        "warnings": warnings,
        "launchd": map_field(devices[0], "launchd") if devices else {},
    }
