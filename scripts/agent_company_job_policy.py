#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/agent_company_jobs.py --help
# 3. Or make executable and run:
#      chmod +x scripts/agent_company_jobs.py && ./scripts/agent_company_jobs.py --help
# ─────────────────

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from agent_company_deps import JsonValue
from agent_company_front_door_policy import validate_job_route_binding
from agent_company_job_definition import (
    JOB_TYPES,
    JobRequest,
    ROLES,
    ROOT,
    build_job,
    classify,
    read_object,
    recipe,
    validate_company_context,
    write_object,
    write_text,
)
from agent_company_projection_policy import (
    PolicyError,
    ProjectionInputs,
    object_list,
    project_delegation_input,
    read_bound_object,
    string_list,
    text,
)


__all__ = [
    "JOB_TYPES", "ROLES", "JobRequest", "PolicyError", "approve_uigwe", "build_delegation_input",
    "build_job", "classify", "object_list", "read_object", "string_list", "text",
    "write_object", "write_text",
]



def approve_uigwe(
    job: dict[str, JsonValue],
    decision: dict[str, JsonValue] | str,
    decision_ref: str | None = None,
) -> dict[str, JsonValue]:
    gate = job.get("uigwe_gate")
    if (
        not isinstance(gate, dict)
        or gate != {"required": True, "status": "pending-user"}
    ):
        raise PolicyError("job has no pending Uigwe approval")
    if not isinstance(decision, dict) or decision_ref is None:
        raise PolicyError("loaded Uigwe decision object and decision ref are required")
    if decision.get("format") != "agent-company.uigwe-decision/v0.1":
        raise PolicyError("Uigwe decision format is invalid")
    job_id = text(job.get("job_id"), "job_id")
    if decision.get("job_id") != job_id:
        raise PolicyError("Uigwe decision job_id does not match the job")
    if decision.get("decision_authority") not in {"user", "ceo"}:
        raise PolicyError("Uigwe decision authority must be user or CEO")
    packet = decision.get("uigwe_packet")
    if not isinstance(packet, dict) or packet.get("job_id") != job_id:
        raise PolicyError("Uigwe packet must be bound to the same job")
    packet_ref = text(packet.get("ref"), "Uigwe packet ref")
    packet_object, canonical_packet_ref, packet_sha = read_bound_object(packet_ref, "Uigwe packet")
    packet_format = packet_object.get("format")
    if (
        not isinstance(packet_format, str)
        or not packet_format.startswith("uigwe.")
        or packet_object.get("approval_status") != "approved"
    ):
        raise PolicyError("Uigwe packet must be an approved Uigwe artifact")
    resolutions = object_list(decision.get("resolutions"), "Uigwe resolutions")
    resolved_questions = [text(item.get("question"), "resolved question") for item in resolutions]
    for item in resolutions:
        _ = text(item.get("resolution"), "Uigwe resolution")
    material = object_list(job.get("material_ambiguities"), "material_ambiguities")
    questions = [text(item.get("question"), "material question") for item in material]
    if len(resolved_questions) != len(set(resolved_questions)) or set(resolved_questions) != set(questions):
        raise PolicyError("Uigwe decision must resolve every material ambiguity exactly once")
    decision_ref = text(decision_ref, "Uigwe decision ref")
    decision_object, canonical_decision_ref, decision_sha = read_bound_object(decision_ref, "Uigwe decision")
    if decision_object != decision:
        raise PolicyError("Uigwe decision ref must identify the exact loaded decision artifact")
    updated = dict(job)
    updated["uigwe_gate"] = {
        "required": True,
        "status": "approved",
        "packet_ref": canonical_packet_ref,
        "packet_refs": [canonical_packet_ref],
        "packet_sha256": packet_sha,
        "decision_ref": canonical_decision_ref,
        "decision_hash": decision_sha,
        "decision_sha256": decision_sha,
    }
    return updated


def validate_specialist_request(
    request: dict[str, JsonValue], job_id: str, selected: list[str]
) -> tuple[int, int, int]:
    if request.get("format") != "agent-company.specialist-request/v0.1":
        raise PolicyError("specialist request format is invalid")
    if request.get("job_id") != job_id:
        raise PolicyError("specialist request job_id does not match the job")
    requester = text(request.get("requester_role"), "requester_role")
    if requester not in selected:
        raise PolicyError(f"specialist requester is not selected: {requester}")
    if request.get("decision_owner") != "sejong-lead":
        raise PolicyError("specialist decision_owner must be sejong-lead")
    for field in ("request_id", "specialty", "decision_question", "expected_output", "stop_condition"):
        _ = text(request.get(field), field)
    if not string_list(request.get("missing_evidence"), "missing_evidence"):
        raise PolicyError("specialist missing_evidence must not be empty")
    scope = request.get("scope")
    cost = request.get("budget_cost")
    if not isinstance(scope, dict) or not isinstance(cost, dict):
        raise PolicyError("specialist scope and budget_cost must be objects")
    _ = string_list(scope.get("read_refs"), "specialist read_refs")
    if not string_list(scope.get("allowed_outputs"), "specialist allowed_outputs"):
        raise PolicyError("specialist allowed_outputs must not be empty")
    if "final verification" not in string_list(request.get("forbidden_claims"), "specialist forbidden_claims"):
        raise PolicyError("specialist forbidden_claims must include final verification")
    values = (cost.get("workers"), cost.get("spawn_depth"), cost.get("rounds"))
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise PolicyError("specialist budget values must be integers")
    workers, spawn_depth, rounds = values
    if not isinstance(workers, int) or not isinstance(spawn_depth, int) or not isinstance(rounds, int):
        raise PolicyError("specialist budget values must be integers")
    if workers < 1 or spawn_depth < 0 or rounds < 1:
        raise PolicyError("specialist budget values are outside their allowed ranges")
    return workers, spawn_depth, rounds


def _positive_budget(value: JsonValue, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PolicyError(f"{label} must be a positive integer")
    return value


def build_delegation_input(
    job: dict[str, JsonValue],
    *,
    specialist_requests: tuple[dict[str, JsonValue], ...] = (),
    company_plan_path: Path | None = None,
    role_plan_paths: tuple[Path, ...] = (),
    env: Mapping[str, str] | None = None,
) -> dict[str, JsonValue]:
    validate_company_context(job)
    job_type = text(job.get("job_type"), "job_type")
    workflow_ref = text(job.get("workflow_ref"), "workflow_ref")
    budget = job.get("default_budget")
    if not isinstance(budget, dict):
        raise PolicyError("default_budget must be an object")
    budget_values = (
        _positive_budget(budget.get("max_total_workers"), "max_total_workers"),
        _positive_budget(budget.get("max_concurrency"), "max_concurrency"),
        _positive_budget(budget.get("max_spawn_depth"), "max_spawn_depth"),
        _positive_budget(budget.get("max_rounds"), "max_rounds"),
    )
    job_id = text(job.get("job_id"), "job_id")
    selected = string_list(job.get("selected_roles"), "selected_roles")
    costs = tuple(validate_specialist_request(request, job_id, selected) for request in specialist_requests)
    request_ids = [text(request.get("request_id"), "request_id") for request in specialist_requests]
    if len(request_ids) != len(set(request_ids)):
        raise PolicyError("specialist request_id values must be unique")
    route_binding = validate_job_route_binding(job)
    if company_plan_path is not None:
        if specialist_requests:
            raise PolicyError("company-plan delegation does not accept specialist requests")
        if not role_plan_paths:
            raise PolicyError("company-plan delegation requires role plans")
        from agent_company_plan_delegation import (
            PlanDelegationInputs,
            project_company_plan_delegation,
        )

        projection = project_company_plan_delegation(PlanDelegationInputs(
            job,
            company_plan_path,
            role_plan_paths,
            env if env is not None else os.environ,
        ))
        if route_binding is not None:
            projection["route_binding"] = route_binding
        if job.get("company_context") is not None:
            projection["company_context"] = job["company_context"]
        return projection
    if role_plan_paths:
        raise PolicyError("role plans require a company plan")
    inputs = ProjectionInputs(
        job=job,
        workflow=read_object(ROOT / workflow_ref),
        recipe=recipe(job_type),
        budget=budget_values,
        specialist_requests=specialist_requests,
        request_costs=costs,
        route_binding=route_binding,
    )
    projection = project_delegation_input(inputs)
    if job.get("company_context") is not None:
        projection["company_context"] = job["company_context"]
    return projection
