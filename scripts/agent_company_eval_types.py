#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Import from another stdlib-only Agent Company eval script.
# 3. Type-check: ty check scripts/agent_company_eval_types.py
# ─────────────────

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias, assert_never


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class EvalContractError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


def _reject_non_json_constant(raw: str) -> JsonValue:
    raise EvalContractError("malformed_input", f"non-JSON numeric constant is forbidden: {raw}")


def object_value(value: JsonValue, field: str) -> JsonObject:
    match value:
        case dict():
            return value
        case str() | int() | float() | bool() | None | list():
            raise EvalContractError("malformed_input", f"{field} must be an object")
        case unreachable:
            assert_never(unreachable)


def load_object(path: Path) -> JsonObject:
    try:
        parsed: JsonValue = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_non_json_constant,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalContractError("malformed_input", f"cannot parse {path}") from exc
    return object_value(parsed, str(path))


def exact_fields(value: JsonObject, expected: frozenset[str], field: str) -> None:
    if set(value) != expected:
        raise EvalContractError("malformed_input", f"{field} fields mismatch: {sorted(set(value) ^ expected)}")


def text_value(value: JsonValue, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvalContractError("malformed_input", f"{field} must be non-empty text")
    return value


def string_list(value: JsonValue, field: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise EvalContractError("malformed_input", f"{field} must be a string array")
    if not allow_empty and not value:
        raise EvalContractError("malformed_input", f"{field} must not be empty")
    if len(value) != len(set(value)):
        raise EvalContractError("malformed_input", f"{field} must contain unique values")
    return value


def boolean_value(value: JsonValue, field: str) -> bool:
    if not isinstance(value, bool):
        raise EvalContractError("malformed_input", f"{field} must be boolean")
    return value


def finite_number(value: JsonValue, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EvalContractError("malformed_input", f"{field} must be a finite number")
    return float(value)


def canonical_sha256(value: JsonValue) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()
