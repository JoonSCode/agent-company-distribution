#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Import this module from scripts/agent_company_routing.py.
# ─────────────────

from __future__ import annotations

import hashlib
import json
from typing import Final, assert_never

from agent_company_route_contract import (
    CoreRoute,
    JsonObject,
    ProjectionRequest,
    RoutingError,
    canonical_json,
    known_route,
    parse_object,
)


FORMAT: Final[str] = "agent-company.route-decision/v0.2"
ORDINARY_ROLES: Final[frozenset[str]] = frozenset(
    {"founder", "planning", "design", "development", "marketing", "qa-release"}
)
RETAINED_GATES: Final[tuple[str, ...]] = (
    "material-ambiguity",
    "external-action",
    "host-permission",
    "selected-surface-verification",
)


def safe_role_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(values) != len(set(values)) or not set(values).issubset(ORDINARY_ROLES):
        return ()
    return values


def parse_roles(values: tuple[str, ...]) -> tuple[str, ...]:
    if "specialist" in values:
        raise RoutingError(
            "specialist_collision",
            "auxiliary specialist is not an ordinary Company role",
        )
    if len(values) != len(set(values)):
        raise RoutingError("malformed_input", "ordinary_role_ids must be unique")
    unknown = sorted(set(values) - ORDINARY_ROLES)
    if unknown:
        raise RoutingError(
            "malformed_input", f"unknown ordinary role ids: {', '.join(unknown)}"
        )
    return values


def boundary_rejection(
    selected_route: str, roles: tuple[str, ...], error: RoutingError
) -> JsonObject:
    return {
        "format": FORMAT,
        "status": "rejected",
        "lane": "reject",
        "selected_route": selected_route,
        "ordinary_role_ids": list(safe_role_ids(roles)),
        "rejection": {"code": error.code, "detail": error.detail},
    }


def rejection(request: ProjectionRequest, error: RoutingError) -> JsonObject:
    return boundary_rejection(
        request.core.selected_route, request.ordinary_role_ids, error
    )


def accepted(request: ProjectionRequest, lane: str) -> JsonObject:
    role_count = len(request.ordinary_role_ids)
    staffing = (
        "none" if role_count == 0 else "one" if role_count == 1 else "two-or-more"
    )
    skips = ["v0.1-kickoff", "squad", "company-plan"] if lane == "direct" else []
    report: JsonObject = {
        "format": FORMAT,
        "status": "accepted",
        "lane": lane,
        "selected_route": request.core.selected_route,
        "capability_refs": list(request.core.capability_refs),
        "gate_refs": list(request.core.gate_refs),
        "evidence_refs": list(request.core.evidence_refs),
        "recommended_reentry_target": request.core.recommended_reentry_target,
        "ordinary_role_ids": list(request.ordinary_role_ids),
        "core_continues": True,
        "core_authority_sha256": request.core.authority_sha256,
        "core_source_ref": request.core.source_ref,
        "core_source_sha256": request.core.source_sha256,
        "staffing_sha256": hashlib.sha256(
            canonical_json(list(request.ordinary_role_ids)).encode()
        ).hexdigest(),
        "lifecycle": {
            "skips": skips,
            "retained_gates": list(RETAINED_GATES),
            "ordinary_staffing": staffing,
            "auxiliary_specialist_separate": True,
            "external_mutation": request.external_mutation,
            "approval_required": request.approval_required,
        },
    }
    if request.core.backend_json is not None:
        report["backend_provenance"] = parse_object(
            json.loads(request.core.backend_json), "backend_provenance"
        )
    if request.approval_evidence is not None:
        evidence = request.approval_evidence
        report["approval_receipt"] = {
            "receipt_ref": evidence.receipt_ref,
            "receipt_sha256": evidence.receipt_sha256,
            "action_id": evidence.action_id,
            "source_user_decision_ref": evidence.source_user_decision_ref,
        }
    return report


def project(request: ProjectionRequest) -> JsonObject:
    route = known_route(request.core.selected_route)
    if route is None:
        return rejection(
            request,
            RoutingError("unsupported_route", "Core selected an unsupported route"),
        )
    count = len(request.ordinary_role_ids)
    match route:
        case CoreRoute.DIRECT:
            if count > 0:
                return rejection(
                    request,
                    RoutingError(
                        "staffing_not_permitted", "Direct cannot add ordinary roles"
                    ),
                )
            if request.external_mutation and (
                not request.approval_required or request.approval_evidence is None
            ):
                return rejection(
                    request,
                    RoutingError(
                        "approval_gate_missing",
                        "external mutation requires an explicit approval receipt",
                    ),
                )
            return accepted(request, "direct")
        case CoreRoute.BOUNDED | CoreRoute.TEAM:
            return accepted(
                request, "inactive" if count == 0 else "role" if count == 1 else "squad"
            )
        case CoreRoute.RESEARCH | CoreRoute.DRY_RUN:
            if count > 0:
                return rejection(
                    request,
                    RoutingError(
                        "staffing_not_permitted", "Core route forbids ordinary staffing"
                    ),
                )
            return accepted(request, "inactive")
        case unreachable:
            assert_never(unreachable)


def validate_projection(
    candidate: JsonObject, request: ProjectionRequest
) -> JsonObject:
    expected = project(request)
    if candidate.get("role") == "specialist" or candidate.get("ordinary_role_ids") == [
        "specialist"
    ]:
        return rejection(
            request,
            RoutingError(
                "specialist_collision", "auxiliary specialist cannot become a lane role"
            ),
        )
    if request.core.backend_json is None and "backend_provenance" in candidate:
        return rejection(
            request,
            RoutingError(
                "backend_provenance_forged", "Company cannot add backend provenance"
            ),
        )
    if candidate != expected:
        return rejection(
            request,
            RoutingError(
                "stale_state",
                "projection differs from immutable Core or staffing input",
            ),
        )
    return expected
