#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run the focused contract tests:
#      uv run scripts/test_agent_company_plan_delegation.py
# ─────────────────

from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportUnnecessaryIsInstance=false
import copy
from collections.abc import Mapping, Sequence
from itertools import takewhile
from typing import Final

from agent_company_deps import JsonValue
from agent_company_execution_contract import (
    WORKER_PACKET_CANONICAL_ALGORITHM,
    model_routing_binding,
    project_execution_contract,
    worker_packet_sha256,
)
from agent_company_expertise_catalog import load_expertise_catalog
from agent_company_knowledge_context import issue_default_context
from agent_company_model_routing import (
    ModelRoutingDecision,
    ModelRoutingRequest,
    route_model,
)
from agent_company_plan_delegation_binding import (
    AssignmentModelRoutingInputs,
    PlanAssignment,
    PlanDelegationInputs,
    ValidatedPlan,
)
from agent_company_plan_delegation_binding import (
    validated_plan as _validated_plan,
)
from agent_company_plan_design_evidence import (
    design_evidence_context as _design_evidence_context,
)
from agent_company_plan_models import object_value
from agent_company_plan_parallelism import (
    ParallelSlice,
    parallelism_evidence,
    selected_recipe,
)
from agent_company_projection_validation import (
    PolicyError,
    string_list,
    text,
)

JsonObject = dict[str, JsonValue]
CORE_CONTRACTS: Final[JsonObject] = {
    "worker_lifecycle": "king-sejong-core", "worktrees": "king-sejong-core",
    "leases": "king-sejong-core", "retries": "king-sejong-core",
    "receipts": "king-sejong-core", "final_verification": "king-sejong-core",
}
FORBIDDEN_CLAIMS: Final[list[JsonValue]] = ["Uigwe approval", "final synthesis", "final verification", "scope widening"]


def _worker_id(job_id: str, assignment: PlanAssignment) -> str:
    return f"{job_id}-{assignment.role}-{assignment.assignment_id}"


def _scope_root(scope: str) -> tuple[str, ...]:
    parts = (part for part in scope.strip().strip("/").split("/") if part)
    return tuple(takewhile(lambda part: not any(marker in part for marker in "*?["), parts))


def _scopes_overlap(left: str, right: str) -> bool:
    left_root = _scope_root(left)
    right_root = _scope_root(right)
    common = min(len(left_root), len(right_root))
    return not left_root or not right_root or left_root[:common] == right_root[:common]


def _require_disjoint(assignments: tuple[PlanAssignment, ...]) -> None:
    for index, left in enumerate(assignments):
        for right in assignments[index + 1 :]:
            if any(
                _scopes_overlap(left_scope, right_scope)
                for left_scope in left.write_scope
                for right_scope in right.write_scope
            ):
                raise PolicyError(f"parallel assignments have overlapping write_scope: {left.assignment_id}, {right.assignment_id}")


def _waves(plan: ValidatedPlan) -> tuple[tuple[PlanAssignment, ...], ...]:
    milestone_by_leaf = {milestone.leaf_id: milestone for milestone in plan.milestones}
    assignment_by_leaf = {assignment.leaf_id: assignment for assignment in plan.assignments}
    missing = sorted(set(milestone_by_leaf) - set(assignment_by_leaf))
    if missing:
        raise PolicyError(f"milestones have no assignment: {missing}")
    pending = set(milestone_by_leaf)
    completed: set[str] = set()
    result: list[tuple[PlanAssignment, ...]] = []
    while pending:
        ready = tuple(
            assignment_by_leaf[milestone.leaf_id]
            for milestone in plan.milestones
            if milestone.leaf_id in pending and set(milestone.depends_on) <= completed
        )
        _require_disjoint(ready)
        result.append(ready)
        ready_leaves = {assignment.leaf_id for assignment in ready}
        pending -= ready_leaves
        completed |= ready_leaves
    return tuple(result)


def _positive_budget(value: JsonValue, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PolicyError(f"{field} must be a positive integer")
    return value


def _json_strings(values: Sequence[str]) -> list[JsonValue]:
    return [value for value in values]


def _routed_decisions(
    inputs: PlanDelegationInputs,
    plan: ValidatedPlan,
) -> dict[str, tuple[ModelRoutingDecision, JsonObject]]:
    routing_inputs = inputs.model_routing_inputs
    if routing_inputs is None:
        return {}
    if not isinstance(routing_inputs, Mapping):
        raise PolicyError("model routing inputs must be an assignment mapping")
    snapshot = tuple(routing_inputs.items())
    assignments = {
        assignment.assignment_id: assignment
        for assignment in plan.assignments
    }
    if any(type(assignment_id) is not str for assignment_id, _ in snapshot):
        raise PolicyError("model routing inputs must use assignment ids")
    unexpected = sorted({assignment_id for assignment_id, _ in snapshot} - assignments.keys())
    if unexpected:
        raise PolicyError(
            f"model routing inputs have unassigned ids: {unexpected}",
        )
    projected: dict[str, tuple[ModelRoutingDecision, JsonObject]] = {}
    decision_ids: set[str] = set()
    for assignment_id, routing_input in snapshot:
        if type(routing_input) is not AssignmentModelRoutingInputs:
            raise PolicyError("model routing inputs must use AssignmentModelRoutingInputs")
        assignment = assignments[assignment_id]
        if (
            type(routing_input.request) is ModelRoutingRequest
            and routing_input.request.role != assignment.role
        ):
            raise PolicyError(
                f"model routing request role does not bind assignment: {assignment_id}",
            )
        decision = route_model(
            routing_input.request,
            routing_input.registry,
            routing_input.policy,
            routing_input.capacity,
        )
        binding = model_routing_binding(decision)
        decision_id = text(binding.get("decision_id"), "model routing decision id")
        if decision_id in decision_ids:
            raise PolicyError("model routing decision is bound to multiple assignments")
        decision_ids.add(decision_id)
        projected[assignment_id] = (decision, binding)
    return projected


def project_company_plan_delegation(inputs: PlanDelegationInputs) -> JsonObject:
    plan = _validated_plan(inputs)
    routed_decisions = _routed_decisions(inputs, plan)
    waves = _waves(plan)
    squad_recipe = selected_recipe(inputs.job)
    job_id, selected = text(inputs.job.get("job_id"), "job_id"), string_list(inputs.job.get("selected_roles"), "selected_roles")
    expertise_catalog = load_expertise_catalog()
    budget = object_value(inputs.job.get("default_budget"), "$job.default_budget")
    worker_limit = _positive_budget(budget.get("max_total_workers"), "max_total_workers")
    concurrency_limit = _positive_budget(budget.get("max_concurrency"), "max_concurrency")
    spawn_depth_limit = _positive_budget(budget.get("max_spawn_depth"), "max_spawn_depth")
    round_limit = _positive_budget(budget.get("max_rounds"), "max_rounds")
    if len(plan.assignments) > worker_limit or len(waves) > round_limit:
        raise PolicyError("company-plan delegation exceeds the Core budget")
    if any(len(wave) > concurrency_limit for wave in waves):
        raise PolicyError("company-plan delegation exceeds Core concurrency")
    workers: list[JsonValue] = []
    for assignment in plan.assignments:
        context = issue_default_context(
            assignment.role,
            assignment.objective,
            expertise_catalog,
        )
        worker: JsonObject = {
            "worker_id": _worker_id(job_id, assignment),
            "assignment_id": assignment.assignment_id,
            "leaf_id": assignment.leaf_id,
            "stage_id": assignment.leaf_id,
            "role": assignment.role,
            "objective": assignment.objective,
            "profile_ref": f"agents/{assignment.role}.json",
            "knowledge_context_binding": context,
            "read_scope": _json_strings(assignment.read_scope),
            "write_scope": _json_strings(assignment.write_scope),
            "allowed_outputs": _json_strings(assignment.outputs),
            "forbidden_mutations": _json_strings(assignment.forbidden_mutations),
            "role_plan_binding": {
                "role_plan_id": assignment.role_plan_id,
                "ref": assignment.role_plan_ref,
                "sha256": assignment.role_plan_sha256,
            },
            "execution_receipt_binding": {
                "ref": assignment.receipt_ref,
                "receipt_id": assignment.receipt_id,
                "role_plan_id": assignment.role_plan_id,
                "assignment_id": assignment.assignment_id,
                "role": assignment.role,
            },
            "forbidden_claims": list(FORBIDDEN_CLAIMS),
            "stop_condition": "return bounded evidence or an explicit blocker to the Sejong lead",
            "action_authority": "evidence_only",
        }
        role_evidence_context = _design_evidence_context(
            job_id,
            assignment,
            plan,
            context,
        )
        if role_evidence_context is not None:
            worker["role_evidence_context_binding"] = role_evidence_context
        if assignment.qa_verification is not None:
            worker["qa_verification"] = copy.deepcopy(
                assignment.qa_verification,
            )
        routed = routed_decisions.get(assignment.assignment_id)
        if routed is not None:
            decision, routing = routed
            worker["execution_contract"] = project_execution_contract(
                assignment,
                decision,
            )
            worker["model_routing_binding"] = routing
        worker["worker_packet_canonical_algorithm"] = (
            WORKER_PACKET_CANONICAL_ALGORITHM
        )
        worker["worker_packet_sha256"] = worker_packet_sha256(worker)
        workers.append(worker)
    leaf_to_wave = {
        assignment.leaf_id: f"{job_id}-plan-wave-{index}"
        for index, wave in enumerate(waves, start=1)
        for assignment in wave
    }
    milestone_by_leaf = {milestone.leaf_id: milestone for milestone in plan.milestones}
    wave_payloads: list[JsonValue] = []
    for index, wave in enumerate(waves, start=1):
        dependency_waves = sorted({
            leaf_to_wave[dependency]
            for assignment in wave
            for dependency in milestone_by_leaf[assignment.leaf_id].depends_on
        })
        payload: JsonObject = {
            "wave_id": f"{job_id}-plan-wave-{index}",
            "stage_ids": _json_strings([assignment.leaf_id for assignment in wave]),
            "depends_on": _json_strings(dependency_waves),
            "required_worker_ids": _json_strings([
                _worker_id(job_id, assignment)
                for assignment in wave
            ]),
        }
        if len(wave) > 1:
            payload["parallelism_evidence"] = parallelism_evidence(
                squad_recipe,
                tuple(
                    ParallelSlice(
                        assignment.assignment_id,
                        assignment.leaf_id,
                        assignment.role,
                        assignment.objective,
                        milestone_by_leaf[assignment.leaf_id].depends_on,
                    )
                    for assignment in wave
                ),
            )
        wave_payloads.append(payload)
    return {
        "format": "agent-company.core-delegation-input/v0.1",
        "job_id": job_id,
        "job_ref": "agent-company.job/v0.1",
        "selected_roles": _json_strings(selected),
        "company_plan_binding": {
            "plan_id": plan.plan_id,
            "ref": str(inputs.company_plan_path.resolve()),
            "sha256": plan.plan_sha256,
        },
        "budget": {
            "max_total_workers": worker_limit,
            "max_concurrency": concurrency_limit,
            "max_spawn_depth": spawn_depth_limit,
            "max_rounds": round_limit,
        },
        "budget_consumed": {
            "workers": len(plan.assignments),
            "spawn_depth": 0,
            "rounds": len(waves),
        },
        "assignments": workers,
        "waves": wave_payloads,
        "core_contracts": dict(CORE_CONTRACTS),
        "policy_refs": inputs.job.get("policy_refs"),
    }
