#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Import via agent_company_front_door_policy.py.
# 2. Verify with: uv run scripts/test_agent_company_front_door_security.py
# ──────────────────

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final
from urllib.parse import unquote, urlsplit

from agent_company_front_door_route import (
    FrontDoorError,
    FrontDoorRequest,
    validate_route_decision,
)
from agent_company_projection_validation import read_bound_object
from agent_company_route_contract import JsonObject, JsonValue, canonical_json
from agent_company_route_policy import ORDINARY_ROLES


KEYS: Final[frozenset[str]] = frozenset({
    "format", "core_decision_ref", "core_decision_sha256", "ordinary_role_ids",
    "external_mutation", "approval_required", "route_decision",
    "route_decision_sha256", "route_binding_sha256",
})


def _roles(value: JsonValue) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise FrontDoorError("malformed_route", "ordinary_role_ids must be a list")
    roles = tuple(item for item in value if isinstance(item, str))
    if len(roles) != len(set(roles)) or not set(roles).issubset(ORDINARY_ROLES):
        raise FrontDoorError("malformed_route", "ordinary roles must be unique and supported")
    return roles


def _digest(value: JsonValue) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _sha(value: JsonValue, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise FrontDoorError("malformed_route", f"{label} must be a lowercase sha256")
    return value


def _canonical_core_location(reference: str) -> tuple[Path, str]:
    parsed = urlsplit(reference)
    if parsed.scheme:
        if (
            parsed.scheme != "file"
            or parsed.netloc
            or parsed.query
            or parsed.fragment
        ):
            raise FrontDoorError(
                "noncanonical_core_ref",
                "Core decision URI must be a canonical local file URI",
            )
        path = Path(unquote(parsed.path)).resolve()
        canonical_ref = path.as_uri()
    else:
        path = Path(reference).expanduser().resolve()
        canonical_ref = str(path)
    if reference != canonical_ref:
        raise FrontDoorError(
            "noncanonical_core_ref",
            "Core decision ref must be canonical and contain no symlinks",
        )
    return path, canonical_ref


def _canonical_core(request: FrontDoorRequest) -> tuple[JsonObject, str, str]:
    path, canonical_ref = _canonical_core_location(request.core_source_ref)
    core, loaded_ref, source_sha = read_bound_object(str(path), "Core decision")
    if loaded_ref != str(path):
        raise FrontDoorError("noncanonical_core_ref", "Core decision path changed while loading")
    if core != request.core_decision or source_sha != request.core_source_sha256:
        raise FrontDoorError("stale_core_source", "loaded Core source differs from the front-door request")
    return core, canonical_ref, source_sha


def bind_squad_job(
    job: JsonObject, decision: JsonObject, request: FrontDoorRequest,
) -> JsonObject:
    _, core_ref, core_sha = _canonical_core(request)
    route = validate_route_decision(decision, request)
    if route.lane != "squad":
        raise FrontDoorError("wrong_lifecycle", "only Squad uses the v0.1 company-job lifecycle")
    selected = _roles(job.get("selected_roles"))
    if selected != route.roles:
        raise FrontDoorError("stale_staffing", "job staffing differs from the accepted route")
    binding: JsonObject = {
        "format": "agent-company.route-binding/v0.2",
        "core_decision_ref": core_ref,
        "core_decision_sha256": core_sha,
        "ordinary_role_ids": list(selected),
        "external_mutation": request.external_mutation,
        "approval_required": request.approval_required,
        "route_decision": decision,
        "route_decision_sha256": _digest(decision),
    }
    binding["route_binding_sha256"] = _digest(binding)
    bound = dict(job)
    bound["route_binding"] = binding
    return bound


def validate_job_route_binding(job: JsonObject) -> JsonObject | None:
    value = job.get("route_binding")
    if value is None:
        return None
    if not isinstance(value, dict) or frozenset(value) != KEYS or value.get("format") != "agent-company.route-binding/v0.2":
        raise FrontDoorError("malformed_route", "job route_binding fields are invalid")
    unsigned = {key: item for key, item in value.items() if key != "route_binding_sha256"}
    if _sha(value.get("route_binding_sha256"), "route_binding_sha256") != _digest(unsigned):
        raise FrontDoorError("stale_route", "route binding mutated after acceptance")
    core_ref = value.get("core_decision_ref")
    if not isinstance(core_ref, str):
        raise FrontDoorError("malformed_route", "core_decision_ref must be text")
    core_path, canonical_ref = _canonical_core_location(core_ref)
    core, loaded_ref, source_sha = read_bound_object(str(core_path), "Core decision")
    if loaded_ref != str(core_path):
        raise FrontDoorError("noncanonical_core_ref", "Core decision path changed while loading")
    if canonical_ref != core_ref or _sha(value.get("core_decision_sha256"), "core_decision_sha256") != source_sha:
        raise FrontDoorError("stale_core_source", "Core source bytes changed after route binding")
    selected = _roles(job.get("selected_roles"))
    if selected != _roles(value.get("ordinary_role_ids")):
        raise FrontDoorError("stale_staffing", "job staffing mutated after route acceptance")
    route_decision = value.get("route_decision")
    if not isinstance(route_decision, dict):
        raise FrontDoorError("malformed_route", "route_decision must be an object")
    if _sha(value.get("route_decision_sha256"), "route_decision_sha256") != _digest(route_decision):
        raise FrontDoorError("stale_route", "route decision bytes changed after binding")
    external = value.get("external_mutation")
    approval = value.get("approval_required")
    if not isinstance(external, bool) or not isinstance(approval, bool):
        raise FrontDoorError("malformed_route", "binding gate flags must be boolean")
    request = FrontDoorRequest(
        core,
        selected,
        external,
        approval,
        core_ref,
        _sha(value.get("core_decision_sha256"), "core_decision_sha256"),
    )
    route = validate_route_decision(route_decision, request)
    if route.lane != "squad":
        raise FrontDoorError("wrong_lifecycle", "v0.1 company jobs require Squad")
    return value
