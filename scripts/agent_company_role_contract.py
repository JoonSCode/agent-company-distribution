#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/agent_company_role_contract.py
# 3. Or run with system Python when stdlib-only execution is preferred:
#      python3 scripts/agent_company_role_contract.py
# ─────────────────

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from agent_company_profiles import validate_profile_file
from agent_company_role_schema import JsonValue, NATIVE_AGENT_FIELDS, as_json_object, load_json_file


REASONING_EFFORTS: Final[frozenset[str]] = frozenset({"minimal", "low", "medium", "high", "xhigh"})
SAFE_AGENT_NAME: Final[re.Pattern[str]] = re.compile(r"^agent-company-[a-z0-9]+(?:-[a-z0-9]+)*$")
SAFE_NICKNAME: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9 _-]+$")


@dataclass(frozen=True, slots=True)
class NativeAgentError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class NativeAgent:
    name: str
    description: str
    sandbox_mode: str
    model: str | None
    reasoning_effort: str | None
    nicknames: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class HandoffShape:
    format: str
    policy_ref: str
    required_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RoleProfile:
    source: Path
    role: str
    display_name: str
    authority_boundary: str
    mission: str
    owns: tuple[str, ...]
    does_not_own: tuple[str, ...]
    skills: tuple[str, ...]
    memory_refs: tuple[str, ...]
    tools: tuple[str, ...]
    approval_rules: tuple[str, ...]
    handoff_shape: HandoffShape
    native_agent: NativeAgent


def profile_text(profile: dict[str, JsonValue], field: str) -> str:
    value = profile.get(field)
    if not isinstance(value, str) or not value.strip():
        raise NativeAgentError("malformed_profile", f"{field} must be non-empty text")
    return value


def profile_texts(profile: dict[str, JsonValue], field: str) -> tuple[str, ...]:
    value = profile.get(field)
    if not isinstance(value, list) or not value:
        raise NativeAgentError("malformed_profile", f"{field} must be a non-empty list")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise NativeAgentError("malformed_profile", f"{field} must contain non-empty text")
        items.append(item)
    return tuple(items)


def instruction_text(value: str, field: str) -> str:
    invalid_control = any(
        unicodedata.category(character) == "Cc" and character not in "\n\t" for character in value
    )
    if not value.strip() or invalid_control:
        raise NativeAgentError("malformed_instructions", f"{field} contains invalid instruction text")
    return value


def optional_text(native: dict[str, JsonValue], field: str) -> str | None:
    value = native.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise NativeAgentError("malformed_profile", f"native_agent.{field} must be non-empty text")
    return value


def parse_nicknames(native: dict[str, JsonValue]) -> tuple[str, ...] | None:
    value = native.get("nickname_candidates")
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise NativeAgentError("malformed_profile", "nickname_candidates must be a non-empty list")
    nicknames: list[str] = []
    for item in value:
        if not isinstance(item, str) or SAFE_NICKNAME.fullmatch(item) is None:
            raise NativeAgentError("malformed_profile", "nickname_candidates contains an unsafe name")
        nicknames.append(item)
    if len(set(nicknames)) != len(nicknames):
        raise NativeAgentError("malformed_profile", "nickname_candidates must be unique")
    return tuple(nicknames)


def parse_native(profile: dict[str, JsonValue]) -> NativeAgent:
    native = as_json_object(profile.get("native_agent"))
    if native is None:
        raise NativeAgentError("malformed_profile", "native_agent must be an object")
    unknown = sorted(set(native) - NATIVE_AGENT_FIELDS)
    if unknown:
        raise NativeAgentError("unknown_native_key", f"unsupported native keys: {unknown}")
    name = profile_text(native, "name")
    if SAFE_AGENT_NAME.fullmatch(name) is None:
        raise NativeAgentError("unsafe_agent_name", f"unsafe agent name: {name!r}")
    reasoning_effort = optional_text(native, "model_reasoning_effort")
    if reasoning_effort is not None and reasoning_effort not in REASONING_EFFORTS:
        raise NativeAgentError("malformed_profile", "unsupported model_reasoning_effort")
    return NativeAgent(
        name=name,
        description=instruction_text(profile_text(native, "description"), "native_agent.description"),
        sandbox_mode=profile_text(native, "sandbox_mode"),
        model=optional_text(native, "model"),
        reasoning_effort=reasoning_effort,
        nicknames=parse_nicknames(native),
    )


def parse_handoff(profile: dict[str, JsonValue]) -> HandoffShape:
    handoff = as_json_object(profile.get("handoff_shape"))
    if handoff is None:
        raise NativeAgentError("malformed_profile", "handoff_shape must be an object")
    return HandoffShape(
        format=instruction_text(profile_text(handoff, "format"), "handoff_shape.format"),
        policy_ref=instruction_text(profile_text(handoff, "policy_ref"), "handoff_shape.policy_ref"),
        required_fields=tuple(
            instruction_text(item, "handoff_shape.required_fields")
            for item in profile_texts(handoff, "required_fields")
        ),
    )


def load_profile(path: Path) -> RoleProfile:
    valid, issues = validate_profile_file(path)
    if not valid:
        codes = {item.code for item in issues}
        if any(item.field == "native_agent.name" and item.code == "invalid_field_value" for item in issues):
            raise NativeAgentError("unsafe_agent_name", f"unsafe agent name in {path.name}")
        if "unknown_native_key" in codes:
            raise NativeAgentError("unknown_native_key", f"unsupported native key in {path.name}")
        if "unknown_profile_key" in codes:
            raise NativeAgentError("unknown_profile_key", f"unsupported profile key in {path.name}")
        if "forbidden_authority_claim" in codes:
            raise NativeAgentError("forbidden_authority", f"forbidden authority claim in {path.name}")
        if "unsafe_control_character" in codes:
            raise NativeAgentError("malformed_instructions", f"unsafe control character in {path.name}")
        raise NativeAgentError("malformed_profile", f"invalid profile {path.name}: {sorted(codes)}")
    parsed, load_issue = load_json_file(path)
    if load_issue is not None or parsed is None:
        raise NativeAgentError("malformed_profile", f"could not load {path.name}")
    profile = as_json_object(parsed)
    if profile is None:
        raise NativeAgentError("malformed_profile", f"{path.name} must contain an object")
    return RoleProfile(
        source=path,
        role=profile_text(profile, "id"),
        display_name=profile_text(profile, "name"),
        authority_boundary=instruction_text(profile_text(profile, "authority_boundary"), "authority_boundary"),
        mission=instruction_text(profile_text(profile, "mission"), "mission"),
        owns=tuple(instruction_text(item, "owns") for item in profile_texts(profile, "owns")),
        does_not_own=tuple(
            instruction_text(item, "does_not_own") for item in profile_texts(profile, "does_not_own")
        ),
        skills=tuple(instruction_text(item, "skills") for item in profile_texts(profile, "skills")),
        memory_refs=tuple(
            instruction_text(item, "memory_refs") for item in profile_texts(profile, "memory_refs")
        ),
        tools=tuple(instruction_text(item, "tools") for item in profile_texts(profile, "tools")),
        approval_rules=tuple(
            instruction_text(item, "approval_rules") for item in profile_texts(profile, "approval_rules")
        ),
        handoff_shape=parse_handoff(profile),
        native_agent=parse_native(profile),
    )
