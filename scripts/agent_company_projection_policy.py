#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/agent_company_projection_policy.py
# ─────────────────

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from agent_company_deps import JsonValue
from agent_company_expertise_catalog import load_expertise_catalog
from agent_company_knowledge_context import issue_default_context
from agent_company_projection_validation import (
    JsonObject,
    PolicyError,
    object_list,
    parallel_groups,
    read_bound_object,
    string_list,
    text,
    validate_delegation_gate,
)

__all__ = [
    "JsonObject", "PolicyError", "ProjectionInputs", "object_list",
    "project_delegation_input", "read_bound_object", "string_list", "text",
]


FORBIDDEN_CLAIMS: Final[list[JsonValue]] = [
    "Uigwe approval", "final synthesis", "final verification", "scope widening",
]


def json_array(values: Iterable[JsonValue]) -> list[JsonValue]:
    return list(values)


@dataclass(frozen=True, slots=True)
class ProjectionInputs:
    job: JsonObject
    workflow: JsonObject
    recipe: JsonObject
    budget: tuple[int, int, int, int]
    specialist_requests: tuple[JsonObject, ...]
    request_costs: tuple[tuple[int, int, int], ...]
    route_binding: JsonObject | None = None


def project_delegation_input(inputs: ProjectionInputs) -> JsonObject:
    job = inputs.job
    specialist_requests = inputs.specialist_requests
    request_costs = inputs.request_costs
    worker_limit, concurrency_limit, depth_limit, round_limit = inputs.budget
    validate_delegation_gate(job)
    job_id = text(job.get("job_id"), "job_id")
    objective = text(job.get("objective"), "objective")
    selected = string_list(job.get("selected_roles"), "selected_roles")
    expertise_catalog = load_expertise_catalog()
    recipe = inputs.recipe
    workflow = inputs.workflow
    stages = [
        stage for stage in object_list(workflow.get("stages"), "stages")
        if set(selected).intersection(string_list(stage.get("owner_roles"), "owner_roles"))
    ]
    if not specialist_requests:
        stages = [stage for stage in stages if stage.get("id") != "bounded-specialist-input"]
    if not stages:
        raise PolicyError("selected roles do not own an active workflow stage")
    conditional = {
        text(item.get("role"), "conditional role"): text(item.get("when"), "conditional rationale")
        for item in object_list(recipe.get("conditional_roles"), "conditional_roles")
    }
    covered = {role for stage in stages for role in string_list(stage.get("owner_roles"), "owner_roles")}
    missing = [role for role in selected if role not in covered]
    unknown = [role for role in missing if role not in conditional]
    if unknown:
        raise PolicyError(f"selected roles have no workflow ownership: {unknown}")
    request_ids = [text(request.get("request_id"), "request_id") for request in specialist_requests]
    parallel = parallel_groups(stages, recipe)
    groups: list[tuple[list[JsonObject], JsonObject | None]] = []
    consumed_stage_ids: set[str] = set()
    for stage in stages:
        stage_id = text(stage.get("id"), "stage id")
        if stage_id in consumed_stage_ids:
            continue
        match = parallel.get(stage_id)
        if isinstance(match, dict):
            ids = string_list(match.get("stage_ids"), "parallel stage_ids")
            grouped = [item for item in stages if text(item.get("id"), "stage id") in ids]
            match_evidence = match.get("evidence")
            groups.append((grouped, match_evidence if isinstance(match_evidence, dict) else None))
            consumed_stage_ids.update(ids)
        else:
            groups.append(([stage], None))
            consumed_stage_ids.add(stage_id)
    specialist_stage = next((
        index for index, (group, _) in enumerate(groups)
        if any(stage.get("id") == "bounded-specialist-input" for stage in group)
    ), None)
    if specialist_requests and specialist_stage is None:
        raise PolicyError("workflow has no bounded specialist dependency wave")
    assignments: list[JsonValue] = []
    waves: list[JsonValue] = []
    stage_to_wave: dict[str, str] = {}
    downstream_gates: list[str] = []
    for index, (group, evidence) in enumerate(groups, start=1):
        wave_id = f"{job_id}-wave-{index}"
        stage_ids = [text(stage.get("id"), "stage id") for stage in group]
        dependency_ids = {
            stage_to_wave[dependency]
            for stage in group
            for dependency in string_list(stage.get("depends_on"), "depends_on")
            if dependency in stage_to_wave
        }
        dependency_ids.update(downstream_gates)
        worker_ids: list[str] = []
        is_specialist = bool(specialist_requests) and index - 1 == specialist_stage
        if is_specialist:
            for request, (workers, spawn_depth, rounds) in zip(specialist_requests, request_costs, strict=True):
                scope = request.get("scope")
                if not isinstance(scope, dict):
                    raise PolicyError("specialist scope must be an object")
                request_id = text(request.get("request_id"), "request_id")
                for slot in range(1, workers + 1):
                    worker_id = f"{job_id}-specialist-{request_id}-{slot}"
                    worker_ids.append(worker_id)
                    assignments.append({
                        "worker_id": worker_id, "role": "specialist", "stage_id": stage_ids[0],
                        "request_id": request_id, "requester_role": request.get("requester_role"),
                        "specialty": request.get("specialty"), "decision_owner": "sejong-lead",
                        "objective": request.get("decision_question"), "read_refs": scope.get("read_refs"),
                        "allowed_outputs": scope.get("allowed_outputs"), "budget_cost": {
                            "workers": workers, "spawn_depth": spawn_depth, "rounds": rounds,
                        },
                        "forbidden_claims": request.get("forbidden_claims"),
                        "stop_condition": request.get("stop_condition"), "action_authority": "evidence_only",
                    })
        else:
            for stage in group:
                stage_id = text(stage.get("id"), "stage id")
                evidence_outputs = string_list(stage.get("exit_evidence"), "exit_evidence")
                stage_owners = string_list(stage.get("owner_roles"), "owner_roles")
                if stage.get("assignment_mode") == "first-selected":
                    stage_owners = [role for role in stage_owners if role in selected][:1]
                    if not stage_owners:
                        raise PolicyError("first-selected stage has no selected owner")
                for role in stage_owners:
                    if role not in selected:
                        continue
                    worker_id = f"{job_id}-{stage_id}-{role}"
                    worker_objective = f"{stage_id}: {objective}"
                    assignment: JsonObject = {
                        "worker_id": worker_id, "role": role, "stage_id": stage_id,
                        "objective": worker_objective, "profile_ref": f"agents/{role}.json",
                        "knowledge_context_binding": issue_default_context(
                            role,
                            worker_objective,
                            expertise_catalog,
                        ),
                        "allowed_outputs": json_array(evidence_outputs), "forbidden_claims": FORBIDDEN_CLAIMS,
                        "stop_condition": "return bounded evidence or an explicit blocker to the Sejong lead",
                        "action_authority": "evidence_only",
                    }
                    hint = text(stage.get("execution_hint"), "execution_hint")
                    if hint.startswith("approval-gated"):
                        assignment["external_action_id"] = f"{job_id}-{stage_id}"
                        assignment["external_action_requirement"] = "core_receipt_required"
                    assignments.append(assignment)
                    worker_ids.append(worker_id)
            if index == 1:
                for role in missing:
                    worker_id = f"{job_id}-{stage_ids[0]}-{role}-conditional"
                    worker_objective = f"conditional {role} evidence: {objective}"
                    worker_ids.append(worker_id)
                    assignments.append({
                        "worker_id": worker_id, "role": role, "stage_id": stage_ids[0],
                        "assignment_kind": "conditional-role", "selection_rationale": conditional[role],
                        "objective": worker_objective,
                        "profile_ref": f"agents/{role}.json", "allowed_outputs": json_array((conditional[role],)),
                        "knowledge_context_binding": issue_default_context(
                            role,
                            worker_objective,
                            expertise_catalog,
                        ),
                        "forbidden_claims": FORBIDDEN_CLAIMS,
                        "stop_condition": "return bounded evidence or an explicit blocker to the Sejong lead",
                        "action_authority": "evidence_only",
                    })
        wave: JsonObject = {
            "wave_id": wave_id, "stage_ids": json_array(stage_ids), "depends_on": json_array(sorted(dependency_ids)),
            "required_worker_ids": json_array(worker_ids),
        }
        if evidence is not None:
            wave["parallelism_evidence"] = evidence
        if is_specialist:
            wave["kind"] = "specialist"
            wave["specialist_request_ids"] = json_array(request_ids)
            downstream_gates.append(wave_id)
        waves.append(wave)
        for stage_id in stage_ids:
            stage_to_wave[stage_id] = wave_id
    workers_used = len(assignments)
    depth_used = max((cost[1] for cost in request_costs), default=0)
    rounds_used = len(waves) + max((cost[2] - 1 for cost in request_costs), default=0)
    overflow = (
        workers_used > worker_limit or depth_used > depth_limit or rounds_used > round_limit
        or any(len(string_list(wave.get("required_worker_ids"), "required_worker_ids")) > concurrency_limit for wave in object_list(waves, "waves"))
    )
    if overflow:
        roles = ", ".join(missing) if missing else "specialist requests"
        raise PolicyError(f"delegation budget exceeded while projecting {roles}")
    projection: JsonObject = {
        "format": "agent-company.core-delegation-input/v0.1", "job_id": job_id,
        "job_ref": "agent-company.job/v0.1", "selected_roles": json_array(selected),
        "budget": job.get("default_budget"), "budget_consumed": {
            "workers": workers_used, "spawn_depth": depth_used, "rounds": rounds_used,
        },
        "assignments": assignments, "waves": waves, "core_contracts": {
            "delegation_run": "sejong.delegation-run/v0.1-draft",
            "external_actions": "sejong.external-action-receipts/v0.1-draft",
        },
        "policy_refs": job.get("policy_refs"),
    }
    if inputs.route_binding is not None:
        projection["route_binding"] = inputs.route_binding
    return projection
