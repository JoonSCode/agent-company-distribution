from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import final, override


@final
class RoutingPolicyError(Exception):
    __slots__ = ("code", "detail")

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)
        self.code = code
        self.detail = detail

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class TaskRule:
    task_type: str
    reference_id: str
    triggers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SpecialistRule:
    skill_id: str
    triggers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RoleRouting:
    role_id: str
    default_task_type: str
    task_rules: tuple[TaskRule, ...]
    specialist_rules: tuple[SpecialistRule, ...]


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    path: Path
    sha256: str
    roles: Mapping[str, RoleRouting]
