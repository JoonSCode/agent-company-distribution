from __future__ import annotations

# pyright: reportUnnecessaryComparison=false
from dataclasses import dataclass
from typing import Final, TypeAlias, assert_never, override

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

PLACEHOLDERS: Final[frozenset[str]] = frozenset(
    {"", "-", "...", "n/a", "none", "pending", "tbd", "todo", "unknown", "default"}
)
COMMITMENT_FIELDS: Final[frozenset[str]] = frozenset(
    {"action", "owner", "time_box", "resource_cap"}
)


@dataclass(frozen=True, slots=True)
class FounderTaskEvidenceError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return self.detail


def record(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    """Parse an evidence record without allowing untyped values downstream."""
    match value:
        case dict():
            return value
        case str() | int() | float() | bool() | None | list():
            raise FounderTaskEvidenceError(f"{label} must be an object")
        case unreachable:
            assert_never(unreachable)


def text(value: JsonValue | None, label: str) -> str:
    """Require non-placeholder decision text."""
    match value:
        case str() if value.strip() and value.strip().casefold() not in PLACEHOLDERS:
            return value.strip()
        case str() | int() | float() | bool() | None | list() | dict():
            raise FounderTaskEvidenceError(f"{label} must be specific non-empty text")
        case unreachable:
            assert_never(unreachable)


def text_like(value: JsonValue | None, label: str) -> tuple[str, ...]:
    """Allow a specific statement or a non-empty set of statements."""
    match value:
        case str():
            return (text(value, label),)
        case list() if value:
            return tuple(
                text(item, f"{label}[{index}]") for index, item in enumerate(value)
            )
        case int() | float() | bool() | None | list() | dict():
            raise FounderTaskEvidenceError(
                f"{label} must be specific text or a non-empty text list"
            )
        case unreachable:
            assert_never(unreachable)


def text_list(value: JsonValue | None, label: str) -> tuple[str, ...]:
    """Require a non-empty evidence-reference or authority-boundary list."""
    match value:
        case list() if value:
            return tuple(
                text(item, f"{label}[{index}]") for index, item in enumerate(value)
            )
        case str() | int() | float() | bool() | None | list() | dict():
            raise FounderTaskEvidenceError(
                f"{label} must be a non-empty specific text list"
            )
        case unreachable:
            assert_never(unreachable)


def commitment(value: JsonValue | None) -> None:
    """Require a bounded, owner-assigned, reversible commitment description."""
    packet = record(value, "next_reversible_commitment")
    actual = frozenset(packet)
    if actual != COMMITMENT_FIELDS:
        missing = sorted(COMMITMENT_FIELDS - actual)
        extra = sorted(actual - COMMITMENT_FIELDS)
        raise FounderTaskEvidenceError(
            f"next_reversible_commitment has unsupported fields: missing={missing}, extra={extra}"
        )
    for field in COMMITMENT_FIELDS:
        _ = text(packet.get(field), f"next_reversible_commitment.{field}")


def forbidden_claims(value: JsonValue | None) -> None:
    """Preserve explicit Founder authority limits in every completed packet."""
    claims = tuple(item.casefold() for item in text_list(value, "forbidden_claims"))
    required = (
        ("ceo", "decision"),
        ("uigwe", "approval"),
        ("external", "action"),
        ("execution", "success"),
        ("final", "verification"),
    )
    for first, second in required:
        if not any(first in claim and second in claim for claim in claims):
            raise FounderTaskEvidenceError(
                f"forbidden_claims must preserve {first} {second}"
            )


def authority_is_bounded(payload: dict[str, JsonValue]) -> bool:
    """Reject authority claims while allowing their explicit forbidden declarations."""
    banned = (
        "i am the ceo",
        "ceo has decided",
        "final approval",
        "approval granted",
        "uigwe gate approved",
        "final verification complete",
        "execution is verified",
        "release ready",
    )
    for field, value in payload.items():
        if field == "forbidden_claims":
            continue
        for item in claim_texts(value):
            if any(fragment in item.casefold() for fragment in banned):
                return False
    return True


def claim_texts(value: JsonValue) -> tuple[str, ...]:
    """Collect candidate claims from a validated JSON-compatible packet."""
    match value:
        case str():
            return (value,)
        case list():
            return tuple(text for item in value for text in claim_texts(item))
        case dict():
            return tuple(text for item in value.values() for text in claim_texts(item))
        case int() | float() | bool() | None:
            return ()
        case unreachable:
            assert_never(unreachable)


__all__ = [
    "FounderTaskEvidenceError",
    "JsonValue",
    "authority_is_bounded",
    "commitment",
    "forbidden_claims",
    "record",
    "text",
    "text_like",
    "text_list",
]
