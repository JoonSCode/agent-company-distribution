#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/agent_company_profiles.py
# 3. Or run with system Python when stdlib-only execution is preferred:
#      python3 scripts/agent_company_profiles.py
# ─────────────────

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_company_role_authority import collect_authority_claims
from agent_company_role_schema import (
    ProfileIssue,
    as_json_object,
    collect_control_issues,
    issue,
    load_json_file,
    validate_profile_shape,
)


@dataclass(frozen=True, slots=True)
class ProfileCheck:
    status: str
    check: str
    profiles_dir: str
    profile_count: int
    valid_profile_count: int
    errors: list[ProfileIssue]


def validate_profile_file(path: Path) -> tuple[bool, list[ProfileIssue]]:
    parsed, load_issue = load_json_file(path)
    if load_issue is not None:
        return False, [load_issue]
    if parsed is None:
        return False, [issue(path, "$", "invalid_json", "profile did not parse")]
    profile = as_json_object(parsed)
    if profile is None:
        return False, [issue(path, "$", "invalid_profile_shape", "profile root must be an object")]
    errors = validate_profile_shape(path, profile)
    errors.extend(collect_control_issues(path, "$", profile))
    errors.extend(collect_authority_claims(path, "$", profile))
    return not errors, errors


def check_profiles(profiles_dir: Path) -> ProfileCheck:
    try:
        profile_paths = sorted(path for path in profiles_dir.glob("*.json") if path.is_file())
    except OSError as exc:
        error = ProfileIssue(str(profiles_dir), "$", "profiles_dir_error", f"could not list profiles: {exc}")
        return ProfileCheck("fail", "profiles", str(profiles_dir), 0, 0, [error])
    errors: list[ProfileIssue] = []
    valid_count = 0
    if not profile_paths:
        errors.append(ProfileIssue(str(profiles_dir), "$", "missing_profiles", "no profile JSON files found"))
    for path in profile_paths:
        is_valid, profile_errors = validate_profile_file(path)
        if is_valid:
            valid_count += 1
        errors.extend(profile_errors)
    status = "ok" if not errors else "fail"
    return ProfileCheck(status, "profiles", str(profiles_dir), len(profile_paths), valid_count, errors)
