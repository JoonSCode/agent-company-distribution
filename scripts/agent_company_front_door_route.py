#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, override

from agent_company_route_contract import (
    ApprovalEvidence,
    JsonObject,
    JsonValue,
    ProjectionRequest,
    RoutingError,
    parse_core,
)
from agent_company_route_policy import (
    parse_roles,
    project,
    validate_projection,
)


Lane = Literal["direct", "role", "squad"]
LANES: Final[dict[str, Lane]] = {
    "direct": "direct",
    "role": "role",
    "squad": "squad",
}


@dataclass(frozen=True, slots=True)
class FrontDoorError(Exception):
    code: str
    detail: str
    reentry: str | None = None

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class FrontDoorRequest:
    core_decision: JsonObject
    ordinary_role_ids: tuple[str, ...]
    external_mutation: bool
    approval_required: bool
    core_source_ref: str
    core_source_sha256: str
    approval_evidence: ApprovalEvidence | None = None


@dataclass(frozen=True, slots=True)
class ValidatedRoute:
    lane: Lane
    roles: tuple[str, ...]
    route_decision: JsonObject
    request: FrontDoorRequest


def text(value: JsonValue, label: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    raise FrontDoorError("malformed_route", f"{label} must be non-empty text")


def _boolean(value: JsonValue, label: str) -> bool:
    if not isinstance(value, bool):
        raise FrontDoorError("malformed_route", f"{label} must be boolean")
    return value


def _rejection_error(rejected: JsonObject) -> FrontDoorError:
    detail = rejected.get("rejection")
    if not isinstance(detail, dict):
        return FrontDoorError("malformed_route", "route projection rejection is malformed")
    code = text(detail.get("code"), "rejection code")
    message = text(detail.get("detail"), "rejection detail")
    reentry = "uigwe" if code == "approval_gate_missing" else None
    return FrontDoorError(code, message, reentry)


def _projection_request(request: FrontDoorRequest) -> ProjectionRequest:
    external_mutation = _boolean(request.external_mutation, "external_mutation")
    approval_required = _boolean(request.approval_required, "approval_required")
    try:
        roles = parse_roles(request.ordinary_role_ids)
        core = parse_core(
            request.core_decision,
            request.core_source_ref,
            request.core_source_sha256,
        )
    except RoutingError as exc:
        raise FrontDoorError(exc.code, exc.detail) from exc
    return ProjectionRequest(
        core,
        roles,
        external_mutation,
        approval_required,
        request.approval_evidence,
    )


def validate_route_decision(
    decision: JsonObject, request: FrontDoorRequest,
) -> ValidatedRoute:
    projection_request = _projection_request(request)
    expected = project(projection_request)
    if expected.get("status") != "accepted":
        raise _rejection_error(expected)
    checked = validate_projection(decision, projection_request)
    if checked != decision or checked.get("status") != "accepted":
        raise _rejection_error(checked)
    lane_value = checked.get("lane")
    lane = LANES.get(lane_value) if isinstance(lane_value, str) else None
    if lane is None:
        raise FrontDoorError("inactive_route", "route cannot start Company work")
    return ValidatedRoute(lane, projection_request.ordinary_role_ids, checked, request)
