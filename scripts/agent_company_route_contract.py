#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Import this module from scripts/agent_company_routing.py.
# ─────────────────

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import Final, TypeAlias, assert_never


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

CORE_FORMAT: Final[str] = "sejong.task-class-delegation-gate/v0.1-draft"
CORE_GATE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "preserves_uigwe_contract",
        "keeps_worker_outputs_evidence_only",
        "records_reviewable_evidence",
        "keeps_artifacts_under_sejong_home_or_promoted_refs",
        "does_not_create_new_court_mode",
    }
)
CORE_NON_GATE_BLOCKERS: Final[frozenset[str]] = frozenset(
    {
        "seungjeongwon_guardrails_blocked",
        "uigwe_contract_required_before_writes",
        "write_mode_no_write",
        "write_mode_dry_run",
        "write_mode_destructive",
        "unsafe_write_risk",
    }
)


@unique
class CoreRoute(StrEnum):
    DIRECT = "direct_execution"
    BOUNDED = "bounded_subagents"
    TEAM = "team_executor"
    RESEARCH = "research_fanout"
    DRY_RUN = "no_write_dry_run"


@dataclass(frozen=True, slots=True)
class RoutingError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class CoreDecision:
    selected_route: str
    capability_refs: tuple[str, ...]
    gate_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    recommended_reentry_target: str
    backend_json: str | None
    authority_sha256: str
    source_ref: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class ApprovalEvidence:
    receipt_ref: str
    receipt_sha256: str
    action_id: str
    source_user_decision_ref: str


@dataclass(frozen=True, slots=True)
class ProjectionRequest:
    core: CoreDecision
    ordinary_role_ids: tuple[str, ...]
    external_mutation: bool
    approval_required: bool
    approval_evidence: ApprovalEvidence | None = None


@dataclass(frozen=True, slots=True)
class TextListRule:
    label: str
    allow_empty: bool = False
    duplicate_code: str = "malformed_input"


def canonical_json(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def parse_object(value: JsonValue, label: str) -> JsonObject:
    match value:
        case dict():
            return value
        case str() | int() | float() | bool() | None | list():
            raise RoutingError("malformed_input", f"{label} must be an object")
        case unreachable:
            assert_never(unreachable)


def parse_text(value: JsonValue, label: str) -> str:
    match value:
        case str() if value.strip():
            return value
        case str() | int() | float() | bool() | None | list() | dict():
            raise RoutingError("malformed_input", f"{label} must be non-empty text")
        case unreachable:
            assert_never(unreachable)


def parse_texts(value: JsonValue, rule: TextListRule) -> tuple[str, ...]:
    match value:
        case list() if (value or rule.allow_empty) and all(
            isinstance(item, str) and item.strip() for item in value
        ):
            items = tuple(value)
        case str() | int() | float() | bool() | None | list() | dict():
            raise RoutingError(
                "malformed_input", f"{rule.label} must contain text values"
            )
        case unreachable:
            assert_never(unreachable)
    if len(items) != len(set(items)):
        raise RoutingError(
            rule.duplicate_code, f"{rule.label} must contain unique refs"
        )
    return items


def known_route(value: str) -> CoreRoute | None:
    try:
        return CoreRoute(value)
    except ValueError:
        return None


def validate_gates(
    route: CoreRoute | None, gates: JsonObject, failures: tuple[str, ...]
) -> None:
    if set(gates) != CORE_GATE_NAMES or not all(
        isinstance(passed, bool) for passed in gates.values()
    ):
        raise RoutingError(
            "core_gate_contradiction",
            "Core hard-gate map differs from its pinned contract",
        )
    false_gates = {name for name, passed in gates.items() if passed is False}
    named_failures = set(failures).intersection(CORE_GATE_NAMES)
    non_gate_failures = set(failures).difference(CORE_GATE_NAMES)
    if named_failures != false_gates:
        raise RoutingError(
            "core_gate_contradiction",
            "gate-named failures must exactly equal false Core gates",
        )
    if not non_gate_failures.issubset(CORE_NON_GATE_BLOCKERS):
        raise RoutingError(
            "core_gate_contradiction",
            "Core failures contain an unsupported non-gate blocker",
        )
    match route:
        case CoreRoute.DRY_RUN | None:
            return
        case CoreRoute.DIRECT | CoreRoute.BOUNDED | CoreRoute.TEAM | CoreRoute.RESEARCH:
            if false_gates or failures:
                raise RoutingError(
                    "core_gate_contradiction",
                    "selected Core route contradicts failed hard gates",
                )
        case unreachable:
            assert_never(unreachable)


def parse_refs(root: JsonObject, field: str, source_ref: str) -> tuple[str, ...]:
    if field not in root:
        fragment = {
            "capability_refs": "selected_route",
            "gate_refs": "hard_gates",
            "evidence_refs": "required_evidence",
        }[field]
        return (f"{source_ref}#{fragment}",)
    value = root.get(field)
    if field == "capability_refs" and value == []:
        raise RoutingError(
            "capability_evidence_missing", "capability_refs must contain evidence refs"
        )
    return parse_texts(value, TextListRule(field, duplicate_code="duplicate_core_ref"))


def parse_core(
    value: JsonValue,
    source_ref: str = "core://decision/input",
    source_sha256: str | None = None,
) -> CoreDecision:
    root = parse_object(value, "Core decision")
    if parse_text(root.get("format"), "Core format") != CORE_FORMAT:
        raise RoutingError(
            "core_format_mismatch", "Core format differs from the pinned contract"
        )
    selected_route = parse_text(root.get("selected_route"), "selected_route")
    route = known_route(selected_route)
    gates = parse_object(root.get("hard_gates"), "hard_gates")
    failures = parse_texts(
        root.get("hard_gate_failures"),
        TextListRule("hard_gate_failures", allow_empty=True),
    )
    validate_gates(route, gates, failures)
    _ = parse_texts(root.get("required_evidence"), TextListRule("required_evidence"))
    _ = parse_texts(root.get("forbidden_claims"), TextListRule("forbidden_claims"))
    capability_refs = parse_refs(root, "capability_refs", source_ref)
    gate_refs = parse_refs(root, "gate_refs", source_ref)
    evidence_refs = parse_refs(root, "evidence_refs", source_ref)
    reentry = parse_text(
        root.get("recommended_reentry_target"), "recommended_reentry_target"
    )
    backend = root.get("backend_provenance")
    backend_json: str | None = None
    if backend is not None:
        backend_object = parse_object(backend, "backend_provenance")
        if not backend_object:
            raise RoutingError(
                "malformed_input", "backend_provenance must not be empty"
            )
        backend_json = canonical_json(backend_object)
    authority: JsonObject = {"source_ref": source_ref, "decision": root}
    authority_sha256 = hashlib.sha256(canonical_json(authority).encode()).hexdigest()
    byte_sha256 = source_sha256 or hashlib.sha256(canonical_json(root).encode()).hexdigest()
    return CoreDecision(
        selected_route,
        capability_refs,
        gate_refs,
        evidence_refs,
        reentry,
        backend_json,
        authority_sha256,
        source_ref,
        byte_sha256,
    )


def load_json(path: Path) -> JsonValue:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RoutingError("malformed_input", f"cannot read JSON input: {exc}") from exc
