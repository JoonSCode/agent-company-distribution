#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run with system Python through a caller:
#      python3 scripts/agent_company_jobs.py report --help
# ─────────────────

from __future__ import annotations

# pyright: reportAny=false, reportImplicitRelativeImport=false, reportUnnecessaryComparison=false, reportUnusedCallResult=false
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, assert_never

from agent_company_deps import JsonValue
from agent_company_handoff_knowledge import (
    HandoffKnowledgeError,
    validate_execution_knowledge,
)
from agent_company_handoff_model_routing import (
    ModelRoutingHandoffError,
    ModelRoutingHandoffEvidence,
    validate_model_routing_handoff,
)
from agent_company_handoff_plan import HandoffPlanError, validate_plan_assignment
from agent_company_handoff_receipt_artifact import (
    HandoffArtifactError,
    read_receipt_handoff,
)
from agent_company_handoff_role_evidence import (
    INTEGRATED_ROLES,
    RoleEvidenceError,
    validate_role_evidence,
)
from agent_company_handoff_validation_models import HandoffContractError
from agent_company_handoff_validation_models import (
    HandoffValidation as BaseHandoffValidation,
)
from agent_company_qa_assignment_binding import (
    QaAssignmentBindingError,
    validate_qa_assignment_binding,
)
from agent_company_qa_handoff import QaHandoffError, parse_qa_verification

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
HANDOFF_POLICY_PATH: Final[Path] = ROOT / "policies" / "bounded-handoff.schema.json"
SCOPE_LIST_FIELDS: Final[tuple[str, ...]] = ("allowed_paths", "read_refs", "write_refs")
EVIDENCE_FIELDS: Final[tuple[str, ...]] = ("known", "inferred", "unknown", "actions_taken", "artifacts", "risks")


@dataclass(frozen=True, slots=True)
class HandoffValidation(BaseHandoffValidation):
    model_routing_receipt: ModelRoutingHandoffEvidence | None = None


def _object(value: JsonValue, label: str) -> dict[str, JsonValue]:
    match value:
        case dict():
            return value
        case str() | int() | float() | bool() | None | list():
            raise HandoffContractError(f"{label} must be a JSON object")
        case unreachable:
            assert_never(unreachable)


def _text(value: JsonValue, label: str) -> str:
    match value:
        case str() if value.strip():
            return value
        case str() | int() | float() | bool() | None | list() | dict():
            raise HandoffContractError(f"{label} must be a non-empty string")
        case unreachable:
            assert_never(unreachable)


def _strings(value: JsonValue, label: str) -> list[str]:
    match value:
        case list():
            return [_string_item(item, label) for item in value]
        case str() | int() | float() | bool() | None | dict():
            raise HandoffContractError(f"{label} must be an array of strings")
        case unreachable:
            assert_never(unreachable)


def _string_item(value: JsonValue, label: str) -> str:
    match value:
        case str():
            return value
        case int() | float() | bool() | None | list() | dict():
            raise HandoffContractError(f"{label} must contain only strings")
        case unreachable:
            assert_never(unreachable)


def _read_object(path: Path, label: str) -> dict[str, JsonValue]:
    if not path.is_file():
        raise HandoffContractError(f"{label} local file does not exist")
    try:
        parsed: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise HandoffContractError(f"cannot read {label}") from exc
    except json.JSONDecodeError as exc:
        raise HandoffContractError(f"{label} is not valid JSON: {exc.msg}") from exc
    return _object(parsed, label)


def _local_path(value: JsonValue, label: str) -> tuple[str, Path]:
    reference = _text(value, label)
    if "://" in reference:
        raise HandoffContractError(f"{label} must reference a local file")
    path = Path(reference).expanduser()
    return reference, (path if path.is_absolute() else ROOT / path).resolve()


def _repo_path(value: JsonValue, label: str) -> Path:
    _, path = _local_path(value, label)
    if not path.is_relative_to(ROOT):
        raise HandoffContractError(f"{label} must remain inside the Agent Company repository")
    return path


def _enum(properties: dict[str, JsonValue], field: str) -> set[str]:
    field_schema = _object(properties.get(field), f"handoff policy {field}")
    enum_schema = field_schema
    if field_schema.get("type") == "array":
        enum_schema = _object(field_schema.get("items"), f"handoff policy {field}.items")
    return set(_strings(enum_schema.get("enum"), f"handoff policy {field}.enum"))


def _validate_contract(
    assignment: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> tuple[str | None, str | None, tuple[str, ...], str, bool, bool]:
    role = _text(assignment.get("role"), "assignment role")
    profile_path = _repo_path(assignment.get("profile_ref"), "assignment profile_ref")
    profile = _read_object(profile_path, "assignment profile_ref")
    if _text(profile.get("id"), "profile id") != role:
        raise HandoffContractError("assignment profile id does not match assignment role")
    shape = _object(profile.get("handoff_shape"), "profile handoff_shape")
    policy_path = _repo_path(shape.get("policy_ref"), "handoff_shape policy_ref")
    if policy_path != HANDOFF_POLICY_PATH.resolve():
        raise HandoffContractError("handoff_shape policy_ref must use policies/bounded-handoff.schema.json")
    schema = _read_object(policy_path, "bounded handoff policy")
    required = set(_strings(shape.get("required_fields"), "handoff_shape required_fields"))
    required.update(_strings(schema.get("required"), "bounded handoff required fields"))
    missing = sorted(required - payload.keys())
    if missing:
        raise HandoffContractError(f"worker handoff is missing required fields: {missing}")
    properties = _object(schema.get("properties"), "bounded handoff properties")
    format_schema = _object(properties.get("format"), "handoff policy format")
    expected_format = _text(format_schema.get("const"), "handoff policy format.const")
    if _text(shape.get("format"), "handoff_shape format") != expected_format:
        raise HandoffContractError("profile handoff format disagrees with its policy")
    if payload.get("format") != expected_format:
        raise HandoffContractError(f"worker handoff format must be {expected_format}")
    if payload.get("role") != role:
        raise HandoffContractError(f"worker handoff role does not match assignment role {role}")
    outcome = "completed"
    requests_completion_authority = False
    if role == "qa-release":
        try:
            validate_qa_assignment_binding(
                assignment,
                payload.get("qa_verification"),
            )
            qa_verification = parse_qa_verification(
                payload.get("qa_verification"),
                _text(
                    payload.get("execution_handoff_version"),
                    "worker handoff execution_handoff_version",
                ),
            )
        except (QaAssignmentBindingError, QaHandoffError) as exc:
            raise HandoffContractError(str(exc)) from exc
        if not qa_verification.authorizes_completion:
            outcome = "blocked"
        else:
            requests_completion_authority = True
    elif payload.get("qa_verification") is not None:
        raise HandoffContractError("qa_verification is reserved for qa-release")
    try:
        context_id, knowledge_receipt_id, required_reference_ids, context = (
            validate_execution_knowledge(assignment, payload)
        )
    except HandoffKnowledgeError as exc:
        raise HandoffContractError(str(exc)) from exc
    if role in INTEGRATED_ROLES and context is not None:
        try:
            outcome = validate_role_evidence(
                role=role,
                context=context,
                value=payload.get("role_evidence"),
                expected_context_binding=assignment.get(
                    "role_evidence_context_binding"
                ),
                receipt_ingress=True,
            )
            requests_completion_authority = outcome == "completed"
        except RoleEvidenceError as exc:
            raise HandoffContractError(str(exc)) from exc
    if role not in _enum(properties, "role"):
        raise HandoffContractError(f"assignment role {role} is not allowed by the handoff policy")
    _text(payload.get("objective"), "worker handoff objective")
    scope = _object(payload.get("scope"), "worker handoff scope")
    scope_schema = _object(properties.get("scope"), "handoff policy scope")
    scope_required = set(_strings(scope_schema.get("required"), "handoff policy scope.required"))
    missing_scope = sorted(scope_required - scope.keys())
    if missing_scope:
        raise HandoffContractError(f"worker handoff scope is missing required fields: {missing_scope}")
    for field in SCOPE_LIST_FIELDS:
        _strings(scope.get(field), f"worker handoff scope.{field}")
    _text(scope.get("stop_condition"), "worker handoff scope.stop_condition")
    for field in EVIDENCE_FIELDS:
        _strings(payload.get(field), f"worker handoff {field}")
    next_surface = _text(payload.get("next_recommended_surface"), "worker handoff next_recommended_surface")
    if next_surface not in _enum(properties, "next_recommended_surface"):
        raise HandoffContractError(f"unsupported next_recommended_surface: {next_surface}")
    forbidden_claims = set(_strings(payload.get("forbidden_claims"), "worker handoff forbidden_claims"))
    unsupported_claims = sorted(forbidden_claims - _enum(properties, "forbidden_claims"))
    if unsupported_claims:
        raise HandoffContractError(f"worker handoff forbidden_claims contain unsupported values: {unsupported_claims}")
    try:
        completion_is_assignment_bound = validate_plan_assignment(
            assignment,
            payload,
            scope,
        )
    except HandoffPlanError as exc:
        raise HandoffContractError(str(exc)) from exc
    return (context_id, knowledge_receipt_id, required_reference_ids, outcome, completion_is_assignment_bound, requests_completion_authority)


def validate_worker_handoff(
    assignment: dict[str, JsonValue],
    receipt: dict[str, JsonValue],
) -> HandoffValidation:
    output_ref: str | None = None
    try:
        artifact = read_receipt_handoff(assignment, receipt)
        output_ref = artifact.reference
        (
            context_id,
            knowledge_receipt_id,
            required_reference_ids,
            outcome,
            plan_assignment_bound,
            requests_completion_authority,
        ) = _validate_contract(assignment, artifact.payload)
        routing_receipt = validate_model_routing_handoff(
            assignment,
            artifact.payload,
        )
        assignment_bound = (
            plan_assignment_bound and artifact.receipt_digest_bound
        )
        if requests_completion_authority and not assignment_bound:
            outcome = "blocked"
    except (HandoffArtifactError, HandoffContractError, ModelRoutingHandoffError) as exc:
        return HandoffValidation(
            False,
            output_ref,
            str(exc),
            None,
            None,
            (),
            None,
            False,
        )
    return HandoffValidation(
        True,
        output_ref,
        "valid bounded worker handoff",
        context_id,
        knowledge_receipt_id,
        required_reference_ids,
        outcome,
        assignment_bound,
        routing_receipt,
    )
