#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Import from agent_company_projection_policy.py.
# 2. Verify with: python3 scripts/test_agent_company_policy_suite.py
# ──────────────────

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TypeAlias

from agent_company_deps import JsonValue


JsonObject: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class PolicyError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


def object_list(value: JsonValue, label: str) -> list[JsonObject]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise PolicyError(f"{label} must be an object list")
    return [item for item in value if isinstance(item, dict)]


def string_list(value: JsonValue, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PolicyError(f"{label} must be a string list")
    return [item for item in value if isinstance(item, str)]


def text(value: JsonValue, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PolicyError(f"{label} must be non-empty text")
    return value


def read_bound_object(reference: str, label: str) -> tuple[JsonObject, str, str]:
    path = Path(reference).expanduser().resolve()
    try:
        payload = path.read_bytes()
        value: JsonValue = json.loads(payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PolicyError(f"{label} root must be an object: {path}")
    return value, str(path), sha256(payload).hexdigest()


def validate_delegation_gate(job: JsonObject) -> None:
    gate = job.get("uigwe_gate")
    if not isinstance(gate, dict):
        raise PolicyError("uigwe_gate must be an object")
    required = gate.get("required")
    status = gate.get("status")
    if required is False and status == "not-needed":
        if set(gate) != {"required", "status"}:
            raise PolicyError("not-needed Uigwe gate must not contain decision or packet material")
        return
    if required is True and status == "pending-user" and set(gate) == {"required", "status"}:
        raise PolicyError("Uigwe approval is pending")
    if required is not True or status != "approved":
        raise PolicyError("Uigwe gate is not delegation-ready")
    expected = {
        "required", "status", "packet_ref", "packet_refs", "packet_sha256",
        "decision_ref", "decision_hash", "decision_sha256",
    }
    if set(gate) != expected:
        raise PolicyError("approved Uigwe gate evidence is incomplete")
    job_id = text(job.get("job_id"), "job_id")
    packet_ref = text(gate.get("packet_ref"), "Uigwe packet ref")
    packet_sha = text(gate.get("packet_sha256"), "Uigwe packet sha256")
    decision_ref = text(gate.get("decision_ref"), "Uigwe decision ref")
    decision_sha = text(gate.get("decision_sha256"), "Uigwe decision sha256")
    if gate.get("packet_refs") != [packet_ref] or gate.get("decision_hash") != decision_sha:
        raise PolicyError("Uigwe gate compatibility evidence does not match byte-bound evidence")
    packet, canonical_packet_ref, actual_packet_sha = read_bound_object(packet_ref, "Uigwe packet")
    decision, canonical_decision_ref, actual_decision_sha = read_bound_object(decision_ref, "Uigwe decision")
    if canonical_packet_ref != packet_ref or canonical_decision_ref != decision_ref:
        raise PolicyError("Uigwe evidence refs must be canonical paths")
    if actual_packet_sha != packet_sha or actual_decision_sha != decision_sha:
        raise PolicyError("Uigwe evidence bytes do not match the approved hashes")
    decision_packet = decision.get("uigwe_packet")
    if (
        decision.get("format") != "agent-company.uigwe-decision/v0.1"
        or decision.get("job_id") != job_id
        or decision.get("decision_authority") not in {"user", "ceo"}
        or not isinstance(decision_packet, dict)
        or decision_packet.get("job_id") != job_id
    ):
        raise PolicyError("Uigwe decision is not bound to this job")
    bound_packet_ref = text(decision_packet.get("ref"), "decision Uigwe packet ref")
    if str(Path(bound_packet_ref).expanduser().resolve()) != packet_ref:
        raise PolicyError("Uigwe decision packet ref does not match the approved packet")
    packet_format = packet.get("format")
    if not isinstance(packet_format, str) or not packet_format.startswith("uigwe.") or packet.get("approval_status") != "approved":
        raise PolicyError("Uigwe packet must remain an approved Uigwe artifact")


def parallel_groups(stages: list[JsonObject], recipe: JsonObject) -> dict[str, JsonObject]:
    matches: dict[str, JsonObject] = {}
    for candidate in object_list(recipe.get("parallel_candidates"), "parallel_candidates"):
        if candidate.get("surface") == "company-plan":
            continue
        after = text(candidate.get("after"), "parallel predecessor")
        roles = string_list(candidate.get("roles"), "parallel roles")
        slices = string_list(candidate.get("slices"), "parallel slices")
        condition = text(candidate.get("independence_condition"), "independence_condition")
        if len(roles) != len(slices):
            raise PolicyError("parallel candidate roles and slices must align")
        explicit_stage_ids = candidate.get("stage_ids")
        role_stages: list[JsonObject] = []
        if explicit_stage_ids is not None:
            stage_ids = string_list(explicit_stage_ids, "parallel stage_ids")
            if len(stage_ids) != len(roles):
                raise PolicyError("parallel candidate stage ids and roles must align")
            by_id = {text(stage.get("id"), "stage id"): stage for stage in stages}
            role_stages = [by_id[stage_id] for stage_id in stage_ids if stage_id in by_id]
            valid = len(role_stages) == len(roles) and all(
                role in string_list(stage.get("owner_roles"), "owner_roles")
                and string_list(stage.get("depends_on"), "depends_on") == [after]
                for role, stage in zip(roles, role_stages, strict=True)
            )
            if not valid:
                role_stages = []
        else:
            for role in roles:
                owned = [
                    stage for stage in stages
                    if string_list(stage.get("owner_roles"), "owner_roles") == [role]
                    and string_list(stage.get("depends_on"), "depends_on") == [after]
                ]
                if len(owned) != 1:
                    role_stages = []
                    break
                role_stages.append(owned[0])
        if len(role_stages) != len(roles):
            continue
        stage_ids = [text(stage.get("id"), "stage id") for stage in role_stages]
        evidence: JsonObject = {
            "recipe_id": text(recipe.get("id"), "recipe id"),
            "predecessor": after,
            "independence_condition": condition,
            "role_slices": [
                {"role": role, "slice": slice_name, "stage_id": stage_id}
                for role, slice_name, stage_id in zip(roles, slices, stage_ids, strict=True)
            ],
        }
        for stage_id in stage_ids:
            stage_id_values: list[JsonValue] = list(stage_ids)
            binding: JsonObject = {
                "stage_ids": stage_id_values,
                "evidence": evidence,
            }
            matches[stage_id] = binding
    return matches
