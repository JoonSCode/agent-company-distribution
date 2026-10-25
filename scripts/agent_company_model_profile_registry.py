"""Load the fixed Model Profile Registry and machine-readable policy contract."""

from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportUnnecessaryComparison=false
import hashlib
from pathlib import Path
from types import MappingProxyType
from typing import Final, assert_never

from agent_company_expertise_eval_encoding import parse_json_object
from agent_company_expertise_eval_io import read_bytes, require_inside
from agent_company_expertise_eval_models import ExpertiseEvaluationError
from agent_company_model_routing_models import (
    SUPPORTED_MODELS,
    SUPPORTED_EFFORTS,
    SUPPORTED_SERVICE_TIERS,
    ModelProfile,
    ModelProfileAuthority,
    ModelProfileRegistry,
    ModelRoutingError,
    ModelRoutingPolicy,
    RateCard,
    RoutingPrecedenceRule,
)
from agent_company_role_schema import JsonValue

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
REGISTRY_REF: Final[str] = "policies/model-profile-registry.json"
POLICY_REF: Final[str] = "policies/model-routing-policy.json"
MAX_POLICY_BYTES: Final[int] = 256_000
PROFILE_IDS: Final[frozenset[str]] = frozenset({"mechanical", "standard-implementation", "bounded-deep", "integration", "specialist-reasoning", "role-lead-judgment", "company-judgment"})
REQUIRED_INPUTS: Final[frozenset[str]] = frozenset({"role", "task_type", "ambiguity", "expected_change_scope", "failure_impact", "reversibility", "automated_verifiability", "critical_path", "speed_or_credit_priority", "specialist_tools", "prior_attempts_and_failure_causes", "authority_signals", "dynamic_risk_signals", "capacity_snapshot"})
CAPS: Final[dict[str, int]] = {"mechanical": 8, "standard-implementation": 6, "bounded-deep": 4, "integration": 2, "specialist-reasoning": 2, "role-lead-judgment": 1, "company-judgment": 1}
RANKS: Final[dict[str, int]] = {"mechanical": 1, "standard-implementation": 2, "bounded-deep": 3, "integration": 4, "specialist-reasoning": 5, "role-lead-judgment": 6, "company-judgment": 7}
AUTHORITY: Final[dict[str, tuple[ModelProfileAuthority, bool]]] = {"mechanical": (ModelProfileAuthority.EXECUTOR, True), "standard-implementation": (ModelProfileAuthority.EXECUTOR, True), "bounded-deep": (ModelProfileAuthority.EXECUTOR, True), "integration": (ModelProfileAuthority.EXECUTOR, True), "specialist-reasoning": (ModelProfileAuthority.EXECUTOR, True), "role-lead-judgment": (ModelProfileAuthority.ROLE_LEAD, False), "company-judgment": (ModelProfileAuthority.COMPANY_ROOT, False)}
EXPECTED_RULES: Final[tuple[tuple[int, str, str, str], ...]] = ((1, "company_authority_required", "return_to_company_root", "company-judgment"), (2, "role_lead_judgment_required", "return_to_role_lead", "role-lead-judgment"), (3, "specialist_risk_or_unknown_cause", "select_profile", "specialist-reasoning"), (4, "integration_scope_or_approved_retry", "select_profile", "integration"), (5, "bounded_deep_suitable", "select_profile", "bounded-deep"), (6, "standard_implementation_suitable", "select_profile", "standard-implementation"), (7, "default_mechanical", "select_profile", "mechanical"))

ModelProfileRegistryError = ModelRoutingError


def _text(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ModelProfileRegistryError("model_profile_malformed", f"{label} must be nonempty text")
    return value


def _object(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ModelProfileRegistryError("model_profile_malformed", f"{label} must be an object")
    return value


def _objects(value: JsonValue | None, label: str) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list):
        raise ModelProfileRegistryError("model_profile_malformed", f"{label} must be a list")
    return tuple(_object(item, f"{label}[{index}]") for index, item in enumerate(value))


def _texts(value: JsonValue | None, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ModelProfileRegistryError("model_profile_malformed", f"{label} must be a list")
    result = tuple(_text(item, label) for item in value)
    if not result or len(result) != len(set(result)):
        raise ModelProfileRegistryError("model_profile_malformed", f"{label} must be unique and nonempty")
    return result


def _read(root: Path, reference: str) -> tuple[dict[str, JsonValue], bytes, Path]:
    try:
        path = require_inside(root, root / reference)
        content = read_bytes(path, MAX_POLICY_BYTES)
    except ExpertiseEvaluationError as exc:
        raise ModelProfileRegistryError("model_profile_unsafe", reference) from exc
    try:
        return parse_json_object(content, str(path)), content, path
    except ExpertiseEvaluationError as exc:
        raise ModelProfileRegistryError("model_profile_malformed", reference) from exc


def _profile(raw: dict[str, JsonValue]) -> ModelProfile:
    fields = {"semantic_profile", "model_id", "reasoning_effort", "authority", "dispatchable", "administrative_status", "runtime_availability_required", "service_tier_default", "speed_trait", "credit_trait", "allowed_task_types", "capability_rank", "capability_floor", "fallback_profile", "concurrency_cap", "rate_card_model_id"}
    if set(raw) != fields:
        raise ModelProfileRegistryError("model_profile_malformed", "profile shape is invalid")
    rank, floor, cap = raw.get("capability_rank"), raw.get("capability_floor"), raw.get("concurrency_cap")
    fallback, dispatchable, runtime_required = raw.get("fallback_profile"), raw.get("dispatchable"), raw.get("runtime_availability_required")
    if not isinstance(rank, int) or not isinstance(floor, int) or not isinstance(cap, int) or isinstance(rank, bool) or isinstance(floor, bool) or isinstance(cap, bool) or rank < 1 or rank > 7 or floor < 1 or floor > 7 or floor > rank or cap < 1 or not isinstance(fallback, str | None) or not isinstance(dispatchable, bool) or runtime_required is not True:
        raise ModelProfileRegistryError("model_profile_malformed", "profile scalar fields are invalid")
    model, effort, status, tier, speed, credit = _text(raw.get("model_id"), "model_id"), _text(raw.get("reasoning_effort"), "reasoning_effort"), _text(raw.get("administrative_status"), "administrative_status"), _text(raw.get("service_tier_default"), "service_tier_default"), _text(raw.get("speed_trait"), "speed_trait"), _text(raw.get("credit_trait"), "credit_trait")
    if model not in SUPPORTED_MODELS or effort not in SUPPORTED_EFFORTS or status not in {"enabled", "disabled"} or tier not in SUPPORTED_SERVICE_TIERS or speed not in {"fast", "balanced", "deep"} or credit not in {"lowest", "moderate", "highest"}:
        raise ModelProfileRegistryError("model_profile_malformed", "profile enum values are invalid")
    try:
        authority = ModelProfileAuthority(_text(raw.get("authority"), "authority"))
    except ValueError as exc:
        raise ModelProfileRegistryError("model_profile_malformed", "authority is invalid") from exc
    return ModelProfile(_text(raw.get("semantic_profile"), "semantic_profile"), model, effort, authority, dispatchable, status, True, tier, speed, credit, _texts(raw.get("allowed_task_types"), "allowed_task_types"), rank, floor, fallback, cap, _text(raw.get("rate_card_model_id"), "rate_card_model_id"))


def _validate_profiles(profiles: dict[str, ModelProfile], rate_card: RateCard) -> None:
    if frozenset(profiles) != PROFILE_IDS:
        raise ModelProfileRegistryError("model_profile_malformed", "exactly seven semantic profiles are required")
    for profile in profiles.values():
        expected_authority, expected_dispatchable = AUTHORITY[profile.semantic_profile]
        if profile.authority != expected_authority or profile.dispatchable != expected_dispatchable or profile.concurrency_cap > CAPS[profile.semantic_profile] or profile.capability_rank != RANKS[profile.semantic_profile] or profile.capability_floor != RANKS[profile.semantic_profile] or profile.model_id != profile.rate_card_model_id or profile.model_id not in rate_card.rates:
            raise ModelProfileRegistryError("model_profile_authority", profile.semantic_profile)
        match profile.authority:
            case ModelProfileAuthority.EXECUTOR:
                pass
            case ModelProfileAuthority.ROLE_LEAD | ModelProfileAuthority.COMPANY_ROOT:
                if profile.fallback_profile is not None:
                    raise ModelProfileRegistryError("model_profile_fallback", profile.semantic_profile)
            case unreachable:
                assert_never(unreachable)
    for profile in profiles.values():
        fallback_id = profile.fallback_profile
        if fallback_id is None:
            continue
        fallback = profiles.get(fallback_id)
        if fallback is None or profile.authority != ModelProfileAuthority.EXECUTOR or fallback.authority != ModelProfileAuthority.EXECUTOR or fallback.capability_rank <= profile.capability_rank or fallback.capability_rank < profile.capability_floor:
            raise ModelProfileRegistryError("model_profile_fallback", profile.semantic_profile)
        visited: set[str] = {profile.semantic_profile}
        current = fallback
        while current.fallback_profile is not None:
            if current.semantic_profile in visited:
                raise ModelProfileRegistryError("model_profile_fallback", "fallback cycle")
            visited.add(current.semantic_profile)
            next_profile = profiles.get(current.fallback_profile)
            if next_profile is None:
                raise ModelProfileRegistryError("model_profile_fallback", "missing fallback")
            current = next_profile


def load_model_profile_registry(root: Path = ROOT, rate_card: RateCard | None = None) -> ModelProfileRegistry:
    """Parse seven semantic profiles bound to a stable rate-card ref and surface."""
    if type(rate_card) is not RateCard:
        raise ModelProfileRegistryError("rate_card_required", "rate card must be loaded first")
    if type(root) is not type(ROOT):
        raise ModelProfileRegistryError("model_profile_unsafe", REGISTRY_REF)
    payload, content, path = _read(root, REGISTRY_REF)
    if set(payload) != {"format", "rate_card_binding", "profiles"} or payload.get("format") != "agent-company.model-profile-registry/v0.1":
        raise ModelProfileRegistryError("model_profile_malformed", "unsupported registry header")
    binding = _object(payload.get("rate_card_binding"), "rate_card_binding")
    if set(binding) != {"ref", "surface"} or binding.get("ref") != rate_card.reference or binding.get("surface") != rate_card.surface:
        raise ModelProfileRegistryError("rate_card_binding", "registry does not bind supplied rate-card ref and surface")
    profiles: dict[str, ModelProfile] = {}
    for raw in _objects(payload.get("profiles"), "profiles"):
        profile = _profile(raw)
        if profile.semantic_profile in profiles:
            raise ModelProfileRegistryError("model_profile_malformed", "duplicate semantic profile")
        profiles[profile.semantic_profile] = profile
    _validate_profiles(profiles, rate_card)
    return ModelProfileRegistry(path, hashlib.sha256(content).hexdigest(), rate_card.sha256, rate_card.cost_sensitive_enabled, MappingProxyType(profiles))


def load_model_routing_policy(root: Path = ROOT) -> ModelRoutingPolicy:
    """Parse the selector input table only; predicate evaluation stays in S2."""
    if type(root) is not type(ROOT):
        raise ModelProfileRegistryError("model_profile_unsafe", POLICY_REF)
    payload, content, path = _read(root, POLICY_REF)
    if set(payload) != {"format", "required_inputs", "precedence"} or payload.get("format") != "agent-company.model-routing-policy/v0.1":
        raise ModelProfileRegistryError("model_routing_policy_malformed", "unsupported policy header")
    inputs = _texts(payload.get("required_inputs"), "required_inputs")
    if frozenset(inputs) != REQUIRED_INPUTS:
        raise ModelProfileRegistryError("model_routing_policy_malformed", "required inputs are incomplete")
    rules: list[RoutingPrecedenceRule] = []
    for raw in _objects(payload.get("precedence"), "precedence"):
        if set(raw) != {"priority", "predicate_id", "disposition", "profile", "trigger_summary"}:
            raise ModelProfileRegistryError("model_routing_policy_malformed", "rule shape is invalid")
        priority = raw.get("priority")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ModelProfileRegistryError("model_routing_policy_malformed", "priority is invalid")
        rules.append(RoutingPrecedenceRule(priority, _text(raw.get("predicate_id"), "predicate_id"), _text(raw.get("disposition"), "disposition"), _text(raw.get("profile"), "profile"), _text(raw.get("trigger_summary"), "trigger_summary")))
    if tuple((item.priority, item.predicate_id, item.disposition, item.profile) for item in rules) != EXPECTED_RULES:
        raise ModelProfileRegistryError("model_routing_policy_malformed", "precedence is not deterministic")
    return ModelRoutingPolicy(path, hashlib.sha256(content).hexdigest(), inputs, tuple(rules))
