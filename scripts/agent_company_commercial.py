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
    AppRequest,
    CycleError,
    JsonObject,
    Mutation,
    ObservationRequest,
    canonical_time,
    json_array,
    required_text,
    unique_texts,
)
from agent_company_deps import JsonValue


METRIC_IDS: Final[tuple[str, ...]] = (
    "gross_revenue", "net_revenue", "subscription_revenue", "iap_revenue",
    "ad_revenue", "refunds", "marketing_spend", "infrastructure_cost",
    "installs", "active_users", "paying_users", "new_paying_users",
)
LIFECYCLES: Final[frozenset[str]] = frozenset({
    "discovery", "build", "released", "growth", "maintenance", "paused", "retired",
})
CURRENCY: Final[re.Pattern[str]] = re.compile(r"[A-Z]{3}")


def _object(value: JsonValue, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise CycleError("malformed_state", f"{label} must be an object")
    return value


def _objects(value: JsonValue, label: str) -> list[JsonObject]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise CycleError("malformed_state", f"{label} must be an object list")
    return [item for item in value if isinstance(item, dict)]


def empty_metrics() -> JsonObject:
    return {metric_id: None for metric_id in METRIC_IDS}


def empty_derived() -> JsonObject:
    return {
        "arppu": None,
        "cac": None,
        "contribution_margin": None,
        "payback_months": None,
    }


def register_app(state: JsonObject, request: AppRequest) -> Mutation:
    app_id = required_text(request.app_id, "app_id")
    if request.kind not in {"existing-app", "new-opportunity"}:
        raise CycleError("malformed_input", "app kind is unsupported")
    if request.lifecycle not in LIFECYCLES:
        raise CycleError("malformed_input", "app lifecycle is unsupported")
    repository_ref = (
        required_text(request.repository_ref, "repository_ref")
        if request.repository_ref is not None else None
    )
    next_state = copy.deepcopy(state)
    portfolio = _object(next_state.get("portfolio"), "portfolio")
    apps = _objects(portfolio.get("apps"), "apps")
    if any(item.get("app_id") == app_id for item in apps):
        raise CycleError("duplicate_app", f"app already exists: {app_id}")
    apps.append({
        "app_id": app_id,
        "name": required_text(request.name, "name"),
        "kind": request.kind,
        "lifecycle": request.lifecycle,
        "repository_ref": repository_ref,
        "commercial_state": {
            "evidence_status": "unknown",
            "period_start": None,
            "period_end": None,
            "currency": "KRW",
            "metrics": empty_metrics(),
            "derived": empty_derived(),
        },
    })
    portfolio["apps"] = json_array(apps)
    return Mutation(next_state, {"status": "registered", "app_id": app_id})


def _source(request: ObservationRequest) -> str:
    source_path = Path(required_text(request.source_ref, "source_ref")).expanduser()
    resolved = source_path.resolve()
    if source_path.is_symlink() or request.source_ref != str(resolved):
        raise CycleError("unsafe_commercial_evidence", "source_ref must be a canonical local path")
    try:
        actual_sha256 = hashlib.sha256(resolved.read_bytes()).hexdigest()
    except OSError as exc:
        raise CycleError("commercial_evidence_unavailable", f"cannot read source evidence: {exc}") from exc
    if actual_sha256 != request.source_sha256:
        raise CycleError("stale_commercial_evidence", "source evidence bytes differ from the expected hash")
    return str(resolved)


def _metric_map(request: ObservationRequest) -> JsonObject:
    names = [name for name, _ in request.metrics]
    if len(names) != len(set(names)) or not set(names).issubset(METRIC_IDS):
        raise CycleError("malformed_input", "commercial metrics are duplicated or unsupported")
    if request.evidence_status == "observed" and not names:
        raise CycleError("malformed_input", "observed commercial evidence requires metrics")
    metrics = empty_metrics()
    for name, value in request.metrics:
        metrics[name] = value
    return metrics


def _number(metrics: JsonObject, field: str) -> float | None:
    value = metrics.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CycleError("malformed_input", f"metric {field} must be numeric")
    return float(value)


def _derive(request: ObservationRequest, metrics: JsonObject) -> JsonObject:
    derived = empty_derived()
    if (
        request.evidence_status != "observed"
        or request.freshness != "fresh"
        or request.confidence <= 0
    ):
        return derived
    net = _number(metrics, "net_revenue")
    spend = _number(metrics, "marketing_spend")
    infrastructure = _number(metrics, "infrastructure_cost")
    paying = _number(metrics, "paying_users")
    new_paying = _number(metrics, "new_paying_users")
    if net is not None and spend is not None and infrastructure is not None:
        derived["contribution_margin"] = net - spend - infrastructure
    if net is not None and paying is not None and paying > 0:
        derived["arppu"] = net / paying
    if request.attribution == "attributed" and spend is not None and new_paying is not None and new_paying > 0:
        derived["cac"] = spend / new_paying
    cac, arppu = derived["cac"], derived["arppu"]
    if isinstance(cac, (int, float)) and isinstance(arppu, (int, float)) and arppu > 0:
        derived["payback_months"] = cac / arppu
    return derived


def record_observation(state: JsonObject, request: ObservationRequest) -> Mutation:
    if request.evidence_status not in {"pending", "observed"}:
        raise CycleError("malformed_input", "commercial evidence status is unsupported")
    if request.attribution not in {"unknown", "unattributed", "attributed"}:
        raise CycleError("malformed_input", "commercial attribution is unsupported")
    if request.freshness not in {"fresh", "stale", "unknown"}:
        raise CycleError("malformed_input", "commercial freshness is unsupported")
    if CURRENCY.fullmatch(request.currency) is None:
        raise CycleError("malformed_input", "currency must be a three-letter uppercase code")
    if request.confidence < 0 or request.confidence > 1:
        raise CycleError("malformed_input", "confidence must be between zero and one")
    source_ref = _source(request)
    metrics = _metric_map(request)
    derived = _derive(request, metrics)
    captured_at = canonical_time(request.captured_at, "captured_at")
    limitations = json_array(unique_texts(request.limitations, "limitations"))
    next_state = copy.deepcopy(state)
    portfolio = _object(next_state.get("portfolio"), "portfolio")
    apps = _objects(portfolio.get("apps"), "apps")
    matches = [item for item in apps if item.get("app_id") == request.app_id]
    if len(matches) != 1:
        raise CycleError("unknown_app", "commercial observation app is missing or duplicated")
    observations = _objects(next_state.get("observations"), "observations")
    if any(item.get("observation_id") == request.observation_id for item in observations):
        raise CycleError("duplicate_observation", "commercial observation already exists")
    observations.append({
        "observation_id": required_text(request.observation_id, "observation_id"),
        "app_id": request.app_id,
        "captured_at": captured_at,
        "source_ref": source_ref,
        "source_sha256": request.source_sha256,
        "evidence_status": request.evidence_status,
        "currency": request.currency,
        "attribution": request.attribution,
        "confidence": request.confidence,
        "freshness": request.freshness,
        "limitations": limitations,
        "metrics": metrics,
    })
    next_state["observations"] = json_array(observations)
    matches[0]["commercial_state"] = {
        "evidence_status": request.evidence_status,
        "period_start": captured_at,
        "period_end": captured_at,
        "currency": request.currency,
        "metrics": metrics,
        "derived": derived,
    }
    return Mutation(next_state, {
        "status": "observed", "app_id": request.app_id,
        "observation_id": request.observation_id, "derived": derived,
    })
