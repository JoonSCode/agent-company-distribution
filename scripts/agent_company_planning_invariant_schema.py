from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportImplicitOverride=false, reportUnnecessaryComparison=false
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, assert_never

from agent_company_role_schema import JsonValue

MAX_TEXT_LENGTH: Final[int] = 400
START_GATE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "planning_readiness", "control_timing", "pre_mutation_evidence",
        "startability_disposition", "decision_owner",
    }
)
LEAF_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "id", "criterion_id", "objective", "why", "first_action", "inputs",
        "read_scope", "write_scope", "done_criteria", "dependencies",
        "state_transition", "verification_method", "evidence_target",
        "falsification_signal", "risks", "stop_condition", "owner", "verifier",
        "handoff_output", "binary_completion",
    }
)
DEPENDENCY_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "edge_id", "surface_disposition", "evidence_ref", "recheck_trigger",
        "fallback", "cycle_review", "authority_class", "assignee_state",
        "residual_risk_authority",
    }
)
APPLICABLE_PROOF_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "criterion_id", "surface", "applicability", "candidate_lineage",
        "verifier", "binary_observable",
    }
)
NOT_APPLICABLE_PROOF_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "criterion_id", "surface", "applicability", "reason", "evidence_ref",
        "decision_owner",
    }
)
LINEAGE_FIELDS: Final[frozenset[str]] = frozenset(
    {"source", "artifact", "config", "environment", "runtime_topology"}
)
DEPENDENCY_DISPOSITIONS: Final[frozenset[str]] = frozenset(
    {"satisfied", "unsatisfied", "conditional", "unknown", "not_applicable"}
)
CYCLE_REVIEWS: Final[frozenset[str]] = frozenset(
    {"no_cycle", "cycle_resolved", "cycle_blocked"}
)
AUTHORITY_CLASSES: Final[frozenset[str]] = frozenset(
    {"planning_recommendation", "uigwe_decision", "seungjeongwon_execution", "external_approval"}
)
ASSIGNEE_STATES: Final[frozenset[str]] = frozenset({"assigned", "unavailable", "pending"})
RESIDUAL_RISK_AUTHORITIES: Final[frozenset[str]] = frozenset(
    {"uigwe", "external_approval", "none"}
)
TASK_PACK_BINDINGS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("execution-planning", "task-pack:planning:execution-plan"),
        ("dependency-risk", "task-pack:planning:dependency-risk"),
        ("acceptance-verification", "task-pack:planning:acceptance-verification"),
    }
)
SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"^sha256:[0-9a-f]{64}$")
RESERVED_REFERENCE_COMPONENTS: Final[frozenset[str]] = frozenset(
    {"default", "pending", "placeholder", "example"}
)


class PlanningReadiness(StrEnum):
    CONDITIONAL = "conditional"
    READY = "ready"
    BLOCKED = "blocked"


class ProofApplicability(StrEnum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class PlanningInvariantError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class LeafCriterion:
    leaf_id: str
    criterion_id: str
    dependencies: tuple[str, ...]
    owner: str
    verifier: str


@dataclass(frozen=True, slots=True)
class DependencyAuthority:
    edge_id: str
    surface_disposition: str
    cycle_review: str
    assignee_state: str


@dataclass(frozen=True, slots=True)
class ProofCriterion:
    criterion_id: str
    verifier: str | None


def object_value(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    match value:
        case dict():
            return value
        case str() | int() | float() | bool() | None | list():
            raise PlanningInvariantError(f"{label} must be an object")
        case unreachable:
            assert_never(unreachable)


def text_value(value: JsonValue | None, label: str) -> str:
    match value:
        case str() if value.strip() and len(value) <= MAX_TEXT_LENGTH:
            return value
        case str() | int() | float() | bool() | None | list() | dict():
            raise PlanningInvariantError(f"{label} must be bounded non-empty text")
        case unreachable:
            assert_never(unreachable)


def text_list(value: JsonValue | None, label: str, *, allow_empty: bool) -> tuple[str, ...]:
    match value:
        case list() if allow_empty or value:
            return tuple(text_value(item, f"{label}[{index}]") for index, item in enumerate(value, start=1))
        case str() | int() | float() | bool() | None | dict() | list():
            state = "possibly empty" if allow_empty else "non-empty"
            raise PlanningInvariantError(f"{label} must be a {state} text list")
        case unreachable:
            assert_never(unreachable)


def evidence_reference(value: JsonValue | None, label: str) -> str:
    reference = text_value(value, label)
    components = frozenset(re.split(r"[^a-z0-9]+", reference.lower()))
    if components.intersection(RESERVED_REFERENCE_COMPONENTS):
        raise PlanningInvariantError(f"{label} contains a reserved sentinel component")
    return reference


def sha256_digest(value: JsonValue | None, label: str) -> str:
    digest = text_value(value, label)
    if SHA256_PATTERN.fullmatch(digest) is None:
        raise PlanningInvariantError(f"{label} must be a sha256: digest with 64 lowercase hex characters")
    return digest


def exact_fields(value: dict[str, JsonValue], expected: frozenset[str], label: str) -> None:
    if set(value) != expected:
        raise PlanningInvariantError(f"{label} must contain exactly {sorted(expected)}")


def member(value: str, allowed: frozenset[str], label: str) -> None:
    if value not in allowed:
        raise PlanningInvariantError(f"{label} is unsupported")
