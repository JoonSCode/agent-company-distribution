#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path
from typing import Final

from agent_company_cycle_models import (
    AdvanceRequest,
    CloseRequest,
    CycleError,
    JsonObject,
    Mutation,
    canonical_time,
    json_array,
    required_text,
)
from agent_company_deps import JsonValue


PHASES: Final[tuple[str, ...]] = (
    "job-created", "planning", "delegating", "executing", "verifying", "commercial-review",
)
SHA256: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}")


def _object(value: JsonValue, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise CycleError("malformed_state", f"{label} must be an object")
    return value


def _objects(value: JsonValue, label: str) -> list[JsonObject]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise CycleError("malformed_state", f"{label} must be an object list")
    return [item for item in value if isinstance(item, dict)]


def _plan_binding(reference: str, expected_sha256: str | None) -> tuple[str, str]:
    if expected_sha256 is None:
        raise CycleError("plan_binding_required", "planning requires plan_sha256")
    if SHA256.fullmatch(expected_sha256) is None:
        raise CycleError("malformed_input", "plan_sha256 must be lowercase SHA-256")
    source = Path(reference).expanduser()
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise CycleError("unsafe_plan_ref", f"cannot resolve planning evidence: {exc}") from exc
    if (
        "://" in reference
        or not source.is_absolute()
        or source.is_symlink()
        or reference != str(resolved)
        or not resolved.is_file()
    ):
        raise CycleError("unsafe_plan_ref", "planning evidence must be a canonical local file")
    try:
        actual_sha256 = hashlib.sha256(resolved.read_bytes()).hexdigest()
    except OSError as exc:
        raise CycleError("unsafe_plan_ref", f"cannot read planning evidence: {exc}") from exc
    if actual_sha256 != expected_sha256:
        raise CycleError("stale_plan", "planning evidence bytes differ from plan_sha256")
    return str(resolved), actual_sha256


def advance(state: JsonObject, request: AdvanceRequest) -> Mutation:
    active = _object(state.get("active_cycle"), "active_cycle")
    if active.get("cycle_id") != required_text(request.cycle_id, "cycle_id"):
        raise CycleError("stale_cycle", "active cycle id does not match")
    current = str(active.get("phase"))
    sequential = (
        current in PHASES
        and request.phase in PHASES
        and PHASES.index(request.phase) == PHASES.index(current) + 1
    )
    if request.phase != "awaiting-approval" and not sequential:
        raise CycleError("invalid_transition", f"cannot advance from {current} to {request.phase}")
    next_state = copy.deepcopy(state)
    next_active = _object(next_state.get("active_cycle"), "active_cycle")
    evidence = next_active.get("evidence_refs")
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        raise CycleError("malformed_state", "active cycle evidence_refs are invalid")
    reference = required_text(request.evidence_ref, "evidence_ref")
    plan_binding: tuple[str, str] | None = None
    if request.phase == "planning":
        plan_binding = _plan_binding(reference, request.plan_sha256)
    elif request.plan_sha256 is not None:
        raise CycleError("malformed_input", "plan_sha256 is valid only for planning")
    next_active["phase"] = request.phase
    next_active["updated_at"] = canonical_time(request.now, "now")
    next_active["evidence_refs"] = [*evidence, *([] if reference in evidence else [reference])]
    result: JsonObject = {
        "status": "advanced", "cycle_id": request.cycle_id, "phase": request.phase,
    }
    if plan_binding is not None:
        portfolio = _object(next_state.get("portfolio"), "portfolio")
        initiatives = _objects(portfolio.get("initiatives"), "initiatives")
        matches = [
            item
            for item in initiatives
            if item.get("initiative_id") == next_active.get("initiative_id")
        ]
        if len(matches) != 1:
            raise CycleError("malformed_state", "active initiative is missing or duplicated")
        plan_ref, plan_sha256 = plan_binding
        matches[0]["plan_ref"] = plan_ref
        matches[0]["plan_sha256"] = plan_sha256
        result.update({"plan_ref": plan_ref, "plan_sha256": plan_sha256})
    return Mutation(next_state, result)


def close(state: JsonObject, request: CloseRequest) -> Mutation:
    active = _object(state.get("active_cycle"), "active_cycle")
    if active.get("cycle_id") != required_text(request.cycle_id, "cycle_id"):
        raise CycleError("stale_cycle", "active cycle id does not match")
    if request.outcome not in {"completed", "stopped"}:
        raise CycleError("malformed_input", "cycle outcome is unsupported")
    next_state = copy.deepcopy(state)
    next_active = _object(next_state.get("active_cycle"), "active_cycle")
    reference = required_text(request.evidence_ref, "evidence_ref")
    evidence = next_active.get("evidence_refs")
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        raise CycleError("malformed_state", "active cycle evidence_refs are invalid")
    closure_refs = [*evidence, *([] if reference in evidence else [reference])]
    portfolio = _object(next_state.get("portfolio"), "portfolio")
    initiatives = _objects(portfolio.get("initiatives"), "initiatives")
    match = [item for item in initiatives if item.get("initiative_id") == active.get("initiative_id")]
    if len(match) != 1:
        raise CycleError("malformed_state", "active initiative is missing or duplicated")
    closed_at = canonical_time(request.now, "now")
    match[0]["status"] = request.outcome
    match[0]["updated_at"] = closed_at
    history = _objects(next_state.get("cycle_history"), "cycle_history")
    history.append({
        "cycle_id": request.cycle_id,
        "initiative_id": str(active["initiative_id"]),
        "tick_key": required_text(active.get("tick_key"), "active cycle tick_key"),
        "outcome": request.outcome,
        "closed_at": closed_at,
        "job_ref": str(active["job_ref"]),
        "handoff_ref": required_text(
            active.get("next_action_ref"),
            "active cycle next_action_ref",
        ),
        "evidence_refs": json_array(closure_refs),
    })
    next_state["cycle_history"] = json_array(history)
    next_state["active_cycle"] = None
    next_state["next_tick_at"] = canonical_time(request.next_tick_at, "next_tick_at")
    return Mutation(next_state, {
        "status": "closed", "cycle_id": request.cycle_id, "outcome": request.outcome,
    })
