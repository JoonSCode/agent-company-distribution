#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_company_deps import JsonValue
from agent_company_model_routing import ModelRoutingRequest, ProfileCapacity
from agent_company_model_routing_models import (
    ModelProfileRegistry,
    ModelRoutingPolicy,
)
from agent_company_plan_models import (
    RolePlanBinding,
    file_sha256,
    item_values,
    load_object,
    object_value,
    runtime_reference,
    text_value,
    text_values,
)
from agent_company_plan_validation import check_plan_files
from agent_company_projection_validation import (
    PolicyError,
    string_list,
    text,
    validate_delegation_gate,
)

JsonObject = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class AssignmentModelRoutingInputs:
    request: ModelRoutingRequest
    registry: ModelProfileRegistry
    policy: ModelRoutingPolicy
    capacity: ProfileCapacity


@dataclass(frozen=True, slots=True)
class PlanDelegationInputs:
    job: JsonObject
    company_plan_path: Path
    role_plan_paths: tuple[Path, ...]
    env: Mapping[str, str]
    model_routing_inputs: Mapping[str, AssignmentModelRoutingInputs] | None = None


@dataclass(frozen=True, slots=True)
class PlanAssignment:
    assignment_id: str
    leaf_id: str
    role: str
    objective: str
    read_scope: tuple[str, ...]
    write_scope: tuple[str, ...]
    outputs: tuple[str, ...]
    forbidden_mutations: tuple[str, ...]
    role_plan_id: str
    role_plan_ref: str
    role_plan_sha256: str
    receipt_ref: str
    receipt_id: str
    qa_verification: JsonValue | None = None
    acceptance_criteria: tuple[str, ...] | None = None
    inputs: tuple[str, ...] = ()
    role_local_qa: tuple[str, ...] = ()
    escalation_triggers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Milestone:
    leaf_id: str
    depends_on: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidatedPlan:
    plan_id: str
    plan_sha256: str
    assignments: tuple[PlanAssignment, ...]
    milestones: tuple[Milestone, ...]


def _parse_assignment(
    value: JsonValue,
    index: int,
    binding: RolePlanBinding,
) -> PlanAssignment:
    path = f"$company.assignments[{index}]"
    raw = object_value(value, path)
    acceptance_criteria = (
        text_values(raw.get("acceptance_criteria"), f"{path}.acceptance_criteria")
        if "acceptance_criteria" in raw
        else None
    )
    assignment = binding
    return PlanAssignment(
        assignment_id=text_value(raw.get("id"), f"{path}.id"),
        leaf_id=text_value(raw.get("leaf_id"), f"{path}.leaf_id"),
        role=text_value(raw.get("role"), f"{path}.role"),
        objective=text_value(raw.get("objective"), f"{path}.objective"),
        read_scope=assignment.read_scope,
        write_scope=assignment.write_scope,
        outputs=assignment.outputs,
        forbidden_mutations=assignment.forbidden_mutations,
        role_plan_id=assignment.role_plan_id,
        role_plan_ref=str(assignment.role_plan_ref),
        role_plan_sha256=assignment.role_plan_sha256,
        receipt_ref=assignment.receipt.ref,
        receipt_id=assignment.receipt.receipt_id,
        qa_verification=assignment.qa_verification,
        acceptance_criteria=acceptance_criteria,
        inputs=assignment.inputs,
        role_local_qa=assignment.role_local_qa,
        escalation_triggers=assignment.escalation_triggers,
    )


def _parse_milestone(value: JsonValue, index: int) -> Milestone:
    path = f"$company.milestones[{index}]"
    raw = object_value(value, path)
    return Milestone(
        text_value(raw.get("id"), f"{path}.id"),
        text_values(
            raw.get("depends_on"),
            f"{path}.depends_on",
            allow_empty=True,
        ),
    )


def _bind_uigwe(
    job: JsonObject,
    plan: JsonObject,
    env: Mapping[str, str],
) -> None:
    validate_delegation_gate(job)
    gate = object_value(job.get("uigwe_gate"), "$job.uigwe_gate")
    binding = object_value(plan.get("uigwe_binding"), "$company.uigwe_binding")
    for kind in ("packet", "decision"):
        _, resolved = runtime_reference(
            binding.get(f"{kind}_ref"),
            f"$company.uigwe_binding.{kind}_ref",
            env,
        )
        plan_sha = text_value(
            binding.get(f"{kind}_sha256"),
            f"$company.uigwe_binding.{kind}_sha256",
        )
        job_ref = text(gate.get(f"{kind}_ref"), f"job Uigwe {kind} ref")
        job_sha = text(gate.get(f"{kind}_sha256"), f"job Uigwe {kind} sha256")
        if (str(resolved), plan_sha) != (job_ref, job_sha):
            raise PolicyError(
                f"company plan Uigwe {kind} bytes do not bind the job",
            )


def validated_plan(inputs: PlanDelegationInputs) -> ValidatedPlan:
    plan_sha256 = file_sha256(inputs.company_plan_path, "stale_state")
    check = check_plan_files(
        inputs.company_plan_path,
        inputs.role_plan_paths,
        inputs.env,
    )
    plan = load_object(inputs.company_plan_path)
    job_id = text(inputs.job.get("job_id"), "job_id")
    objective = text(inputs.job.get("objective"), "objective")
    if text_value(plan.get("job_id"), "$company.job_id") != job_id:
        raise PolicyError("company plan job_id does not bind the job")
    if text_value(plan.get("objective"), "$company.objective") != objective:
        raise PolicyError("company plan objective does not bind the job")
    _bind_uigwe(inputs.job, plan, inputs.env)
    role_bindings = {
        binding.assignment_id: binding
        for binding in check.role_bindings
    }
    assignments_list: list[PlanAssignment] = []
    for index, value in enumerate(
        item_values(plan.get("assignments"), "$company.assignments"),
    ):
        raw = object_value(value, f"$company.assignments[{index}]")
        assignment_id = text_value(
            raw.get("id"),
            f"$company.assignments[{index}].id",
        )
        binding = role_bindings.get(assignment_id)
        if binding is None:
            raise PolicyError(
                f"assignment lacks a validated role plan: {assignment_id}",
            )
        assignments_list.append(_parse_assignment(value, index, binding))
    assignments = tuple(assignments_list)
    milestones = tuple(
        _parse_milestone(value, index)
        for index, value in enumerate(
            item_values(plan.get("milestones"), "$company.milestones"),
        )
    )
    selected = string_list(inputs.job.get("selected_roles"), "selected_roles")
    if len(selected) != len(set(selected)):
        raise PolicyError("selected_roles must contain unique roles")
    plan_roles = {assignment.role for assignment in assignments}
    unexpected = sorted(plan_roles - set(selected))
    missing = sorted(set(selected) - plan_roles)
    if unexpected:
        raise PolicyError(f"plan roles are not selected: {unexpected}")
    if missing:
        raise PolicyError(f"selected role coverage is incomplete: {missing}")
    if check.plan_id != text_value(plan.get("plan_id"), "$company.plan_id"):
        raise PolicyError("validated plan identity changed")
    if file_sha256(inputs.company_plan_path, "stale_state") != plan_sha256:
        raise PolicyError("company plan bytes changed during projection")
    return ValidatedPlan(check.plan_id, plan_sha256, assignments, milestones)
