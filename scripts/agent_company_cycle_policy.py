#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["jsonschema>=4.25,<5"]
# ///

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Final

from agent_company_cycle_models import (
    CycleError,
    InitiativeRequest,
    JsonObject,
    Mutation,
    TickRequest,
    canonical_time,
    json_array,
    parse_time,
    required_text,
    unique_texts,
)
from agent_company_cycle_store import ROOT, write_immutable
from agent_company_deps import JsonValue
from agent_company_job_policy import JobRequest, PolicyError, build_job


JOB_TYPES: Final[frozenset[str]] = frozenset({
    "new-app", "improvement", "planning", "promotion", "release", "incident", "portfolio",
})
def _object(value: JsonValue, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise CycleError("malformed_state", f"{label} must be an object")
    return value


def _objects(value: JsonValue, label: str) -> list[JsonObject]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise CycleError("malformed_state", f"{label} must be an object list")
    return [item for item in value if isinstance(item, dict)]


def _texts(value: JsonValue, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CycleError("malformed_state", f"{label} must be a text list")
    return tuple(item for item in value if isinstance(item, str))


def default_state(now: str, next_tick_at: str) -> JsonObject:
    _ = canonical_time(now, "now")
    scheduled = canonical_time(next_tick_at, "next_tick_at")
    charter_path = ROOT / "policies" / "company-charter.json"
    try:
        charter_sha256 = hashlib.sha256(charter_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise CycleError("charter_unavailable", f"cannot read company charter: {exc}") from exc
    return {
        "format": "agent-company.company-state/v0.1",
        "company_id": "agent-company",
        "charter_binding": {
            "ref": "policies/company-charter.json",
            "sha256": charter_sha256,
        },
        "revision": 0,
        "fencing_token": 0,
        "next_tick_at": scheduled,
        "last_tick_key": None,
        "last_handoff_ref": None,
        "portfolio": {"apps": [], "initiatives": []},
        "active_cycle": None,
        "cycle_history": [],
        "observations": [],
    }


def enqueue(state: JsonObject, request: InitiativeRequest) -> Mutation:
    if request.origin not in {"ceo-directed", "company-initiated"}:
        raise CycleError("malformed_input", "initiative origin is unsupported")
    if request.job_type not in JOB_TYPES:
        raise CycleError("malformed_input", "initiative job type is unsupported")
    if request.priority < 0:
        raise CycleError("malformed_input", "initiative priority must be non-negative")
    initiative_id = required_text(request.initiative_id, "initiative_id")
    timestamp = canonical_time(request.now, "now")
    next_state = copy.deepcopy(state)
    portfolio = _object(next_state.get("portfolio"), "portfolio")
    if request.app_id is not None:
        apps = _objects(portfolio.get("apps"), "apps")
        if len([item for item in apps if item.get("app_id") == request.app_id]) != 1:
            raise CycleError("unknown_app", "initiative app is missing or duplicated")
    initiatives = _objects(portfolio.get("initiatives"), "initiatives")
    if any(item.get("initiative_id") == initiative_id for item in initiatives):
        raise CycleError("duplicate_initiative", f"initiative already exists: {initiative_id}")
    initiative: JsonObject = {
        "initiative_id": initiative_id,
        "origin": request.origin,
        "app_id": request.app_id,
        "job_type": request.job_type,
        "status": "ready",
        "priority": request.priority,
        "objective": required_text(request.objective, "objective"),
        "commercial_hypothesis": required_text(
            request.commercial_hypothesis, "commercial_hypothesis",
        ),
        "success_metrics": json_array(unique_texts(request.success_metrics, "success_metrics")),
        "failure_metrics": json_array(unique_texts(request.failure_metrics, "failure_metrics")),
        "guardrails": json_array(unique_texts(request.guardrails, "guardrails")),
        "created_at": timestamp,
        "updated_at": timestamp,
        "plan_ref": None,
        "plan_sha256": None,
    }
    initiatives.append(initiative)
    portfolio["initiatives"] = json_array(initiatives)
    return Mutation(next_state, {"status": "enqueued", "initiative_id": initiative_id})


def _discovery_initiative(tick_key: str, now: str) -> JsonObject:
    initiative_id = f"discovery-{hashlib.sha256(tick_key.encode()).hexdigest()[:12]}"
    return {
        "initiative_id": initiative_id,
        "origin": "company-initiated",
        "app_id": None,
        "job_type": "portfolio",
        "status": "ready",
        "priority": 0,
        "objective": "Discover and prioritize the next profitable app opportunity",
        "commercial_hypothesis": "A bounded portfolio review can identify the fastest path to commercial evidence",
        "success_metrics": json_array(("one evidence-backed initiative is ready for CEO-visible execution",)),
        "failure_metrics": json_array(("no opportunity has enough evidence for a bounded experiment",)),
        "guardrails": json_array(("external mutation, publication, and spend require explicit CEO approval",)),
        "created_at": now,
        "updated_at": now,
        "plan_ref": None,
        "plan_sha256": None,
    }


def _job_for(initiative: JsonObject, cycle_id: str, tick_key: str) -> JsonObject:
    job_type = str(initiative["job_type"])
    app_id = initiative.get("app_id")
    target_kind = "new-app" if job_type == "new-app" else "existing-app" if app_id else "portfolio"
    plan_question = (
        "Approve the byte-bound company plan, worker scopes, metrics, and guardrails for this cycle",
        "The answer can change execution topology, accepted risk, and the commercial evidence bar",
    )
    try:
        return build_job(JobRequest(
            f"job-{cycle_id}",
            job_type,
            str(initiative["objective"]),
            f"Company resumable tick {tick_key}",
            (),
            (plan_question,),
            job_type in {"improvement", "promotion", "portfolio"},
            initiative_origin=str(initiative["origin"]),
            initiative_id=str(initiative["initiative_id"]),
            target_kind=target_kind,
            target_ref=f"app://{app_id}" if app_id else "company://portfolio",
            commercial_hypothesis=str(initiative["commercial_hypothesis"]),
            success_metrics=_texts(initiative.get("success_metrics"), "success_metrics"),
            failure_metrics=_texts(initiative.get("failure_metrics"), "failure_metrics"),
            guardrails=_texts(initiative.get("guardrails"), "guardrails"),
        ))
    except PolicyError as exc:
        raise CycleError("job_projection_failed", str(exc)) from exc


def tick(state: JsonObject, request: TickRequest) -> Mutation:
    tick_key = required_text(request.tick_key, "tick_key")
    now = canonical_time(request.now, "now")
    historical = [
        item
        for item in _objects(state.get("cycle_history"), "cycle_history")
        if item.get("tick_key") == tick_key
    ]
    if len(historical) > 1:
        raise CycleError("malformed_state", "tick key appears more than once in cycle history")
    if historical:
        closure = historical[0]
        return Mutation(None, {
            "status": "duplicate",
            "cycle_id": closure.get("cycle_id"),
            "initiative_id": closure.get("initiative_id"),
            "handoff_ref": closure.get("handoff_ref"),
        })
    if state.get("last_tick_key") == tick_key:
        active = state.get("active_cycle")
        return Mutation(None, {
            "status": "duplicate",
            "cycle_id": active.get("cycle_id") if isinstance(active, dict) else None,
            "initiative_id": active.get("initiative_id") if isinstance(active, dict) else None,
            "handoff_ref": state.get("last_handoff_ref"),
        })
    if parse_time(now, "now") < parse_time(str(state["next_tick_at"]), "next_tick_at"):
        return Mutation(None, {"status": "not-due", "next_tick_at": state["next_tick_at"]})
    active = state.get("active_cycle")
    if isinstance(active, dict):
        return Mutation(None, {
            "status": "active-cycle",
            "cycle_id": active.get("cycle_id"),
            "initiative_id": active.get("initiative_id"),
        })
    next_state = copy.deepcopy(state)
    portfolio = _object(next_state.get("portfolio"), "portfolio")
    initiatives = _objects(portfolio.get("initiatives"), "initiatives")
    ready = [item for item in initiatives if item.get("status") == "ready"]
    source = "ready-queue"
    if ready:
        ready.sort(key=lambda item: (-int(str(item["priority"])), str(item["created_at"]), str(item["initiative_id"])))
        initiative = ready[0]
    else:
        initiative = _discovery_initiative(tick_key, now)
        initiatives.append(initiative)
        portfolio["initiatives"] = json_array(initiatives)
        source = "portfolio-discovery"
    initiative_id = str(initiative["initiative_id"])
    cycle_id = f"cycle-{hashlib.sha256(f'{tick_key}:{initiative_id}'.encode()).hexdigest()[:16]}"
    job = _job_for(initiative, cycle_id, tick_key)
    output_root = Path(request.handoff_dir).expanduser().resolve()
    job_ref = write_immutable(output_root / f"{cycle_id}.job.json", job)
    job_sha256 = hashlib.sha256(Path(job_ref).read_bytes()).hexdigest()
    handoff: JsonObject = {
        "format": "agent-company.cycle-handoff/v0.1",
        "cycle_id": cycle_id,
        "initiative_id": initiative_id,
        "tick_key": tick_key,
        "job_ref": job_ref,
        "job_sha256": job_sha256,
        "next_action": "route-and-create-byte-bound-company-plan",
        "core_boundary": {
            "dispatch_enabled": False,
            "execution_owner": "king-sejong-core",
            "worker_lifecycle_owner": "king-sejong-core",
            "final_verification_owner": "seungjeongwon",
            "external_action_authority": "explicit-ceo-approval",
        },
        "state_transition": {
            "from_revision": state["revision"],
            "to_revision": int(str(state["revision"])) + 1,
            "fencing_token": int(str(state["fencing_token"])) + 1,
        },
    }
    handoff_ref = write_immutable(output_root / f"{cycle_id}.handoff.json", handoff)
    initiative["status"] = "active"
    initiative["updated_at"] = now
    next_state["last_tick_key"] = tick_key
    next_state["last_handoff_ref"] = handoff_ref
    next_state["active_cycle"] = {
        "cycle_id": cycle_id,
        "initiative_id": initiative_id,
        "tick_key": tick_key,
        "phase": "job-created",
        "started_at": now,
        "updated_at": now,
        "job_ref": job_ref,
        "next_action_ref": handoff_ref,
        "evidence_refs": [],
    }
    return Mutation(next_state, {
        "status": "started", "cycle_id": cycle_id, "initiative_id": initiative_id,
        "initiative_source": source, "job_ref": job_ref, "handoff_ref": handoff_ref,
    })
