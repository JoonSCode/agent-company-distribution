#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Import bind_canonical_report from this module.
# ─────────────────

"""Strictly bind canonical v0.1 report bytes for compact projection."""

from __future__ import annotations
# pyright: reportAny=false, reportImplicitRelativeImport=false

import hashlib
import json
import re
from typing import Final, TypeAlias

from agent_company_deps import JsonValue
from agent_company_compact_models import (
    CanonicalBinding,
    CanonicalEntry,
    CanonicalReport,
    EvidenceState,
    OverallState,
)
from agent_company_compact_evidence import contains_unsafe_control, parse_evidence_ref
from agent_company_projection_policy import PolicyError


JsonObject: TypeAlias = dict[str, JsonValue]
ROOT_KEYS: Final = frozenset({
    "format", "job_id", "job_type", "objective", "overall_status",
    "decision_summary", "role_deliveries", "external_actions", "claims",
    "user_decisions", "risks", "next_actions",
})
JOB_TYPES: Final = frozenset({
    "new-app", "improvement", "planning", "promotion", "release", "incident", "portfolio",
})
ROLES: Final = frozenset({
    "founder", "planning", "design", "development", "marketing", "qa-release", "specialist",
})
ORDINARY_ROLES: Final = ROLES - {"specialist"}
DELIVERY_KEYS: Final = frozenset({"role", "worker_ref", "state", "summary", "evidence_refs"})
ACTION_KEYS: Final = frozenset({"action_id", "action_name", "target", "state", "evidence_refs"})
CLAIM_KEYS: Final = frozenset({"claim", "state", "evidence_refs"})
JOB_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _object(value: JsonValue, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise PolicyError(f"{label} must be an object")
    return value


def _objects(value: JsonValue, label: str, *, require_one: bool = False) -> tuple[JsonObject, ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise PolicyError(f"{label} must be an object list")
    items = tuple(item for item in value if isinstance(item, dict))
    if require_one and not items:
        raise PolicyError(f"{label} must contain at least one canonical item")
    return items


def _text(value: JsonValue, label: str, *, visible: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise PolicyError(f"{label} must be non-empty text")
    if visible and contains_unsafe_control(value):
        raise PolicyError(f"{label} contains control characters")
    return value


def _texts(value: JsonValue, label: str, *, visible: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PolicyError(f"{label} must be a string list")
    return tuple(_text(item, f"{label} item", visible=visible) for item in value)


def _refs(value: JsonValue, label: str, state: EvidenceState) -> tuple[str, ...]:
    refs = tuple(parse_evidence_ref(ref, label) for ref in _texts(value, label, visible=True))
    if len(refs) != len(set(refs)):
        raise PolicyError(f"{label} must contain unique references")
    if state is EvidenceState.VERIFIED and not refs:
        raise PolicyError(f"{label} must bind verified evidence")
    return refs


def _state(value: JsonValue, label: str) -> EvidenceState:
    try:
        return EvidenceState(_text(value, label))
    except ValueError as exc:
        raise PolicyError(f"{label} has an unsupported state") from exc


def _entry(item: JsonObject, kind: str) -> CanonicalEntry:
    expected = DELIVERY_KEYS if kind == "delivery" else ACTION_KEYS if kind == "action" else CLAIM_KEYS
    if set(item) != set(expected):
        raise PolicyError(f"canonical {kind} keys do not match v0.1")
    state = _state(item.get("state"), f"{kind} state")
    if kind == "delivery":
        summary = _text(item.get("summary"), "delivery summary", visible=True)
        _ = _text(item.get("worker_ref"), "delivery worker_ref")
    elif kind == "action":
        action = _text(item.get("action_name"), "action name", visible=True)
        target = _text(item.get("target"), "action target", visible=True)
        _ = _text(item.get("action_id"), "action id")
        summary = f"{action}: {target}"
    else:
        summary = _text(item.get("claim"), "claim", visible=True)
    return CanonicalEntry(state, summary, _refs(item.get("evidence_refs"), f"{kind} evidence_refs", state))


def _report(root: JsonObject) -> CanonicalReport:
    if set(root) != set(ROOT_KEYS) or root.get("format") != "agent-company.ceo-report/v0.1":
        raise PolicyError("canonical report root does not match v0.1")
    job_id = _text(root.get("job_id"), "job_id", visible=True)
    if JOB_ID.fullmatch(job_id) is None or ".." in job_id:
        raise PolicyError("job_id is unsafe for content-addressed evidence")
    if _text(root.get("job_type"), "job_type") not in JOB_TYPES:
        raise PolicyError("job_type is unsupported")
    _ = _text(root.get("objective"), "objective")
    try:
        overall = OverallState(_text(root.get("overall_status"), "overall_status"))
    except ValueError as exc:
        raise PolicyError("overall_status is unsupported") from exc
    decision = _text(root.get("decision_summary"), "decision_summary", visible=True)
    deliveries = _objects(root.get("role_deliveries"), "role_deliveries", require_one=True)
    roles: list[str] = []
    entries = [_entry(item, "delivery") for item in deliveries]
    for item in deliveries:
        role = _text(item.get("role"), "delivery role")
        if role not in ROLES:
            raise PolicyError("delivery role is unsupported")
        if role in ORDINARY_ROLES and role not in roles:
            roles.append(role)
    entries.extend(_entry(item, "action") for item in _objects(root.get("external_actions"), "external_actions"))
    entries.extend(_entry(item, "claim") for item in _objects(root.get("claims"), "claims"))
    _ = _texts(root.get("user_decisions"), "user_decisions")
    risks = _texts(root.get("risks"), "risks", visible=True)
    entries.extend(CanonicalEntry(EvidenceState.UNVERIFIED, risk, ()) for risk in risks)
    next_actions = _texts(root.get("next_actions"), "next_actions", visible=True)
    if overall is OverallState.VERIFIED and (
        risks or any(entry.state is not EvidenceState.VERIFIED for entry in entries)
    ):
        raise PolicyError("verified overall status contradicts canonical entries")
    return CanonicalReport(job_id, overall, decision, tuple(roles), tuple(entries), next_actions)


def bind_canonical_report(payload: bytes) -> CanonicalBinding:
    """Parse exact report bytes and assign their sole content-addressed ref."""
    try:
        parsed: JsonValue = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PolicyError(f"canonical report bytes are invalid JSON: {exc}") from exc
    report = _report(_object(parsed, "canonical report"))
    digest = hashlib.sha256(payload).hexdigest()
    reference = parse_evidence_ref(
        f"evidence://agent-company/ceo-report/{report.job_id}/{digest}.json",
        "canonical source evidence reference",
    )
    return CanonicalBinding(report, payload, digest, reference)


def validate_canonical_binding(source: CanonicalBinding) -> CanonicalBinding:
    """Reject a constructed or replaced source binding before projection."""
    rebound = bind_canonical_report(source.payload)
    if rebound != source:
        raise PolicyError("canonical binding differs from its report bytes")
    return rebound
