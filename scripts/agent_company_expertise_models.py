from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import override


class ExpertiseCatalogError(Exception):
    code: str
    detail: str

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class SpecialistSpec:
    skill_id: str
    selection_status: str
    task_types: tuple[str, ...]
    decision_questions: tuple[str, ...]
    distinct_evidence: str
    allowed_use: str
    loading_cost: str
    stop_condition: str


@dataclass(frozen=True, slots=True)
class ReferenceFreshness:
    mode: str
    reviewed_at: str
    expires_at: str | None
    recheck_triggers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReferenceSpec:
    id: str
    version: str
    layer: str
    owner_role: str
    ref: str
    source_url: str | None
    sha256: str
    applies_to_tasks: tuple[str, ...]
    decision_questions: tuple[str, ...]
    authority_class: str
    allowed_uses: tuple[str, ...]
    freshness: ReferenceFreshness
    loading_cost: str
    dependencies: tuple[str, ...]
    conflicts: tuple[str, ...]
    evaluation_refs: tuple[str, ...]
    status: str
    replaced_by: str | None


@dataclass(frozen=True, slots=True)
class RoleExpertise:
    role_id: str
    role_os_skill: str
    role_kernel_id: str
    default_task_type: str
    default_verifier: str
    optional_specialists: tuple[SpecialistSpec, ...]

    @property
    def optional_specialist_ids(self) -> tuple[str, ...]:
        return tuple(item.skill_id for item in self.optional_specialists)

    @property
    def automatic_specialist_ids(self) -> tuple[str, ...]:
        return tuple(
            item.skill_id
            for item in self.optional_specialists
            if item.selection_status == "automatic"
        )


@dataclass(frozen=True, slots=True)
class ExpertiseCatalog:
    root: Path
    registry_sha256: str
    manifest_sha256: str
    default_specialist_limit: int
    roles: Mapping[str, RoleExpertise]
    references: Mapping[str, ReferenceSpec]
