#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Import this policy module from Agent Company front-door code.
# 2. Verify with: uv run scripts/test_agent_company_front_door_security.py
# ──────────────────

from __future__ import annotations

from agent_company_front_door_route import (
    FrontDoorError as FrontDoorError,
    FrontDoorRequest,
    ValidatedRoute as ValidatedRoute,
    text as _text,
    validate_route_decision,
)
from agent_company_route_contract import (
    JsonObject,
    JsonValue,
)


def project_front_door(
    decision: JsonObject, request: FrontDoorRequest, objective: str,
) -> JsonObject:
    route = validate_route_decision(decision, request)
    objective = _text(objective, "objective")
    verification = "selected-surface" if route.lane == "direct" else "seungjeongwon"
    assignments: list[JsonValue] = []
    if route.lane == "role":
        assignments = [{
            "role": route.roles[0], "objective": objective,
            "action_authority": "evidence_only",
            "verification_owner": verification,
        }]
    return {
        "format": "agent-company.front-door/v0.2", "lane": route.lane,
        "objective": objective, "company_job": None,
        "ordinary_assignments": assignments, "verification_owner": verification,
    }


def bind_squad_job(
    job: JsonObject, decision: JsonObject, request: FrontDoorRequest,
) -> JsonObject:
    from agent_company_front_door_binding import bind_squad_job as bind

    return bind(job, decision, request)


def validate_job_route_binding(job: JsonObject) -> JsonObject | None:
    from agent_company_front_door_binding import validate_job_route_binding as validate

    return validate(job)
