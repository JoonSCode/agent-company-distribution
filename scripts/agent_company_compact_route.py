#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Import bind_route_decision from this module.
# ─────────────────

"""Bind compact lanes to Todo 1's validated Core route semantics."""

from __future__ import annotations
# pyright: reportAny=false, reportImplicitRelativeImport=false

import hashlib
import json
from typing import TypeAlias

from agent_company_compact_models import ValidatedRoute
from agent_company_compact_evidence import parse_evidence_ref
from agent_company_route_contract import (
    JsonObject,
    JsonValue,
    ProjectionRequest,
    RoutingError,
    TextListRule,
    parse_core,
    parse_object,
    parse_texts,
)
from agent_company_route_policy import parse_roles, validate_projection
from agent_company_projection_policy import PolicyError


JsonMap: TypeAlias = dict[str, JsonValue]


def _json(payload: bytes, label: str) -> JsonObject:
    try:
        value: JsonValue = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PolicyError(f"{label} bytes are invalid JSON: {exc}") from exc
    try:
        return parse_object(value, label)
    except RoutingError as exc:
        raise PolicyError(str(exc)) from exc


def _bind(
    candidate_payload: bytes,
    core_payload: bytes,
    external_mutation: bool,
    approval_required: bool,
) -> ValidatedRoute:
    candidate = _json(candidate_payload, "route decision")
    core_input = _json(core_payload, "Core decision")
    core_digest = hashlib.sha256(core_payload).hexdigest()
    source_ref = f"core://agent-company/route-input/{core_digest}.json"
    try:
        core = parse_core(core_input, source_ref)
        roles = parse_roles(parse_texts(
            candidate.get("ordinary_role_ids"),
            TextListRule("ordinary_role_ids", allow_empty=True),
        ))
        request = ProjectionRequest(
            core, roles, external_mutation, approval_required,
        )
        validated = validate_projection(candidate, request)
    except RoutingError as exc:
        raise PolicyError(str(exc)) from exc
    if validated.get("status") != "accepted":
        rejection = validated.get("rejection")
        detail = rejection.get("detail") if isinstance(rejection, dict) else "route validation rejected"
        raise PolicyError(f"route decision is not Todo 1 validated: {detail}")
    lane = validated.get("lane")
    if not isinstance(lane, str) or lane not in {"direct", "role", "squad"}:
        raise PolicyError("route decision is not a compact success lane")
    refs: list[str] = []
    for field in ("capability_refs", "gate_refs", "evidence_refs"):
        values = parse_texts(validated.get(field), TextListRule(field))
        parsed_refs = tuple(
            parse_evidence_ref(value, f"{field} evidence reference") for value in values
        )
        if len(parsed_refs) != len(set(parsed_refs)):
            raise PolicyError(f"{field} evidence references collide after decoding")
        refs.extend(parsed_refs)
    return ValidatedRoute(
        lane,
        roles,
        tuple(refs),
        candidate_payload,
        core_payload,
        external_mutation,
        approval_required,
    )


def bind_route_decision(
    candidate_payload: bytes,
    core_payload: bytes,
    *,
    external_mutation: bool = False,
    approval_required: bool = False,
) -> ValidatedRoute:
    """Return an immutable route only after Todo 1 exact-projection validation."""
    return _bind(candidate_payload, core_payload, external_mutation, approval_required)


def validate_route_binding(route: ValidatedRoute) -> ValidatedRoute:
    """Reject a constructed or replaced binding before projection or render."""
    rebound = _bind(
        route.candidate_payload,
        route.core_payload,
        route.external_mutation,
        route.approval_required,
    )
    if rebound != route:
        raise PolicyError("route binding differs from its validated bytes")
    return rebound
