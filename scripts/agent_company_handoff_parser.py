from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportUnnecessaryComparison=false
# pyright: reportUnusedCallResult=false
from collections.abc import Iterator
from pathlib import Path
from typing import Final, assert_never

from agent_company_deps import JsonValue
from agent_company_expertise_eval_io import parse_json_object, read_bytes
from agent_company_expertise_eval_models import ExpertiseEvaluationError
from agent_company_handoff_errors import HandoffError
from agent_company_handoff_version_validation import (
    validate_versioned_handoff,
)

FORMAT: Final[str] = "agent_company_bounded_handoff.v0.1"
ROLES: Final[set[str]] = {
    "founder", "planning", "marketing", "design", "development", "qa-release",
}
SURFACES: Final[set[str]] = {
    "company-lead", "planning", "qa-release", "user",
    "sejong", "jangyeongsil", "jiphyeonjeon", "uigwe", "seungjeongwon",
    "sillok", "danjong",
}
INTERNAL_ONLY_FIELDS: Final[set[str]] = {
    "recommended_next_surface", "recommended_reasoning_owner",
}
LEGACY_CONTRACT_FIELDS: Final[frozenset[str]] = frozenset(
    {"operating_contract_ref", "operating_contract_sha256"}
)
TEXT_FIELDS: Final[tuple[str, ...]] = (
    "format", "role", "objective", "next_recommended_surface",
)
LIST_FIELDS: Final[tuple[str, ...]] = (
    "known", "inferred", "unknown", "actions_taken", "artifacts", "risks",
    "forbidden_claims",
)
UNSAFE_TOKENS: Final[tuple[str, ...]] = (
    "~/.codex", "auth.json", ".env", "sqlite", "session_index",
    "credentials", "gateway", "final verification authority",
    "gate approval authority", "override user authority", "self-approve final verification", "override king sejong", "replaces king sejong",
)
ALLOWED_FORBIDDEN_CLAIMS: Final[set[str]] = {
    "override user authority", "self-approve final verification",
    "final verification authority",
    "gate approval authority",
    "override King Sejong",
    "replaces King Sejong",
}
MAX_BYTES: Final[int] = 32768
MAX_ITEMS: Final[int] = 20
MAX_TEXT: Final[int] = 400


def json_object(value: JsonValue, field: str) -> dict[str, JsonValue]:
    match value:
        case dict():
            return value
        case str() | int() | float() | bool() | None | list():
            raise HandoffError("malformed_input", f"{field} must be an object")
        case unreachable:
            assert_never(unreachable)


def text_field(values: dict[str, JsonValue], field: str) -> str:
    value = values.get(field)
    match value:
        case str() if value.strip() and len(value) <= MAX_TEXT:
            return value
        case str() | int() | float() | bool() | None | list() | dict():
            raise HandoffError("malformed_input", f"{field} must be bounded non-empty text")
        case unreachable:
            assert_never(unreachable)


def text_list(values: dict[str, JsonValue], field: str) -> list[str]:
    value = values.get(field)
    match value:
        case list() if len(value) <= MAX_ITEMS:
            return [_bounded_string(item, field) for item in value]
        case str() | int() | float() | bool() | None | dict() | list():
            raise HandoffError("malformed_input", f"{field} must be a bounded list")
        case unreachable:
            assert_never(unreachable)


def _bounded_string(value: JsonValue, field: str) -> str:
    match value:
        case str() if value.strip() and len(value) <= MAX_TEXT:
            return value
        case str() | int() | float() | bool() | None | list() | dict():
            raise HandoffError("malformed_input", f"{field} must contain bounded strings")
        case unreachable:
            assert_never(unreachable)


def reject_unsafe_text(payload: JsonValue) -> None:
    joined = " ".join(_json_strings(payload)).lower()
    for token in UNSAFE_TOKENS:
        if token in joined:
            raise HandoffError("unsafe_claim", f"handoff contains disallowed claim token: {token}")


def _json_strings(value: JsonValue) -> Iterator[str]:
    match value:
        case str():
            yield value
        case list():
            for item in value:
                yield from _json_strings(item)
        case dict():
            for key, item in value.items():
                yield key
                yield from _json_strings(item)
        case int() | float() | bool() | None:
            return
        case unreachable:
            assert_never(unreachable)


def validate_handoff_payload(
    payload: dict[str, JsonValue],
    *,
    expected_role_evidence_context_binding: JsonValue | None = None,
) -> dict[str, JsonValue]:
    for field in TEXT_FIELDS:
        text_field(payload, field)
    for field in LIST_FIELDS:
        text_list(payload, field)
    if text_field(payload, "format") != FORMAT or text_field(payload, "role") not in ROLES:
        raise HandoffError("malformed_input", "unsupported handoff format or role")
    if text_field(payload, "next_recommended_surface") not in SURFACES:
        raise HandoffError("malformed_input", "unsupported next surface")
    role = text_field(payload, "role")
    legacy_fields = set(payload) & LEGACY_CONTRACT_FIELDS
    if legacy_fields:
        raise HandoffError("malformed_input", f"unbound contract fields: {sorted(legacy_fields)}")
    validate_versioned_handoff(
        payload,
        role,
        text_field(payload, "objective"),
        expected_role_evidence_context_binding=(
            expected_role_evidence_context_binding
        ),
    )
    leaked = INTERNAL_ONLY_FIELDS.intersection(payload)
    if leaked:
        raise HandoffError("malformed_input", f"internal-only fields: {sorted(leaked)}")
    json_object(payload.get("scope"), "scope")
    unsupported = sorted(
        set(text_list(payload, "forbidden_claims")) - ALLOWED_FORBIDDEN_CLAIMS
    )
    if unsupported:
        raise HandoffError("malformed_input", f"unsupported forbidden_claims: {unsupported}")
    public = {key: value for key, value in payload.items() if key != "forbidden_claims"}
    reject_unsafe_text(public)
    return payload


def parse_handoff(
    path: Path,
    *,
    expected_role_evidence_context_binding: JsonValue | None = None,
) -> dict[str, JsonValue]:
    try:
        content = read_bytes(path, MAX_BYTES)
    except ExpertiseEvaluationError as exc:
        if exc.code == "evaluation_runtime_oversized":
            raise HandoffError(
                "malformed_input",
                "handoff exceeds bounded size",
            ) from exc
        raise HandoffError("stale_state", f"could not read handoff: {exc}") from exc
    try:
        parsed = parse_json_object(content, str(path))
    except ExpertiseEvaluationError as exc:
        raise HandoffError("malformed_input", "invalid handoff JSON") from exc
    return validate_handoff_payload(
        json_object(parsed, str(path)),
        expected_role_evidence_context_binding=(
            expected_role_evidence_context_binding
        ),
    )
