"""Deterministic encoding helpers shared by expertise runtimes."""

from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import hashlib
import json
from datetime import UTC, datetime
from typing import cast

from agent_company_expertise_eval_models import ExpertiseEvaluationError
from agent_company_role_schema import JsonValue


class _DuplicateJsonKey(ValueError):
    pass


def _unique_json_object(
    pairs: list[tuple[str, JsonValue]],
) -> dict[str, JsonValue]:
    value: dict[str, JsonValue] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateJsonKey(key)
        value[key] = item
    return value


def parse_json_object(content: bytes, label: str) -> dict[str, JsonValue]:
    try:
        value = cast(
            JsonValue,
            json.loads(content, object_pairs_hook=_unique_json_object),
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _DuplicateJsonKey,
        RecursionError,
    ) as exc:
        raise ExpertiseEvaluationError(
            "evaluation_runtime_malformed",
            label,
        ) from exc
    if not isinstance(value, dict):
        raise ExpertiseEvaluationError("evaluation_runtime_malformed", label)
    return value


def canonical(value: dict[str, JsonValue]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
