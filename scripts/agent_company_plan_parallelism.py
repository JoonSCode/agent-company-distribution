#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# -- How to run --
# uv run scripts/test_agent_company_plan_delegation.py

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias, assert_never

from agent_company_deps import JsonValue
from agent_company_job_definition import recipe
from agent_company_projection_validation import (
    PolicyError,
    object_list,
    string_list,
    text,
)


JsonObject: TypeAlias = dict[str, JsonValue]


class DependencyCondition(StrEnum):
    NO_DIRECT_PREDECESSOR = "no-direct-predecessor"
    SAME_DIRECT_PREDECESSOR = "same-direct-predecessor"


@dataclass(frozen=True, slots=True)
class ParallelSlice:
    assignment_id: str
    leaf_id: str
    role: str
    objective: str
    depends_on: tuple[str, ...]


def selected_recipe(job: JsonObject) -> JsonObject:
    job_type = text(job.get("job_type"), "job_type")
    selected_id = text(job.get("selected_recipe_id"), "selected_recipe_id")
    selected = recipe(job_type)
    if (
        text(selected.get("id"), "recipe id") != selected_id
        or text(selected.get("job_type"), "recipe job_type") != job_type
    ):
        raise PolicyError("selected recipe does not bind the company-plan job")
    return selected


def _dependencies_match(
    dependency_condition: DependencyCondition,
    after: str,
    slices: Sequence[ParallelSlice],
) -> bool:
    match dependency_condition:
        case DependencyCondition.NO_DIRECT_PREDECESSOR:
            return after == "$company-plan" and all(not item.depends_on for item in slices)
        case DependencyCondition.SAME_DIRECT_PREDECESSOR:
            return all(item.depends_on == (after,) for item in slices)
        case unreachable:
            assert_never(unreachable)


def parallelism_evidence(
    selected: JsonObject,
    slices: Sequence[ParallelSlice],
) -> JsonObject:
    actual_roles = [item.role for item in slices]
    actual_stages = [item.leaf_id for item in slices]
    actual_slices = [item.objective for item in slices]
    for candidate in object_list(selected.get("parallel_candidates"), "parallel_candidates"):
        if candidate.get("surface") != "company-plan":
            continue
        candidate_id = text(candidate.get("id"), "parallel candidate id")
        after = text(candidate.get("after"), "parallel predecessor")
        raw_dependency = text(
            candidate.get("dependency_condition"),
            "parallel dependency_condition",
        )
        try:
            dependency = DependencyCondition(raw_dependency)
        except ValueError as exc:
            raise PolicyError(
                "company-plan parallel candidate has unsupported dependency_condition",
            ) from exc
        roles = string_list(candidate.get("roles"), "parallel roles")
        stage_ids = string_list(candidate.get("stage_ids"), "parallel stage_ids")
        slice_names = string_list(candidate.get("slices"), "parallel slices")
        condition = text(
            candidate.get("independence_condition"),
            "parallel independence_condition",
        )
        if not (
            roles == actual_roles
            and stage_ids == actual_stages
            and slice_names == actual_slices
            and _dependencies_match(dependency, after, slices)
        ):
            continue
        return {
            "source": "selected-squad-recipe",
            "recipe_id": text(selected.get("id"), "recipe id"),
            "candidate_id": candidate_id,
            "predecessor": after,
            "dependency_condition": dependency.value,
            "independence_condition": condition,
            "assignment_ids": [item.assignment_id for item in slices],
            "role_slices": [
                {"role": item.role, "slice": item.objective, "stage_id": item.leaf_id}
                for item in slices
            ],
        }
    raise PolicyError(
        "parallel company-plan wave has no exact selected recipe candidate",
    )
