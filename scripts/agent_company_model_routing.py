"""Pure, fail-closed Model Profile Registry routing."""

from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportUnnecessaryIsInstance=false
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from agent_company_model_routing_models import (
    SUPPORTED_MODELS,
    SUPPORTED_EFFORTS,
    SUPPORTED_SERVICE_TIERS,
    ModelProfile,
    ModelProfileAuthority,
    ModelProfileRegistry,
    ModelRoutingPolicy,
    RoutingPrecedenceRule,
)

REQUEST_FORMAT: Final[str] = "agent-company.model-routing-request/v0.2"
CAPACITY_FORMAT: Final[str] = "agent-company.model-routing-capacity/v0.2"
DECISION_FORMAT: Final[str] = "agent-company.model-routing-decision/v0.2"
CANONICAL_ALGORITHM: Final[str] = "sha256-canonical-json/v1"
PROFILES: Final[frozenset[str]] = frozenset({"mechanical", "standard-implementation", "bounded-deep", "integration", "specialist-reasoning", "role-lead-judgment", "company-judgment"})
EXECUTORS: Final[frozenset[str]] = frozenset({"mechanical", "standard-implementation", "bounded-deep", "integration", "specialist-reasoning"})
ROLES: Final[frozenset[str]] = frozenset({"founder", "planning", "marketing", "design", "development", "qa-release"})
RISKS: Final[frozenset[str]] = frozenset({"security", "data-loss", "data-integrity", "migration", "lineage", "rollback", "concurrency", "performance"})
ADAPTERS: Final[frozenset[str]] = frozenset({"codex-native-worker", "host-model-override", "none"})
RANKS: Final[dict[str, int]] = {"mechanical": 1, "standard-implementation": 2, "bounded-deep": 3, "integration": 4, "specialist-reasoning": 5, "role-lead-judgment": 6, "company-judgment": 7}
CAPS: Final[dict[str, int]] = {"mechanical": 8, "standard-implementation": 6, "bounded-deep": 4, "integration": 2, "specialist-reasoning": 2, "role-lead-judgment": 1, "company-judgment": 1}
REQUIRED: Final[frozenset[str]] = frozenset({"role", "task_type", "ambiguity", "expected_change_scope", "failure_impact", "reversibility", "automated_verifiability", "critical_path", "speed_or_credit_priority", "specialist_tools", "prior_attempts_and_failure_causes", "authority_signals", "dynamic_risk_signals", "capacity_snapshot"})
RULES: Final[tuple[tuple[int, str, str, str], ...]] = ((1, "company_authority_required", "return_to_company_root", "company-judgment"), (2, "role_lead_judgment_required", "return_to_role_lead", "role-lead-judgment"), (3, "specialist_risk_or_unknown_cause", "select_profile", "specialist-reasoning"), (4, "integration_scope_or_approved_retry", "select_profile", "integration"), (5, "bounded_deep_suitable", "select_profile", "bounded-deep"), (6, "standard_implementation_suitable", "select_profile", "standard-implementation"), (7, "default_mechanical", "select_profile", "mechanical"))
SLUG: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z0-9-]*\Z")
REF: Final[re.Pattern[str]] = re.compile(r"[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*\Z")


class RoutingDisposition(StrEnum):
    DISPATCH = "dispatch"
    RETURN_TO_ROLE_LEAD = "return_to_role_lead"
    RETURN_TO_COMPANY_ROOT = "return_to_company_root"
    BLOCKED = "blocked"


class FallbackCause(StrEnum):
    SELECTED = "selected"
    ADMINISTRATIVELY_DISABLED = "administratively_disabled"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"
    PROFILE_SATURATED = "profile_saturated"
    TOOL_UNSUPPORTED = "tool_unsupported"
    RUNTIME_MISMATCH = "runtime_mismatch"


@dataclass(frozen=True, slots=True)
class AuthoritySignals:
    cross_role_conflict: bool = False; goal_change: bool = False; irreversible_decision: bool = False; final_promotion: bool = False; rollback_decision: bool = False


@dataclass(frozen=True, slots=True)
class DynamicRiskSignals:
    initial_unknown_cause: bool = False; unexpected_emergence: bool = False; acceptance_conflict: bool = False; tests_passed_intent_unclear: bool = False; risks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PriorAttempt:
    failure_cause: str; execution_failed: bool; role_lead_approved_retry: bool


@dataclass(frozen=True, slots=True)
class ModelRoutingRequest:
    role: str; task_type: str; ambiguity: str; expected_change_scope: str; failure_impact: str; reversibility: str; automated_verifiability: str; critical_path: bool; speed_or_credit_priority: str; specialist_tools: tuple[str, ...]; prior_attempts: tuple[PriorAttempt, ...]; authority_signals: AuthoritySignals; dynamic_risk_signals: DynamicRiskSignals; clear_patterned_multi_file: bool; difficult_or_long: bool; parallelizable: bool


@dataclass(frozen=True, slots=True)
class RuntimeProfileCapacity:
    semantic_profile: str; model_id: str; reasoning_effort: str; adapter: str; available: bool; active_count: int; observed_cap: int; supported_tools: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProfileCapacity:
    profiles: Mapping[str, RuntimeProfileCapacity]; total_active: int; effective_total_cap: int; hard_total_cap: int; observed_at: str; evaluated_at: str; expires_at: str; operating_mode: str; operating_reason: str; evidence_ref: str; evidence_sha256: str


@dataclass(frozen=True, slots=True)
class FallbackAttempt:
    semantic_profile: str; cause: FallbackCause


@dataclass(frozen=True, slots=True)
class ModelRoutingDecision:
    format: str; canonical_algorithm: str; disposition: RoutingDisposition; requested_profile: str | None; selected_profile: str | None; effective_model_id: str | None; effective_reasoning_effort: str | None; effective_adapter: str | None; predicate_id: str; selection_reason: str; fallback_attempts: tuple[FallbackAttempt, ...]; request_format: str; capacity_format: str; request_digest: str; registry_digest: str; registry_projection_digest: str; policy_digest: str; policy_projection_digest: str; rate_card_digest: str; capacity_digest: str; validation_errors: tuple[str, ...]; decision_id: str


@dataclass(frozen=True, slots=True)
class NormalizedRoutingInput:
    request: ModelRoutingRequest | None; registry: ModelProfileRegistry | None; policy: ModelRoutingPolicy | None; capacity: ProfileCapacity | None; request_digest: str; registry_digest: str; registry_projection_digest: str; policy_digest: str; policy_projection_digest: str; rate_card_digest: str; capacity_digest: str; errors: tuple[str, ...]


def _canonical(value: Mapping[str, str | int | bool | None | tuple[str, ...] | tuple[Mapping[str, str], ...]]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _digest(value: Mapping[str, str | int | bool | None | tuple[str, ...] | tuple[Mapping[str, str], ...]]) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _slug(value: str) -> bool: return bool(SLUG.fullmatch(value))


def _sha(value: str) -> bool: return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _ref(value: str) -> bool: return type(value) is str and len(value) <= 256 and REF.fullmatch(value) is not None


def _time(value: str) -> datetime | None:
    if type(value) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value) is None: return None
    try: parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError: return None
    return parsed if parsed.tzinfo is not None else None


def _request_data(request: ModelRoutingRequest) -> dict[str, str | bool | tuple[str, ...] | tuple[Mapping[str, str], ...]]:
    attempts = tuple({"cause": item.failure_cause, "failed": str(item.execution_failed), "approved": str(item.role_lead_approved_retry)} for item in request.prior_attempts)
    return {"format": REQUEST_FORMAT, "role": request.role, "task_type": request.task_type, "ambiguity": request.ambiguity, "scope": request.expected_change_scope, "impact": request.failure_impact, "reversibility": request.reversibility, "verification": request.automated_verifiability, "critical_path": request.critical_path, "priority": request.speed_or_credit_priority, "tools": request.specialist_tools, "attempts": attempts, "authority": tuple(str(item) for item in (request.authority_signals.cross_role_conflict, request.authority_signals.goal_change, request.authority_signals.irreversible_decision, request.authority_signals.final_promotion, request.authority_signals.rollback_decision)), "risks": request.dynamic_risk_signals.risks, "flags": tuple(str(item) for item in (request.dynamic_risk_signals.initial_unknown_cause, request.dynamic_risk_signals.unexpected_emergence, request.dynamic_risk_signals.acceptance_conflict, request.dynamic_risk_signals.tests_passed_intent_unclear, request.clear_patterned_multi_file, request.difficult_or_long, request.parallelizable))}


def _capacity_data(capacity: ProfileCapacity) -> dict[str, str | int | tuple[Mapping[str, str], ...]]:
    rows = tuple({"key": key, "profile": row.semantic_profile, "model": row.model_id, "effort": row.reasoning_effort, "adapter": row.adapter, "available": str(row.available), "active": str(row.active_count), "observed_cap": str(row.observed_cap), "tools": str(row.supported_tools)} for key, row in sorted(capacity.profiles.items()))
    return {"format": CAPACITY_FORMAT, "profiles": rows, "total_active": capacity.total_active, "effective_total_cap": capacity.effective_total_cap, "hard_total_cap": capacity.hard_total_cap, "observed_at": capacity.observed_at, "evaluated_at": capacity.evaluated_at, "expires_at": capacity.expires_at, "mode": capacity.operating_mode, "reason": capacity.operating_reason, "evidence_ref": capacity.evidence_ref, "evidence_sha256": capacity.evidence_sha256}


def _request_valid(request: ModelRoutingRequest) -> bool:
    if type(request.authority_signals) is not AuthoritySignals or type(request.dynamic_risk_signals) is not DynamicRiskSignals: return False
    strings = (request.role, request.task_type, request.ambiguity, request.expected_change_scope, request.failure_impact, request.reversibility, request.automated_verifiability, request.speed_or_credit_priority)
    booleans = (request.critical_path, request.clear_patterned_multi_file, request.difficult_or_long, request.parallelizable, request.authority_signals.cross_role_conflict, request.authority_signals.goal_change, request.authority_signals.irreversible_decision, request.authority_signals.final_promotion, request.authority_signals.rollback_decision, request.dynamic_risk_signals.initial_unknown_cause, request.dynamic_risk_signals.unexpected_emergence, request.dynamic_risk_signals.acceptance_conflict, request.dynamic_risk_signals.tests_passed_intent_unclear)
    attempts, tools, risks = request.prior_attempts, request.specialist_tools, request.dynamic_risk_signals.risks
    if not all(type(item) is str for item in strings) or not all(type(item) is bool for item in booleans) or type(tools) is not tuple or type(risks) is not tuple or type(attempts) is not tuple: return False
    if any(type(item) is not str for item in (*tools, *risks)) or any(type(item) is not PriorAttempt for item in attempts): return False
    if any(type(item.failure_cause) is not str or type(item.execution_failed) is not bool or type(item.role_lead_approved_retry) is not bool for item in attempts): return False
    return request.role in ROLES and _slug(request.task_type) and request.ambiguity in {"low", "medium", "high"} and request.expected_change_scope in {"single-site", "multi-file", "multi-module", "long-context"} and request.failure_impact in {"low", "medium", "high", "critical"} and request.reversibility in {"reversible", "partially-reversible", "irreversible"} and request.automated_verifiability in {"none", "partial", "strong"} and request.speed_or_credit_priority in {"speed", "balanced", "credit"} and all(_slug(item) for item in (*tools, *risks)) and len(tools) == len(set(tools)) and len(risks) == len(set(risks)) and set(risks).issubset(RISKS) and all(_slug(item.failure_cause) and (not item.role_lead_approved_retry or item.execution_failed) for item in attempts) and not (request.authority_signals.irreversible_decision and request.reversibility != "irreversible")


def _policy_valid(policy: ModelRoutingPolicy) -> bool:
    if type(policy.sha256) is not str or not _sha(policy.sha256) or type(policy.required_inputs) is not tuple or type(policy.precedence) is not tuple: return False
    if any(type(item) is not str or not item for item in policy.required_inputs) or any(type(rule) is not RoutingPrecedenceRule for rule in policy.precedence): return False
    if any(type(rule.priority) is not int or isinstance(rule.priority, bool) or type(rule.predicate_id) is not str or type(rule.disposition) is not str or type(rule.profile) is not str or type(rule.trigger_summary) is not str or not rule.trigger_summary for rule in policy.precedence): return False
    required = frozenset(policy.required_inputs)
    rules = tuple((rule.priority, rule.predicate_id, rule.disposition, rule.profile) for rule in policy.precedence)
    return len(policy.required_inputs) == len(required) and required == REQUIRED and rules == RULES


def _registry_valid(registry: ModelProfileRegistry) -> bool:
    if type(registry.cost_sensitive_enabled) is not bool or not _sha(registry.sha256) or not _sha(registry.rate_card_sha256) or type(registry.profiles) not in {dict, MappingProxyType}: return False
    rows = tuple(registry.profiles.items())
    if any(type(name) is not str or type(profile) is not ModelProfile for name, profile in rows): return False
    if frozenset(name for name, _ in rows) != PROFILES or len(rows) != len(PROFILES): return False
    for name, profile in rows:
        profile_strings = (profile.semantic_profile, profile.model_id, profile.reasoning_effort, profile.administrative_status, profile.service_tier_default, profile.speed_trait, profile.credit_trait, profile.rate_card_model_id)
        profile_ints = (profile.capability_rank, profile.capability_floor, profile.concurrency_cap)
        if any(type(item) is not str for item in profile_strings) or any(type(item) is not int or isinstance(item, bool) for item in profile_ints) or type(profile.authority) is not ModelProfileAuthority or type(profile.dispatchable) is not bool or type(profile.runtime_availability_required) is not bool or type(profile.allowed_task_types) is not tuple or (profile.fallback_profile is not None and type(profile.fallback_profile) is not str): return False
        if not profile.allowed_task_types or any(type(item) is not str for item in profile.allowed_task_types): return False
        executor = name in EXECUTORS
        expected_authority = ModelProfileAuthority.EXECUTOR if executor else ModelProfileAuthority.ROLE_LEAD if name == "role-lead-judgment" else ModelProfileAuthority.COMPANY_ROOT
        if profile.semantic_profile != name or profile.model_id not in SUPPORTED_MODELS or profile.reasoning_effort not in SUPPORTED_EFFORTS or profile.rate_card_model_id != profile.model_id or profile.capability_rank != RANKS[name] or profile.capability_floor != RANKS[name] or not 1 <= profile.concurrency_cap <= CAPS[name] or profile.dispatchable != executor or profile.authority != expected_authority or profile.administrative_status not in {"enabled", "disabled"} or profile.runtime_availability_required is not True or profile.service_tier_default not in SUPPORTED_SERVICE_TIERS or profile.speed_trait not in {"fast", "balanced", "deep"} or profile.credit_trait not in {"lowest", "moderate", "highest"} or len(profile.allowed_task_types) != len(set(profile.allowed_task_types)) or any(not _slug(item) for item in profile.allowed_task_types) or (not executor and profile.fallback_profile is not None): return False
    for start in EXECUTORS:
        seen: set[str] = set(); current: str | None = start
        for _ in range(7):
            if current is None: break
            if current in seen: return False
            seen.add(current); profile = registry.profiles.get(current)
            if profile is None: return False
            target = registry.profiles.get(profile.fallback_profile) if profile.fallback_profile is not None else None
            if target is not None and (target.authority != ModelProfileAuthority.EXECUTOR or target.capability_rank <= profile.capability_rank or target.capability_rank < profile.capability_floor): return False
            current = profile.fallback_profile
    return True


def _capacity_valid(registry: ModelProfileRegistry, capacity: ProfileCapacity) -> bool:
    if type(capacity.profiles) not in {dict, MappingProxyType}: return False
    scalars = (capacity.observed_at, capacity.evaluated_at, capacity.expires_at, capacity.operating_mode, capacity.operating_reason, capacity.evidence_ref, capacity.evidence_sha256)
    integers = (capacity.total_active, capacity.effective_total_cap, capacity.hard_total_cap)
    if any(type(item) is not str for item in scalars) or any(type(item) is not int or isinstance(item, bool) for item in integers): return False
    rows = tuple(capacity.profiles.items())
    if any(type(key) is not str or type(row) is not RuntimeProfileCapacity for key, row in rows): return False
    if frozenset(key for key, _ in rows) != EXECUTORS or len(rows) != len(EXECUTORS): return False
    for key, row in rows:
        if any(type(item) is not str for item in (row.semantic_profile, row.model_id, row.reasoning_effort, row.adapter)) or type(row.available) is not bool or type(row.active_count) is not int or isinstance(row.active_count, bool) or type(row.observed_cap) is not int or isinstance(row.observed_cap, bool) or type(row.supported_tools) is not tuple or any(type(tool) is not str for tool in row.supported_tools): return False
    stamps = tuple(_time(item) for item in (capacity.observed_at, capacity.evaluated_at, capacity.expires_at))
    mode_ok = (capacity.operating_mode == "normal" and capacity.operating_reason == "" and 4 <= capacity.effective_total_cap <= 8) or (capacity.operating_mode == "load_shed" and capacity.operating_reason in {"queue-pressure", "host-degradation"} and 1 <= capacity.effective_total_cap <= 3) or (capacity.operating_mode == "approved_burst" and capacity.operating_reason in {"role-lead-approval", "company-root-approval"} and 9 <= capacity.effective_total_cap <= 40)
    if capacity.hard_total_cap != 40 or capacity.total_active < 0 or capacity.total_active > capacity.effective_total_cap or not mode_ok or not _ref(capacity.evidence_ref) or not _sha(capacity.evidence_sha256): return False
    observed, evaluated, expires = stamps
    if observed is None or evaluated is None or expires is None or observed > evaluated or evaluated > expires: return False
    for key, row in rows:
        profile = registry.profiles[key]
        if key != row.semantic_profile or row.active_count < 0 or row.observed_cap < 0 or row.active_count > row.observed_cap or row.model_id != profile.model_id or row.reasoning_effort != profile.reasoning_effort or row.adapter not in ADAPTERS or (row.available and (row.adapter == "none" or row.observed_cap < 1)) or any(not _slug(tool) for tool in row.supported_tools) or len(row.supported_tools) != len(set(row.supported_tools)): return False
    return capacity.total_active >= sum(row.active_count for _, row in rows)


def _choose(request: ModelRoutingRequest, registry: ModelProfileRegistry) -> tuple[str, str | None, RoutingDisposition]:
    authority, dynamic = request.authority_signals, request.dynamic_risk_signals
    company_owned = frozenset(registry.profiles["company-judgment"].allowed_task_types)
    other_owned = frozenset(task for name, profile in registry.profiles.items() if name != "company-judgment" for task in profile.allowed_task_types)
    company_tasks = company_owned - other_owned
    role_tasks = registry.profiles["role-lead-judgment"].allowed_task_types
    specialist_tasks = registry.profiles["specialist-reasoning"].allowed_task_types
    integration_tasks = registry.profiles["integration"].allowed_task_types
    bounded_tasks = registry.profiles["bounded-deep"].allowed_task_types
    standard_tasks = registry.profiles["standard-implementation"].allowed_task_types
    mechanical_tasks = registry.profiles["mechanical"].allowed_task_types
    if authority.cross_role_conflict or authority.goal_change or authority.final_promotion or authority.rollback_decision or authority.irreversible_decision or request.task_type in company_tasks: return "company_authority_required", "company-judgment", RoutingDisposition.RETURN_TO_COMPANY_ROOT
    if request.task_type in role_tasks or "data-loss" in dynamic.risks or request.ambiguity in {"medium", "high"} or request.failure_impact == "critical" or request.reversibility == "irreversible" or dynamic.unexpected_emergence or dynamic.acceptance_conflict or dynamic.tests_passed_intent_unclear or any(sum(other.execution_failed and other.failure_cause == item.failure_cause for other in request.prior_attempts) >= 2 for item in request.prior_attempts): return "role_lead_judgment_required", "role-lead-judgment", RoutingDisposition.RETURN_TO_ROLE_LEAD
    if request.task_type in specialist_tasks or dynamic.initial_unknown_cause or bool(set(dynamic.risks) & RISKS): return "specialist_risk_or_unknown_cause", "specialist-reasoning", RoutingDisposition.DISPATCH
    approved_retry = any(item.execution_failed and item.role_lead_approved_retry for item in request.prior_attempts)
    integration_ready = request.expected_change_scope in {"multi-module", "long-context"} or request.critical_path or approved_retry
    known_integration = {"multi-module", "long-context", "critical-path", "approved-retry"}
    integration_match = (request.task_type == "multi-module" and request.expected_change_scope == "multi-module") or (request.task_type == "long-context" and request.expected_change_scope == "long-context") or (request.task_type == "critical-path" and request.critical_path) or (request.task_type == "approved-retry" and approved_retry) or (request.task_type not in known_integration and integration_ready)
    if request.task_type in integration_tasks and not integration_match: return "role_lead_judgment_required", "role-lead-judgment", RoutingDisposition.RETURN_TO_ROLE_LEAD
    if request.task_type in integration_tasks or integration_ready: return "integration_scope_or_approved_retry", "integration", RoutingDisposition.DISPATCH
    bounded_ready = request.difficult_or_long and request.ambiguity == "low" and request.automated_verifiability == "strong" and request.speed_or_credit_priority == "credit" and request.parallelizable
    if request.task_type in bounded_tasks and not bounded_ready: return "role_lead_judgment_required", "role-lead-judgment", RoutingDisposition.RETURN_TO_ROLE_LEAD
    if request.task_type in bounded_tasks or bounded_ready: return "bounded_deep_suitable", "bounded-deep", RoutingDisposition.DISPATCH if registry.cost_sensitive_enabled else RoutingDisposition.BLOCKED
    standard_ready = request.expected_change_scope == "multi-file" and request.clear_patterned_multi_file
    if request.task_type in standard_tasks and not standard_ready: return "role_lead_judgment_required", "role-lead-judgment", RoutingDisposition.RETURN_TO_ROLE_LEAD
    if request.task_type in standard_tasks or request.expected_change_scope == "multi-file": return ("standard_implementation_suitable", "standard-implementation", RoutingDisposition.DISPATCH) if standard_ready else ("role_lead_judgment_required", "role-lead-judgment", RoutingDisposition.RETURN_TO_ROLE_LEAD)
    if request.expected_change_scope == "single-site" and request.task_type in mechanical_tasks and request.ambiguity == "low" and request.failure_impact == "low" and request.reversibility == "reversible": return "default_mechanical", "mechanical", RoutingDisposition.DISPATCH
    return "role_lead_judgment_required", "role-lead-judgment", RoutingDisposition.RETURN_TO_ROLE_LEAD


def _sentinel(component: str) -> str: return _digest({"format": DECISION_FORMAT, "component": component, "state": "invalid"})


def _registry_projection(registry: ModelProfileRegistry) -> str:
    rows = tuple({"profile": name, "model": item.model_id, "effort": item.reasoning_effort, "authority": item.authority.value, "dispatchable": str(item.dispatchable), "status": item.administrative_status, "runtime_required": str(item.runtime_availability_required), "tier": item.service_tier_default, "speed": item.speed_trait, "credit": item.credit_trait, "tasks": ",".join(item.allowed_task_types), "rank": str(item.capability_rank), "floor": str(item.capability_floor), "fallback": item.fallback_profile or "", "cap": str(item.concurrency_cap), "rate_model": item.rate_card_model_id} for name, item in sorted(registry.profiles.items()))
    return _digest({"format": "agent-company.model-profile-registry-projection/v0.2", "profiles": rows})


def _policy_projection(policy: ModelRoutingPolicy) -> str:
    rows = tuple({"priority": str(item.priority), "predicate": item.predicate_id, "disposition": item.disposition, "profile": item.profile, "trigger": item.trigger_summary} for item in policy.precedence)
    return _digest({"format": "agent-company.model-routing-policy-projection/v0.2", "inputs": tuple(sorted(policy.required_inputs)), "rules": rows})


def _normalise(request: ModelRoutingRequest, registry: ModelProfileRegistry, policy: ModelRoutingPolicy, capacity: ProfileCapacity) -> NormalizedRoutingInput:
    errors: list[str] = []
    request_ok = type(request) is ModelRoutingRequest and _request_valid(request)
    registry_ok = type(registry) is ModelProfileRegistry and _registry_valid(registry)
    policy_ok = type(policy) is ModelRoutingPolicy and _policy_valid(policy)
    capacity_ok = registry_ok and type(capacity) is ProfileCapacity and _capacity_valid(registry, capacity)
    if not request_ok: errors.append("request.invalid")
    if not registry_ok: errors.append("registry.invalid")
    if not policy_ok: errors.append("policy.invalid")
    if not capacity_ok: errors.append("capacity.invalid")
    return NormalizedRoutingInput(request if request_ok else None, registry if registry_ok else None, policy if policy_ok else None, capacity if capacity_ok else None, _digest(_request_data(request)) if request_ok else _sentinel("request"), registry.sha256 if registry_ok else _sentinel("registry-file"), _registry_projection(registry) if registry_ok else _sentinel("registry-projection"), policy.sha256 if policy_ok else _sentinel("policy-file"), _policy_projection(policy) if policy_ok else _sentinel("policy-projection"), registry.rate_card_sha256 if registry_ok else _sentinel("rate-card"), _digest(_capacity_data(capacity)) if capacity_ok else _sentinel("capacity"), tuple(sorted(errors)))


def _decision(disposition: RoutingDisposition, requested: str | None, selected: str | None, predicate: str, reason: str, attempts: tuple[FallbackAttempt, ...], normal: NormalizedRoutingInput, model: str | None = None, effort: str | None = None, adapter: str | None = None) -> ModelRoutingDecision:
    payload = {"format": DECISION_FORMAT, "algorithm": CANONICAL_ALGORITHM, "disposition": disposition.value, "requested": requested, "selected": selected, "model": model, "effort": effort, "adapter": adapter, "predicate": predicate, "reason": reason, "attempts": tuple({"profile": item.semantic_profile, "cause": item.cause.value} for item in attempts), "request_format": REQUEST_FORMAT, "capacity_format": CAPACITY_FORMAT, "request_digest": normal.request_digest, "registry_digest": normal.registry_digest, "registry_projection_digest": normal.registry_projection_digest, "policy_digest": normal.policy_digest, "policy_projection_digest": normal.policy_projection_digest, "rate_card_digest": normal.rate_card_digest, "capacity_digest": normal.capacity_digest, "validation_errors": normal.errors}
    return ModelRoutingDecision(DECISION_FORMAT, CANONICAL_ALGORITHM, disposition, requested, selected, model, effort, adapter, predicate, reason, attempts, REQUEST_FORMAT, CAPACITY_FORMAT, normal.request_digest, normal.registry_digest, normal.registry_projection_digest, normal.policy_digest, normal.policy_projection_digest, normal.rate_card_digest, normal.capacity_digest, normal.errors, _digest(payload))


def route_model(request: ModelRoutingRequest, registry: ModelProfileRegistry, policy: ModelRoutingPolicy, capacity: ProfileCapacity) -> ModelRoutingDecision:
    """Select without filesystem, time, network, retry, spawn, or mutation."""
    normal = _normalise(request, registry, policy, capacity)
    if normal.errors: return _decision(RoutingDisposition.BLOCKED, None, None, "invalid_input", "versioned boundary validation failed", (), normal)
    if normal.request is None or normal.registry is None or normal.policy is None or normal.capacity is None: return _decision(RoutingDisposition.BLOCKED, None, None, "invalid_input", "normalization invariant failed", (), normal)
    request, registry, policy, capacity = normal.request, normal.registry, normal.policy, normal.capacity
    predicate, requested, disposition = _choose(request, registry)
    if disposition == RoutingDisposition.BLOCKED: return _decision(disposition, requested, None, predicate, "verified rate schedule is disabled", (), normal)
    if disposition != RoutingDisposition.DISPATCH: return _decision(disposition, requested, requested, predicate, "authority judgment is required", (), normal)
    if capacity.total_active >= capacity.effective_total_cap: return _decision(RoutingDisposition.BLOCKED, requested, None, predicate, "global effective capacity is saturated", (), normal)
    attempts: list[FallbackAttempt] = []; current = requested; visited: set[str] = set()
    for _ in range(7):
        if current is None or current in visited: return _decision(RoutingDisposition.BLOCKED, requested, None, predicate, "fallback chain is unsafe", tuple(attempts), normal)
        visited.add(current); profile, row = registry.profiles.get(current), capacity.profiles.get(current)
        if profile is None or row is None or current not in EXECUTORS or profile.authority != ModelProfileAuthority.EXECUTOR: return _decision(RoutingDisposition.BLOCKED, requested, None, predicate, "fallback target is unsafe", tuple(attempts), normal)
        if profile.administrative_status != "enabled": cause = FallbackCause.ADMINISTRATIVELY_DISABLED
        elif not row.available: cause = FallbackCause.RUNTIME_UNAVAILABLE
        elif not set(request.specialist_tools).issubset(row.supported_tools): cause = FallbackCause.TOOL_UNSUPPORTED
        elif row.active_count >= min(profile.concurrency_cap, row.observed_cap): cause = FallbackCause.PROFILE_SATURATED
        else: return _decision(RoutingDisposition.DISPATCH, requested, current, predicate, "registered profile selected", (*attempts, FallbackAttempt(current, FallbackCause.SELECTED)), normal, profile.model_id, profile.reasoning_effort, row.adapter)
        attempts.append(FallbackAttempt(current, cause)); current = profile.fallback_profile
        target = registry.profiles.get(current) if current is not None else None
        if target is not None and (target.authority != ModelProfileAuthority.EXECUTOR or target.capability_rank <= profile.capability_rank or target.capability_rank < profile.capability_floor): return _decision(RoutingDisposition.BLOCKED, requested, None, predicate, "fallback target is unsafe", tuple(attempts), normal)
    return _decision(RoutingDisposition.BLOCKED, requested, None, predicate, "fallback hop limit reached", tuple(attempts), normal)
