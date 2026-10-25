#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Import from agent_company_job_policy.py.
# 2. Verify with: python3 scripts/test_agent_company_policy_suite.py
# ──────────────────

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Final

from agent_company_deps import JsonValue
from agent_company_projection_policy import PolicyError, object_list, string_list, text
from agent_company_route_contract import RoutingError, load_json


ROOT: Final[Path] = Path(__file__).resolve().parents[1]
JOB_TYPES: Final[tuple[str, ...]] = (
    "new-app", "improvement", "planning", "promotion", "release", "incident", "portfolio",
)
ROLES: Final[set[str]] = {"founder", "planning", "design", "development", "marketing", "qa-release"}
COMPANY_CONTEXT_KEYS: Final[frozenset[str]] = frozenset({
    "charter_ref", "charter_sha256", "initiative_origin", "initiative_id",
    "target_kind", "target_ref", "commercial_hypothesis", "success_metrics",
    "failure_metrics", "guardrails", "commercial_evidence_state", "external_action_authority",
    "execution_owner", "final_verification_owner",
})


@dataclass(frozen=True, slots=True)
class JobRequest:
    job_id: str
    job_type: str
    objective: str
    source_request: str
    activated_roles: tuple[str, ...]
    ambiguities: tuple[tuple[str, str], ...]
    company_plan_topology: bool = False
    initiative_origin: str = "ceo-directed"
    initiative_id: str | None = None
    target_kind: str = "portfolio"
    target_ref: str = "company://portfolio"
    commercial_hypothesis: str = "Commercial hypothesis is unknown until evidence is gathered"
    success_metrics: tuple[str, ...] = ("commercial evidence is gathered or explicitly remains unknown",)
    failure_metrics: tuple[str, ...] = ("guardrail breach or negative commercial evidence is recorded",)
    guardrails: tuple[str, ...] = (
        "external mutation, publication, and spend require explicit CEO approval",
        "independent matching-surface verification is required",
    )


def read_object(path: Path) -> dict[str, JsonValue]:
    try:
        value = load_json(path)
    except RoutingError as exc:
        raise PolicyError(f"cannot read policy object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PolicyError(f"policy root must be an object: {path}")
    return value


def write_text(path: Path, value: str) -> None:
    temporary: Path | None = None
    try:
        _ = path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            "w", encoding="utf-8", newline="", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            _ = stream.write(value)
        _ = temporary.replace(path)
    except OSError as exc:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
        raise PolicyError(f"cannot write output {path}: {exc}") from exc


def write_object(path: Path, value: dict[str, JsonValue]) -> None:
    write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def classify(request: str) -> str:
    lowered = request.lower()
    rules = (
        ("incident", ("장애", "incident", "outage", "복구", "crash")),
        ("portfolio", ("포트폴리오", "portfolio", "우선순위", "portfolio bet")),
        ("promotion", ("홍보", "마케팅", "marketing", "promotion", "인플루언서", "광고")),
        ("new-app", ("새 앱", "신규 앱", "new app", "앱을 만들", "app을 만들")),
        ("planning", ("기획", "계획", "plan", "전략 정리")),
        ("release", ("testflight", "릴리스", "release", "앱스토어 제출", "배포 준비")),
        ("improvement", ("개선", "improve", "최적화", "고쳐", "수정")),
    )
    for job_type, tokens in rules:
        if any(token in lowered for token in tokens):
            return job_type
    return "improvement"


def catalog_job(job_type: str) -> dict[str, JsonValue]:
    catalog = read_object(ROOT / "policies" / "job-catalog.json")
    for item in object_list(catalog.get("jobs"), "jobs"):
        if item.get("id") == job_type:
            return item
    raise PolicyError(f"unsupported job type: {job_type}")


def recipe(job_type: str) -> dict[str, JsonValue]:
    recipes = read_object(ROOT / "policies" / "squad-recipes.json")
    for item in object_list(recipes.get("recipes"), "recipes"):
        if item.get("job_type") == job_type:
            return item
    raise PolicyError(f"missing squad recipe: {job_type}")


def _non_empty(value: str, label: str) -> str:
    if not value.strip():
        raise PolicyError(f"{label} must be non-empty text")
    return value


def _boolean(value: JsonValue, label: str) -> bool:
    if not isinstance(value, bool):
        raise PolicyError(f"{label} must be boolean")
    return value


def _json_array(values: Iterable[JsonValue]) -> list[JsonValue]:
    return list(values)


def _metric_list(values: tuple[str, ...], label: str) -> list[JsonValue]:
    if not values or len(values) != len(set(values)):
        raise PolicyError(f"{label} must contain unique non-empty metrics")
    return [_non_empty(value, label) for value in values]


def _company_context(request: JobRequest, job_id: str) -> dict[str, JsonValue]:
    if request.initiative_origin not in {"ceo-directed", "company-initiated"}:
        raise PolicyError("initiative_origin must be ceo-directed or company-initiated")
    if request.target_kind not in {"existing-app", "new-app", "portfolio"}:
        raise PolicyError("target_kind must be existing-app, new-app, or portfolio")
    charter_path = ROOT / "policies" / "company-charter.json"
    try:
        charter_sha256 = hashlib.sha256(charter_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise PolicyError(f"cannot read company charter {charter_path}: {exc}") from exc
    return {
        "charter_ref": "policies/company-charter.json",
        "charter_sha256": charter_sha256,
        "initiative_origin": request.initiative_origin,
        "initiative_id": _non_empty(request.initiative_id or job_id, "initiative_id"),
        "target_kind": request.target_kind,
        "target_ref": _non_empty(request.target_ref, "target_ref"),
        "commercial_hypothesis": _non_empty(
            request.commercial_hypothesis, "commercial_hypothesis",
        ),
        "success_metrics": _metric_list(request.success_metrics, "success_metrics"),
        "failure_metrics": _metric_list(request.failure_metrics, "failure_metrics"),
        "guardrails": _metric_list(request.guardrails, "guardrails"),
        "commercial_evidence_state": "unknown",
        "external_action_authority": "explicit-ceo-approval",
        "execution_owner": "orca",
        "final_verification_owner": "qa-release",
    }


def validate_company_context(job: dict[str, JsonValue], *, historical_read: bool = False) -> None:
    value = job.get("company_context")
    if value is None:
        return
    if not isinstance(value, dict) or frozenset(value) != COMPANY_CONTEXT_KEYS:
        raise PolicyError("company_context fields are invalid")
    charter_ref = text(value.get("charter_ref"), "charter_ref")
    if charter_ref != "policies/company-charter.json":
        raise PolicyError("company_context charter_ref is invalid")
    charter_path = ROOT / charter_ref
    try:
        charter_sha256 = hashlib.sha256(charter_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise PolicyError(f"cannot read company charter {charter_path}: {exc}") from exc
    if value.get("charter_sha256") != charter_sha256:
        raise PolicyError("company_context charter bytes changed")
    if value.get("initiative_origin") not in {"ceo-directed", "company-initiated"}:
        raise PolicyError("company_context initiative_origin is invalid")
    if value.get("target_kind") not in {"existing-app", "new-app", "portfolio"}:
        raise PolicyError("company_context target_kind is invalid")
    for field in ("initiative_id", "target_ref", "commercial_hypothesis"):
        _ = text(value.get(field), field)
    for field in ("success_metrics", "failure_metrics", "guardrails"):
        metrics = string_list(value.get(field), field)
        if not metrics or len(metrics) != len(set(metrics)):
            raise PolicyError(f"company_context {field} must contain unique metrics")
    expected = {
        "commercial_evidence_state": "unknown",
        "external_action_authority": "explicit-ceo-approval",
    }
    if any(value.get(field) != expected_value for field, expected_value in expected.items()):
        raise PolicyError("company_context authority or evidence state is invalid")
    owners = (value.get("execution_owner"), value.get("final_verification_owner"))
    if owners != ("orca", "qa-release") and not (
        historical_read and owners == ("king-sejong-core", "seungjeongwon")
    ):
        raise PolicyError("company_context owners are invalid")


def build_job(request: JobRequest) -> dict[str, JsonValue]:
    job_id = _non_empty(request.job_id, "job_id")
    job_type = request.job_type
    objective = _non_empty(request.objective, "objective")
    source_request = _non_empty(request.source_request, "source_request")
    activated_roles = request.activated_roles
    ambiguities = request.ambiguities
    if len(activated_roles) != len(set(activated_roles)):
        raise PolicyError("activated roles must be unique")
    catalog = catalog_job(job_type)
    selected_recipe = recipe(job_type)
    required = string_list(selected_recipe.get("required_roles"), "required_roles")
    conditional = {
        text(item.get("role"), "conditional role")
        for item in object_list(selected_recipe.get("conditional_roles"), "conditional_roles")
    }
    topology = _boolean(request.company_plan_topology, "company_plan_topology")
    if topology and (job_type not in {"improvement", "promotion", "portfolio"} or "planning" not in conditional):
        raise PolicyError("company-plan topology is unsupported for this job type")
    if "planning" in activated_roles and not topology:
        raise PolicyError("Planning requires explicit company-plan topology")
    effective = (*activated_roles, "planning") if topology and "planning" not in activated_roles else activated_roles
    invalid = sorted(set(effective) - conditional)
    if invalid:
        raise PolicyError(f"roles are not conditional for {job_type}: {invalid}")
    additional = [role for role in effective if role not in required and (role != "planning" or not topology)]
    selected = [*(["planning"] if topology else []), *required, *additional]
    if not set(selected).issubset(ROLES):
        raise PolicyError("selected roles contain an unsupported role")
    workflow_ref = text(catalog.get("workflow_ref"), "workflow_ref")
    recipe_id = text(catalog.get("minimum_squad_recipe_id"), "minimum_squad_recipe_id")
    budget = catalog.get("default_budget")
    if not isinstance(budget, dict):
        raise PolicyError("default_budget must be an object")
    ambiguity_items: list[JsonValue] = [
        {"question": question, "decision_impact": impact} for question, impact in ambiguities
    ]
    company_context = _company_context(request, job_id)
    return {
        "format": "agent-company.job/v0.1", "job_id": job_id, "job_type": job_type,
        "objective": objective, "source_request": source_request,
        "selected_recipe_id": recipe_id, "selected_roles": _json_array(selected),
        "workflow_ref": workflow_ref,
        "policy_refs": _json_array(("policies/company-charter.json", "policies/company-state.schema.json", "policies/job-catalog.json", "policies/squad-recipes.json", workflow_ref, "policies/specialist-request.schema.json", "policies/uigwe-decision.schema.json", "policies/external-action-policy.json", "policies/ceo-report.schema.json")),
        "company_context": company_context,
        "default_budget": budget,
        "kickoff": {
            "status": "recorded", "participants": _json_array(("ceo", "company-lead", *selected)),
            "agenda": _json_array((objective, "confirm intake classification, squad, budget, workflow, and open decisions")),
            "intake_decision": {
                "job_type": job_type, "material_ambiguity_count": len(ambiguities),
                "company_plan_topology": topology,
            },
            "selected_squad": {"recipe_id": recipe_id, "roles": _json_array(selected)},
            "budget": budget, "workflow_ref": workflow_ref,
        },
        "material_ambiguities": ambiguity_items,
        "uigwe_gate": {"required": bool(ambiguities), "status": "pending-user" if ambiguities else "not-needed"},
        "core_execution_refs": _json_array(()),
    }
