#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Import through the plan validator:
#      python3 scripts/agent_company_plans.py check --help
# 3. Run its focused tests:
#      python3 scripts/test_agent_company_plans.py
# ─────────────────

from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from agent_company_operating_contracts import OperatingContractBinding

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
RUNTIME_PATTERN = re.compile(r"\$\{SEJONG_HOME\}/runs/agent-company/[A-Za-z0-9._-]+/.+")


@dataclass(frozen=True, slots=True)
class PlanError(Exception):
    code: str
    path: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code} at {self.path}: {self.detail}"


@dataclass(frozen=True, slots=True)
class Assignment:
    id: str
    leaf_id: str
    role: str
    read_scope: frozenset[str]
    write_scope: frozenset[str]
    outputs: frozenset[str]
    forbidden_mutations: frozenset[str]
    acceptance_criteria: frozenset[str] | None


@dataclass(frozen=True, slots=True)
class CompanyPlan:
    path: Path
    sha256: str
    id: str
    assignments: Mapping[str, Assignment]


@dataclass(frozen=True, slots=True)
class ReceiptBinding:
    ref: str
    resolved_ref: Path
    receipt_id: str
    role_plan_id: str
    assignment_id: str
    role: str


@dataclass(frozen=True, slots=True)
class RolePlanBinding:
    role_plan_id: str
    role_plan_ref: Path
    role_plan_sha256: str
    assignment_id: str
    leaf_id: str
    role: str
    read_scope: tuple[str, ...]
    write_scope: tuple[str, ...]
    outputs: tuple[str, ...]
    forbidden_mutations: tuple[str, ...]
    receipt: ReceiptBinding
    operating_contract: OperatingContractBinding | None
    inputs: tuple[str, ...]
    role_local_qa: tuple[str, ...]
    escalation_triggers: tuple[str, ...]
    qa_verification: JsonValue | None = None


@dataclass(frozen=True, slots=True)
class PlanCheck:
    plan_id: str
    assignment_count: int
    role_plan_count: int
    role_bindings: tuple[RolePlanBinding, ...]


def object_value(value: JsonValue, path: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise PlanError("malformed_input", path, "must be an object")
    return value


def text_value(value: JsonValue, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanError("malformed_input", path, "must be a non-empty string")
    return value


def text_values(value: JsonValue, path: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise PlanError("malformed_input", path, "must be an array of strings")
    result = tuple(text_value(item, f"{path}[]") for item in value)
    if len(result) != len(set(result)):
        raise PlanError("malformed_input", path, "must contain unique values")
    return result


def item_values(value: JsonValue, path: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise PlanError("malformed_input", path, "must be an array")
    return value


def require_keys(value: dict[str, JsonValue], fields: frozenset[str], path: str) -> None:
    missing = sorted(fields - value.keys())
    extra = sorted(value.keys() - fields)
    if missing or extra:
        raise PlanError("malformed_input", path, f"missing={missing}; extra={extra}")


def load_object(path: Path) -> dict[str, JsonValue]:
    try:
        parsed: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanError("malformed_input", str(path), f"cannot load JSON: {exc}") from exc
    return object_value(parsed, str(path))


def file_sha256(path: Path, code: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise PlanError(code, str(path), "referenced artifact is unavailable") from exc


def runtime_reference(value: JsonValue, path: str, env: Mapping[str, str]) -> tuple[str, Path]:
    reference = text_value(value, path)
    if RUNTIME_PATTERN.fullmatch(reference) is None:
        raise PlanError("malformed_input", path, "must remain under ${SEJONG_HOME}/runs/agent-company/<run-id>")
    home_value = env.get("SEJONG_HOME")
    if not home_value:
        raise PlanError("runtime_home_required", path, "SEJONG_HOME is required to resolve runtime refs")
    home = Path(home_value).expanduser().resolve()
    runtime_root = (home / "runs" / "agent-company").resolve()
    if not runtime_root.is_relative_to(home):
        raise PlanError("runtime_ref_escape", path, "runtime root resolves outside SEJONG_HOME")
    relative = reference.removeprefix("${SEJONG_HOME}/")
    resolved = (home / relative).resolve(strict=False)
    if not resolved.is_relative_to(runtime_root):
        raise PlanError("runtime_ref_escape", path, "resolved path escapes the Agent Company runtime root")
    if len(resolved.relative_to(runtime_root).parts) < 2:
        raise PlanError("malformed_input", path, "runtime ref must include a run id and artifact path")
    return reference, resolved


def verify_uigwe_binding(value: JsonValue, path: str, env: Mapping[str, str]) -> None:
    binding = object_value(value, path)
    require_keys(binding, frozenset({"packet_ref", "packet_sha256", "decision_ref", "decision_sha256"}), path)
    for kind in ("packet", "decision"):
        _, resolved = runtime_reference(binding.get(f"{kind}_ref"), f"{path}.{kind}_ref", env)
        expected = text_value(binding.get(f"{kind}_sha256"), f"{path}.{kind}_sha256")
        if re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise PlanError("malformed_input", f"{path}.{kind}_sha256", "must be a lowercase SHA-256")
        if file_sha256(resolved, "stale_uigwe") != expected:
            raise PlanError("stale_uigwe", f"{path}.{kind}_sha256", "referenced bytes do not match")


def receipt_binding(value: JsonValue, path: str, env: Mapping[str, str]) -> ReceiptBinding:
    binding = object_value(value, path)
    fields = frozenset({"ref", "receipt_id", "role_plan_id", "assignment_id", "role"})
    require_keys(binding, fields, path)
    reference, resolved = runtime_reference(binding.get("ref"), f"{path}.ref", env)
    return ReceiptBinding(
        reference,
        resolved,
        text_value(binding.get("receipt_id"), f"{path}.receipt_id"),
        text_value(binding.get("role_plan_id"), f"{path}.role_plan_id"),
        text_value(binding.get("assignment_id"), f"{path}.assignment_id"),
        text_value(binding.get("role"), f"{path}.role"),
    )
