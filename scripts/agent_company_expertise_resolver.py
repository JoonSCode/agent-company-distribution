from __future__ import annotations

import re
from dataclasses import dataclass
from typing import final, override

from agent_company_expertise_catalog import load_expertise_catalog
from agent_company_expertise_models import ExpertiseCatalog
from agent_company_expertise_routing import load_routing_policy
from agent_company_expertise_routing_models import (
    RoleRouting,
    RoutingPolicy,
    RoutingPolicyError,
    TaskRule,
)
from agent_company_role_schema import JsonValue


@final
class ExpertiseResolutionError(Exception):
    __slots__ = ("code", "detail")

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)
        self.code = code
        self.detail = detail

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class SpecialistDecision:
    skill_id: str
    decision_question: str
    expected_marginal_value: str
    matched_triggers: tuple[str, ...]
    loading_cost: str

    def payload(self) -> dict[str, JsonValue]:
        return {
            "skill_id": self.skill_id,
            "decision_question": self.decision_question,
            "expected_marginal_value": self.expected_marginal_value,
            "matched_triggers": list(self.matched_triggers),
            "loading_cost": self.loading_cost,
        }


@dataclass(frozen=True, slots=True)
class ExpertiseResolution:
    role: str
    role_os_skill: str
    task_type: str
    task_pack_id: str
    required_reference_ids: tuple[str, ...]
    decision_questions: tuple[str, ...]
    specialists: tuple[SpecialistDecision, ...]
    classification_basis: str
    matched_triggers: tuple[str, ...]
    ambiguous_task_types: tuple[str, ...]
    routing_sha256: str

    @property
    def specialist_skills(self) -> tuple[str, ...]:
        return tuple(item.skill_id for item in self.specialists)

    def selection_payload(self) -> dict[str, JsonValue]:
        return {
            "role_os_skill": self.role_os_skill,
            "task_pack_id": self.task_pack_id,
            "classification_basis": self.classification_basis,
            "matched_triggers": list(self.matched_triggers),
            "ambiguous_task_types": list(self.ambiguous_task_types),
            "specialists": [item.payload() for item in self.specialists],
        }


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _matches(text: str, triggers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(trigger for trigger in triggers if trigger in text)


def _task_selection(
    routing: RoleRouting,
    objective: str,
    task_hint: str | None,
) -> tuple[TaskRule, str, tuple[str, ...], tuple[str, ...]]:
    text = _normalized(objective)
    if task_hint is not None:
        selected = next(
            (item for item in routing.task_rules if item.task_type == task_hint),
            None,
        )
        if selected is None:
            raise ExpertiseResolutionError(
                "task_hint_invalid",
                f"task_hint {task_hint} is not registered for {routing.role_id}",
            )
        return selected, "explicit_hint", _matches(text, selected.triggers), ()
    scored = [
        (len(_matches(text, rule.triggers)), index, rule)
        for index, rule in enumerate(routing.task_rules)
    ]
    best_score = max(item[0] for item in scored)
    if best_score == 0:
        selected = next(
            item for item in routing.task_rules
            if item.task_type == routing.default_task_type
        )
        return selected, "role_default", (), ()
    candidates = [item for item in scored if item[0] == best_score]
    _, _, selected = candidates[0]
    ambiguous = tuple(item[2].task_type for item in candidates[1:])
    basis = "trigger_match" if not ambiguous else "trigger_priority"
    return selected, basis, _matches(text, selected.triggers), ambiguous


def _specialists(
    routing: RoleRouting,
    objective: str,
    task_type: str,
    catalog: ExpertiseCatalog,
) -> tuple[SpecialistDecision, ...]:
    text = _normalized(objective)
    expertise = catalog.roles[routing.role_id]
    specs = {item.skill_id: item for item in expertise.optional_specialists}
    ranked: list[tuple[int, int, int, SpecialistDecision]] = []
    loading_rank = {"small": 0, "medium": 1, "large": 2}
    for index, rule in enumerate(routing.specialist_rules):
        spec = specs[rule.skill_id]
        matched = _matches(text, rule.triggers)
        if task_type not in spec.task_types or not matched:
            continue
        ranked.append((
            -len(matched),
            loading_rank[spec.loading_cost],
            index,
            SpecialistDecision(
                spec.skill_id,
                spec.decision_questions[0],
                spec.distinct_evidence,
                matched,
                spec.loading_cost,
            ),
        ))
    ranked.sort(key=lambda item: item[:3])
    return tuple(item[3] for item in ranked[:catalog.default_specialist_limit])


def resolve_expertise(
    role: str,
    objective: str,
    *,
    task_hint: str | None = None,
    catalog: ExpertiseCatalog | None = None,
    policy: RoutingPolicy | None = None,
) -> ExpertiseResolution:
    if not objective.strip():
        raise ExpertiseResolutionError("objective_required", "objective must be non-empty")
    selected_catalog = catalog or load_expertise_catalog()
    try:
        selected_policy = policy or load_routing_policy(
            selected_catalog.root,
            selected_catalog,
        )
    except RoutingPolicyError as exc:
        raise ExpertiseResolutionError(exc.code, exc.detail) from exc
    routing = selected_policy.roles.get(role)
    expertise = selected_catalog.roles.get(role)
    if routing is None or expertise is None:
        raise ExpertiseResolutionError("role_unsupported", role)
    task, basis, matched, ambiguous = _task_selection(
        routing,
        objective,
        task_hint,
    )
    task_pack = selected_catalog.references[task.reference_id]
    kernel = selected_catalog.references[expertise.role_kernel_id]
    decisions = tuple(dict.fromkeys([
        *kernel.decision_questions,
        *task_pack.decision_questions,
    ]))
    return ExpertiseResolution(
        role,
        expertise.role_os_skill,
        task.task_type,
        task.reference_id,
        (expertise.role_kernel_id, task.reference_id),
        decisions,
        _specialists(routing, objective, task.task_type, selected_catalog),
        basis,
        matched,
        ambiguous,
        selected_policy.sha256,
    )
