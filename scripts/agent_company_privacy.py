#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Import from Todo 4 runtime modules; this file has no standalone command.
# 3. Tests: python3 scripts/test_agent_company_privacy_security.py
# ─────────────────

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

import json
import re
from datetime import UTC, datetime
from typing import Final, assert_never, final, override


type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

ROLES: Final = frozenset({"founder", "marketing", "planning", "design", "development", "qa-release"})
RFC3339: Final = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$")
FORBIDDEN_KEYS: Final = (
    "prompt", "transcript", "connector", "credential", "secret", "password", "private_key",
    "api_key", "access_token", "refresh_token", "raw_path", "session", "cookie",
)
SECRET: Final = re.compile(
    "".join((
        r"(?i)(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|sk-[a-z0-9_-]{4,}|gh[pousr]_[a-z0-9]+|",
        r"xox[baprs]-[a-z0-9-]+|akia[a-z0-9]{12,}|aiza[a-z0-9_-]{30,}|bearer\s+[a-z0-9._~-]+|",
        r"eyJ[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}\.[a-z0-9_-]{4,})",
    ))
)
ABSOLUTE_PATH: Final = re.compile(
    "".join((
        r"(?:[A-Za-z]:[\\/]+(?:Users|Documents|ProgramData|Windows)[\\/]+|\\\\[^\\\s]+\\[^\\\s]+|",
        r"(?:^|[\s\"'])(?:/(?:Users|home|root|var|etc|tmp)/)[^\s\"']+)",
    ))
)
TRANSCRIPT: Final = re.compile(r"(?im)(?:^|\n)(?:user|assistant|system|tool)\s*:")
INJECTION: Final = re.compile(r"(?i)(?:ignore\s+(?:all\s+)?prior|system\s+prompt)")


@final
class PrivacyError(Exception):
    """Typed privacy-boundary failure."""

    code: str
    detail: str

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)
        self.code = code
        self.detail = detail

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


def parse_rfc3339(value: str, field: str) -> datetime:
    if RFC3339.fullmatch(value) is None:
        raise PrivacyError("malformed_input", f"{field} must be RFC3339")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PrivacyError("malformed_input", f"{field} must be RFC3339") from exc
    return parsed.astimezone(UTC)


def ensure_role(value: str) -> str:
    if value not in ROLES:
        raise PrivacyError("role_denied", "requesting_role is not allowlisted")
    return value


def parse_json(text: str) -> JsonValue:
    value: JsonValue = json.loads(text)
    return value


def _is_connector_uri(value: str) -> bool:
    return value.strip().casefold().startswith("connector://")


def sensitive_findings(value: JsonValue) -> tuple[str, ...]:
    findings: list[str] = []

    def visit(item: JsonValue) -> None:
        match item:
            case dict():
                for key, nested in item.items():
                    if any(term in key.lower() for term in FORBIDDEN_KEYS):
                        findings.append("forbidden-key")
                    visit(nested)
            case list():
                for nested in item:
                    visit(nested)
            case str() as text:
                stripped = text.strip()
                serialized = False
                if stripped.startswith(("{", "[")):
                    try:
                        serialized = isinstance(json.loads(stripped), dict | list)
                    except json.JSONDecodeError:
                        serialized = False
                if SECRET.search(text) or ABSOLUTE_PATH.search(text) or TRANSCRIPT.search(text) or INJECTION.search(text):
                    findings.append("forbidden-value")
                if serialized or _is_connector_uri(text):
                    findings.append("serialized-payload")
            case None:
                return
            case bool() | int() | float():
                return
            case unreachable:
                assert_never(unreachable)

    visit(value)
    return tuple(findings)


def reject_sensitive(value: JsonValue) -> None:
    if sensitive_findings(value):
        raise PrivacyError("privacy_rejected", "payload contains forbidden private data")
