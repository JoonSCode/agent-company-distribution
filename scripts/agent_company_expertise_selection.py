from __future__ import annotations

from dataclasses import dataclass

from agent_company_expertise_models import RoleExpertise, SpecialistSpec


@dataclass(frozen=True, slots=True)
class ExpertiseSelectionError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


def applicable_specialists(
    role: RoleExpertise,
    task_type: str,
) -> tuple[SpecialistSpec, ...]:
    return tuple(
        specialist
        for specialist in role.optional_specialists
        if task_type in specialist.task_types
    )


def validate_specialist_selection(
    role: RoleExpertise,
    task_type: str,
    specialist_skills: tuple[str, ...],
    limit: int,
) -> None:
    if len(specialist_skills) > limit:
        raise ExpertiseSelectionError("specialist_limit_exceeded", "too many specialist skills")
    if len(set(specialist_skills)) != len(specialist_skills):
        raise ExpertiseSelectionError("specialist_selection_malformed", "specialists must be unique")
    registered = {item.skill_id: item for item in role.optional_specialists}
    for skill_id in specialist_skills:
        specialist = registered.get(skill_id)
        if specialist is None:
            raise ExpertiseSelectionError(
                "specialist_not_registered",
                f"{skill_id} is not registered for {role.role_id}",
            )
        if task_type not in specialist.task_types:
            raise ExpertiseSelectionError(
                "specialist_task_mismatch",
                f"{skill_id} does not apply to {task_type}",
            )
