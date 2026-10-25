#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/agent_company_role_schema.py
# 3. Or run with system Python when stdlib-only execution is preferred:
#      python3 scripts/agent_company_role_schema.py
# ─────────────────

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Final, assert_never


JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

PROFILE_SCHEMA_VERSION: Final[str] = "0.1"
PROFILE_SCHEMA_REF: Final[str] = "../policies/role-profile.schema.json"
ROLE_IDS: Final[frozenset[str]] = frozenset({"founder", "planning", "marketing", "design", "development", "qa-release"})
PROFILE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "$schema",
        "schema_version",
        "id",
        "name",
        "uses_king_sejong",
        "authority_boundary",
        "mission",
        "owns",
        "does_not_own",
        "skills",
        "memory_refs",
        "tools",
        "approval_rules",
        "handoff_shape",
        "native_agent",
    }
)
PROFILE_REQUIRED_FIELDS: Final[frozenset[str]] = PROFILE_FIELDS
HANDOFF_FIELDS: Final[frozenset[str]] = frozenset({"format", "policy_ref", "required_fields"})
HANDOFF_REQUIRED_FIELDS: Final[frozenset[str]] = HANDOFF_FIELDS
NATIVE_AGENT_FIELDS: Final[frozenset[str]] = frozenset(
    {"name", "description", "sandbox_mode", "model", "model_reasoning_effort", "nickname_candidates"}
)
NATIVE_AGENT_REQUIRED_FIELDS: Final[frozenset[str]] = frozenset({"name", "description", "sandbox_mode"})
NATIVE_SANDBOX_MODES: Final[frozenset[str]] = frozenset({"read-only", "workspace-write"})
REASONING_EFFORTS: Final[frozenset[str]] = frozenset({"minimal", "low", "medium", "high", "xhigh"})
SAFE_NICKNAME: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9 _-]+$")
SAFE_NATIVE_NAME: Final[re.Pattern[str]] = re.compile(
    r"^agent-company-(founder|planning|marketing|design|development|qa-release)$"
)
REQUIRED_LIST_FIELDS: Final[tuple[str, ...]] = (
    "owns",
    "does_not_own",
    "skills",
    "memory_refs",
    "tools",
    "approval_rules",
)


@dataclass(frozen=True, slots=True)
class ProfileIssue:
    file: str
    field: str
    code: str
    message: str


def issue(path: Path, field: str, code: str, message: str) -> ProfileIssue:
    return ProfileIssue(file=str(path), field=field, code=code, message=message)


def load_json_file(path: Path) -> tuple[JsonValue | None, ProfileIssue | None]:
    try:
        parsed: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, issue(path, "$", "missing_file", "profile file is missing")
    except json.JSONDecodeError as exc:
        return None, issue(path, "$", "invalid_json", f"invalid JSON: {exc.msg}")
    except OSError as exc:
        return None, issue(path, "$", "read_error", f"could not read file: {exc}")
    return parsed, None


def as_json_object(value: JsonValue) -> dict[str, JsonValue] | None:
    return value if isinstance(value, dict) else None


def is_nonempty_string(value: JsonValue | None) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_true(value: JsonValue | None) -> bool:
    return value is True


def is_nonempty_string_list(value: JsonValue | None) -> bool:
    return isinstance(value, list) and bool(value) and all(is_nonempty_string(item) for item in value)


def is_safe_nickname(value: JsonValue) -> bool:
    return isinstance(value, str) and SAFE_NICKNAME.fullmatch(value) is not None


def collect_control_issues(path: Path, field: str, value: JsonValue) -> list[ProfileIssue]:
    errors: list[ProfileIssue] = []
    match value:
        case str():
            if any(unicodedata.category(character) == "Cc" and character not in "\n\t" for character in value):
                errors.append(issue(path, field, "unsafe_control_character", "profile text contains unsafe control"))
        case list():
            for index, item in enumerate(value):
                errors.extend(collect_control_issues(path, f"{field}[{index}]", item))
        case dict():
            for key, item in value.items():
                errors.extend(collect_control_issues(path, f"{field}.{key}", item))
        case int() | float() | bool() | None:
            return errors
        case unreachable:
            assert_never(unreachable)
    return errors


def validate_profile_shape(path: Path, profile: dict[str, JsonValue]) -> list[ProfileIssue]:
    errors: list[ProfileIssue] = []
    for field in sorted(set(profile) - PROFILE_FIELDS):
        errors.append(issue(path, field, "unknown_profile_key", "unsupported top-level profile key"))
    for field in sorted(PROFILE_REQUIRED_FIELDS - set(profile)):
        errors.append(issue(path, field, "missing_required_field", f"{field} is required"))
    if profile.get("$schema") != PROFILE_SCHEMA_REF:
        errors.append(issue(path, "$schema", "invalid_schema_ref", f"expected $schema {PROFILE_SCHEMA_REF}"))
    if profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
        errors.append(issue(path, "schema_version", "invalid_schema_version", "expected schema_version 0.1"))
    if profile.get("id") not in ROLE_IDS:
        errors.append(issue(path, "id", "invalid_field_value", "id must be a supported role"))
    if not is_nonempty_string(profile.get("name")):
        errors.append(issue(path, "name", "invalid_field_type", "name must be non-empty text"))
    if not is_nonempty_string(profile.get("mission")):
        errors.append(issue(path, "mission", "missing_required_field", "mission must be a non-empty string"))
    if profile.get("uses_king_sejong") is not False:
        errors.append(issue(path, "uses_king_sejong", "missing_required_field", "standalone profiles must set uses_king_sejong to false"))
    if not is_nonempty_string(profile.get("authority_boundary")):
        errors.append(
            issue(path, "authority_boundary", "missing_required_field", "authority_boundary must be a non-empty string")
        )
    for field in REQUIRED_LIST_FIELDS:
        if not is_nonempty_string_list(profile.get(field)):
            errors.append(issue(path, field, "invalid_field_type", f"{field} must be a non-empty string list"))
    handoff_shape = as_json_object(profile.get("handoff_shape"))
    if handoff_shape is None:
        errors.append(issue(path, "handoff_shape", "invalid_field_type", "handoff_shape must be an object"))
    else:
        for field in sorted(set(handoff_shape) - HANDOFF_FIELDS):
            errors.append(issue(path, f"handoff_shape.{field}", "unknown_profile_key", "unsupported handoff key"))
        for field in sorted(HANDOFF_REQUIRED_FIELDS - set(handoff_shape)):
            errors.append(issue(path, f"handoff_shape.{field}", "missing_required_field", f"{field} is required"))
        if handoff_shape.get("format") != "agent_company_bounded_handoff.v0.1":
            errors.append(issue(path, "handoff_shape.format", "invalid_handoff_format", "unexpected handoff format"))
        if handoff_shape.get("policy_ref") != "policies/bounded-handoff.schema.json":
            errors.append(issue(path, "handoff_shape.policy_ref", "invalid_field_value", "unexpected handoff policy"))
        if not is_nonempty_string_list(handoff_shape.get("required_fields")):
            errors.append(
                issue(path, "handoff_shape.required_fields", "invalid_field_type", "required_fields must list strings")
            )
    native_agent = as_json_object(profile.get("native_agent"))
    if native_agent is None:
        errors.append(issue(path, "native_agent", "invalid_field_type", "native_agent must be an object"))
    else:
        unknown = sorted(set(native_agent) - NATIVE_AGENT_FIELDS)
        for field in unknown:
            errors.append(issue(path, f"native_agent.{field}", "unknown_native_key", "unsupported native agent key"))
        for field in NATIVE_AGENT_REQUIRED_FIELDS:
            if not is_nonempty_string(native_agent.get(field)):
                errors.append(
                    issue(path, f"native_agent.{field}", "invalid_field_type", f"{field} must be non-empty text")
                )
        name = native_agent.get("name")
        if not is_nonempty_string(name) or SAFE_NATIVE_NAME.fullmatch(str(name)) is None:
            errors.append(issue(path, "native_agent.name", "invalid_field_value", "unsupported native agent name"))
        if native_agent.get("sandbox_mode") not in NATIVE_SANDBOX_MODES:
            errors.append(
                issue(path, "native_agent.sandbox_mode", "invalid_field_value", "unsupported native sandbox mode")
            )
        model = native_agent.get("model")
        if model is not None and not is_nonempty_string(model):
            errors.append(issue(path, "native_agent.model", "invalid_field_type", "model must be non-empty text"))
        effort = native_agent.get("model_reasoning_effort")
        if effort is not None and effort not in REASONING_EFFORTS:
            errors.append(issue(path, "native_agent.model_reasoning_effort", "invalid_field_value", "unsupported effort"))
        nicknames = native_agent.get("nickname_candidates")
        if nicknames is not None and (
            not isinstance(nicknames, list)
            or not nicknames
            or not all(is_safe_nickname(item) for item in nicknames)
            or len(set(str(item) for item in nicknames)) != len(nicknames)
        ):
            errors.append(
                issue(path, "native_agent.nickname_candidates", "invalid_field_type", "invalid nicknames")
            )
        description = native_agent.get("description")
        if isinstance(description, str) and len(description) > 500:
            errors.append(issue(path, "native_agent.description", "invalid_field_value", "description is too long"))
    return errors
