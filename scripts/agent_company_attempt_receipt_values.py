#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Import through agent_company_attempt_receipt.py.
# 2. Test: uv run scripts/test_agent_company_attempt_receipt.py
# ─────────────────

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

import re
from typing import Final, final, override

from agent_company_privacy import JsonObject, JsonValue


NAME: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
ID: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
EVIDENCE_REF: Final = re.compile(
    r"^(?:artifact|evidence|repo|sejong)://[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*){0,7}$"
)
PRIVATE_PATH_SEGMENTS: Final = frozenset(
    {"home", "private", "tmp", "users", "var", "volumes"}
)


@final
class AttemptReceiptError(Exception):
    """Typed execution-attempt receipt failure."""

    code: str
    detail: str

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)
        self.code = code
        self.detail = detail

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


def object_value(value: JsonValue, name: str) -> JsonObject:
    if not isinstance(value, dict):
        raise AttemptReceiptError("malformed_input", f"{name} must be an object")
    return value


def exact_fields(values: JsonObject, expected: frozenset[str], name: str) -> None:
    if frozenset(values) != expected:
        raise AttemptReceiptError("malformed_input", f"{name} fields are invalid")


def text_value(
    values: JsonObject,
    name: str,
    pattern: re.Pattern[str] = NAME,
) -> str:
    value = values.get(name)
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise AttemptReceiptError("malformed_input", f"{name} is invalid")
    return value


def nullable_text_value(
    values: JsonObject,
    name: str,
    pattern: re.Pattern[str] = NAME,
) -> str | None:
    if values.get(name) is None:
        return None
    return text_value(values, name, pattern)


def choice_value(values: JsonObject, name: str, choices: frozenset[str]) -> str:
    value = text_value(values, name)
    if value not in choices:
        raise AttemptReceiptError("malformed_input", f"{name} is unsupported")
    return value


def count_value(values: JsonObject, name: str) -> int:
    value = values.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AttemptReceiptError(
            "malformed_input",
            f"{name} must be a non-negative integer",
        )
    return value


def nullable_count_value(values: JsonObject, name: str) -> int | None:
    if values.get(name) is None:
        return None
    return count_value(values, name)


def boolean_value(values: JsonObject, name: str) -> bool:
    value = values.get(name)
    if not isinstance(value, bool):
        raise AttemptReceiptError("malformed_input", f"{name} must be boolean")
    return value


def nullable_boolean_value(values: JsonObject, name: str) -> bool | None:
    if values.get(name) is None:
        return None
    return boolean_value(values, name)


def score_value(values: JsonObject, name: str) -> float | None:
    value = values.get(name)
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not 0 <= value <= 1
    ):
        raise AttemptReceiptError(
            "malformed_input",
            f"{name} must be between 0 and 1 or null",
        )
    return float(value)


def strings_value(
    values: JsonObject,
    name: str,
    choices: frozenset[str] | None = None,
) -> tuple[str, ...]:
    value = values.get(name)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AttemptReceiptError("malformed_input", f"{name} must be a text list")
    parsed = tuple(item for item in value if isinstance(item, str))
    if len(set(parsed)) != len(parsed) or (
        choices is not None and not set(parsed).issubset(choices)
    ):
        raise AttemptReceiptError(
            "malformed_input",
            f"{name} contains invalid values",
        )
    return parsed


def evidence_refs_value(
    values: JsonObject,
    name: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    refs = strings_value(values, name)
    unsafe = any(
        EVIDENCE_REF.fullmatch(ref) is None
        or PRIVATE_PATH_SEGMENTS.intersection(ref.split("://", 1)[-1].split("/"))
        for ref in refs
    )
    if unsafe or (not allow_empty and not refs):
        raise AttemptReceiptError("malformed_input", f"{name} contains unsafe refs")
    return refs
