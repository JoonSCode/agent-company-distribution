from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportUnnecessaryComparison=false, reportUnusedCallResult=false
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, assert_never

from agent_company_deps import JsonValue

MAX_BYTES: Final[int] = 20_000
MAX_CRITERIA: Final[int] = 8
SHA256_LENGTH: Final[int] = 64
SURFACES: Final[frozenset[str]] = frozenset(
    {
        "automated",
        "simulator",
        "real_device",
        "permission_lifecycle",
        "storekit",
        "app_store_connect",
        "manual",
    }
)
QUALIFIERS: Final[frozenset[str]] = frozenset(
    {
        "automated",
        "simulator",
        "physical_device",
        "storekit_local",
        "sandbox_account",
        "remote_account",
        "manual",
    }
)
SURFACE_QUALIFIERS: Final[Mapping[str, frozenset[str]]] = MappingProxyType({
    "automated": frozenset({"automated"}),
    "simulator": frozenset({"simulator"}),
    "real_device": frozenset({"physical_device"}),
    "permission_lifecycle": frozenset({"simulator", "physical_device"}),
    "storekit": frozenset({"storekit_local", "sandbox_account"}),
    "app_store_connect": frozenset({"remote_account"}),
    "manual": frozenset({"manual", "simulator", "physical_device"}),
})
PERMISSION_STATES: Final[tuple[str, ...]] = (
    "not_determined",
    "denied",
    "limited",
    "granted",
    "revoked",
    "settings_return",
    "relaunch",
)


@dataclass(frozen=True, slots=True)
class QaVerificationV2:
    authorizes_completion: bool
    readiness: str
    criterion_statuses: tuple[tuple[str, str], ...]
    reference_ids: tuple[str, ...]
    evidence_facts: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True, slots=True)
class QaV2Error(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


def _object(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    match value:
        case dict():
            return value
        case str() | int() | float() | bool() | None | list():
            raise QaV2Error(f"{label} must be an object")
        case unreachable:
            assert_never(unreachable)


def _list(value: JsonValue | None, label: str) -> list[JsonValue]:
    match value:
        case list():
            return value
        case str() | int() | float() | bool() | None | dict():
            raise QaV2Error(f"{label} must be a list")
        case unreachable:
            assert_never(unreachable)


def _text(value: JsonValue | None, label: str) -> str:
    match value:
        case str() if value.strip() and len(value) <= 400:
            return value
        case str() | int() | float() | bool() | None | list() | dict():
            raise QaV2Error(f"{label} must be bounded non-empty text")
        case unreachable:
            assert_never(unreachable)


def _texts(value: JsonValue | None, label: str) -> tuple[str, ...]:
    items = tuple(_text(item, label) for item in _list(value, label))
    if len(items) != len(set(items)):
        raise QaV2Error(f"{label} IDs or values must be unique")
    return items


def _fields(value: dict[str, JsonValue], expected: frozenset[str], label: str) -> None:
    if set(value) != expected:
        raise QaV2Error(f"{label} must contain exactly {sorted(expected)}")


def _sha(value: JsonValue | None, label: str) -> str:
    digest = _text(value, label)
    valid = len(digest) == SHA256_LENGTH and all(char in "0123456789abcdef" for char in digest)
    if not valid:
        raise QaV2Error(f"{label} must be a SHA-256 digest")
    if digest == "0" * SHA256_LENGTH:
        raise QaV2Error(f"{label} rejects placeholder digest")
    return digest


def _candidate(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    candidate = _object(value, label)
    binding = _text(candidate.get("binding"), f"{label}.binding")
    if binding == "exact":
        _fields(candidate, frozenset({"binding", "identity_ref", "identity_sha256"}), label)
        _text(candidate.get("identity_ref"), f"{label}.identity_ref")
        _sha(candidate.get("identity_sha256"), f"{label}.identity_sha256")
        return candidate
    if binding == "partial":
        _fields(candidate, frozenset({"binding", "identity_ref", "reason"}), label)
        _text(candidate.get("identity_ref"), f"{label}.identity_ref")
        _text(candidate.get("reason"), f"{label}.reason")
        return candidate
    if binding == "unknown":
        _fields(candidate, frozenset({"binding", "reason"}), label)
        _text(candidate.get("reason"), f"{label}.reason")
        return candidate
    raise QaV2Error(f"{label}.binding must be exact, partial, or unknown")


def _references(value: JsonValue | None) -> tuple[str, ...]:
    identifiers: list[str] = []
    for index, raw in enumerate(_list(value, "references")):
        item = _object(raw, f"references[{index}]")
        resolution = _text(item.get("resolution"), f"references[{index}].resolution")
        if resolution == "exact":
            _fields(item, frozenset({"id", "resolution", "ref", "sha256"}), f"references[{index}]")
            _text(item.get("ref"), f"references[{index}].ref")
            _sha(item.get("sha256"), f"references[{index}].sha256")
        elif resolution == "unresolved":
            _fields(item, frozenset({"id", "resolution", "ref", "reason"}), f"references[{index}]")
            _text(item.get("ref"), f"references[{index}].ref")
            _text(item.get("reason"), f"references[{index}].reason")
        elif resolution == "not_applicable":
            _fields(item, frozenset({"id", "resolution", "reason"}), f"references[{index}]")
            _text(item.get("reason"), f"references[{index}].reason")
        else:
            raise QaV2Error("reference resolution must be exact, unresolved, or not_applicable")
        identifiers.append(_text(item.get("id"), f"references[{index}].id"))
    if len(identifiers) != len(set(identifiers)):
        raise QaV2Error("reference IDs must be unique")
    return tuple(identifiers)


def _criteria(value: JsonValue | None) -> tuple[tuple[str, str, str, str, tuple[str, ...]], ...]:
    raw_items = _list(value, "criteria")
    if not 1 <= len(raw_items) <= MAX_CRITERIA:
        raise QaV2Error("criteria must contain 1 to 8 plans")
    result: list[tuple[str, str, str, str, tuple[str, ...]]] = []
    expected = frozenset(
        {
            "id", "kind", "claim", "required_surface", "required_qualifier",
            "required_permission_states", "expected_observable",
        }
    )
    for index, raw in enumerate(raw_items):
        item = _object(raw, f"criteria[{index}]")
        _fields(item, expected, f"criteria[{index}]")
        identifier = _text(item.get("id"), f"criteria[{index}].id")
        kind = _text(item.get("kind"), f"criteria[{index}].kind")
        if kind not in {"acceptance", "risk", "boundary"}:
            raise QaV2Error("criterion kind is unsupported")
        _text(item.get("claim"), f"criteria[{index}].claim")
        surface = _text(item.get("required_surface"), f"criteria[{index}].required_surface")
        qualifier = _text(item.get("required_qualifier"), f"criteria[{index}].required_qualifier")
        if surface not in SURFACES or qualifier not in QUALIFIERS:
            raise QaV2Error("criterion surface qualifier is unsupported")
        if qualifier not in SURFACE_QUALIFIERS[surface]:
            raise QaV2Error("criterion surface qualifier violates the iOS ladder")
        states = _texts(item.get("required_permission_states"), f"criteria[{index}].required_permission_states")
        if surface == "permission_lifecycle" and not states:
            raise QaV2Error("permission lifecycle criterion requires states")
        if any(state not in PERMISSION_STATES for state in states):
            raise QaV2Error("permission lifecycle state is unsupported")
        _text(item.get("expected_observable"), f"criteria[{index}].expected_observable")
        result.append((identifier, kind, surface, qualifier, states))
    if len({item[0] for item in result}) != len(result):
        raise QaV2Error("criterion IDs must be unique")
    return tuple(result)
