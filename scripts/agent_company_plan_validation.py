#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Validate through the public CLI:
#      python3 scripts/agent_company_plans.py check --help
# 3. Run focused tests:
#      python3 scripts/test_agent_company_plans.py
# ─────────────────

from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from agent_company_operating_contracts import (
    OperatingContractError,
    bind_operating_contract,
)
from agent_company_plan_models import (
    Assignment,
    CompanyPlan,
    JsonValue,
    PlanCheck,
    PlanError,
    RolePlanBinding,
    file_sha256,
    item_values,
    load_object,
    object_value,
    receipt_binding,
    require_keys,
    runtime_reference,
    text_value,
    text_values,
    verify_uigwe_binding,
)
from agent_company_plan_qa_binding import qa_plan_binding

ROLES = frozenset({"founder", "planning", "marketing", "design", "development", "qa-release"})
PROTECTED_MUTATIONS = frozenset({"uigwe_scope", "company_success_criteria", "company_stop_criteria", "dependency_dag", "other_assignments", "sejong_synthesis", "verification_authority"})
MATERIAL_FIELDS = frozenset({"objective", "uigwe_binding", "company_success_criteria", "company_stop_criteria"})
DELTA_PROTECTED_FIELDS = frozenset({"assignments", "outputs", "read_scope", "write_scope", "forbidden_mutations", "role", "leaf_id", "assignment_id"})
CHANGE_PATH_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*(?:\[[0-9]+\]|\.[A-Za-z_][A-Za-z0-9_-]*)*")
COMPANY_FIELDS = frozenset({"format", "plan_id", "job_id", "objective", "material_ambiguity", "uigwe_binding", "milestones", "assignments", "company_success_criteria", "company_stop_criteria", "decision_register", "planning_deltas", "reentry_triggers", "sejong_synthesis_ref"})
ROLE_FIELDS = frozenset({"format", "role_plan_id", "company_plan_id", "company_plan_ref", "company_plan_sha256", "assignment_id", "leaf_id", "role", "inputs", "local_approach", "read_scope", "write_scope", "outputs", "role_local_qa", "escalation_triggers", "forbidden_mutations", "execution_receipt_binding"})
ROLE_CONTRACT_FIELDS = frozenset({"operating_contract_ref", "operating_contract_sha256"})
ROLE_QA_FIELDS = frozenset({"qa_verification"})


def _parse_assignment(value: JsonValue, index: int) -> Assignment:
    path = f"$company.assignments[{index}]"
    raw = object_value(value, path)
    fields = frozenset({"id", "leaf_id", "role", "objective", "read_scope", "write_scope", "outputs", "forbidden_mutations"})
    optional_fields = frozenset({"acceptance_criteria"})
    require_keys(raw, fields | (set(raw) & optional_fields), path)
    role, _ = text_value(raw.get("role"), f"{path}.role"), text_value(raw.get("objective"), f"{path}.objective")
    if role not in ROLES:
        raise PlanError("malformed_input", f"{path}.role", "unsupported role")
    return Assignment(
        text_value(raw.get("id"), f"{path}.id"),
        text_value(raw.get("leaf_id"), f"{path}.leaf_id"),
        role,
        frozenset(text_values(raw.get("read_scope"), f"{path}.read_scope")),
        frozenset(text_values(raw.get("write_scope"), f"{path}.write_scope")),
        frozenset(text_values(raw.get("outputs"), f"{path}.outputs")),
        frozenset(text_values(raw.get("forbidden_mutations"), f"{path}.forbidden_mutations")),
        (
            frozenset(
                text_values(
                    raw.get("acceptance_criteria"),
                    f"{path}.acceptance_criteria",
                ),
            )
            if "acceptance_criteria" in raw
            else None
        ),
    )


def _check_dag(graph: Mapping[str, tuple[str, ...]]) -> None:
    remaining = set(graph)
    while remaining:
        ready = {node for node in remaining if not (set(graph[node]) & remaining)}
        unknown = {edge for node in remaining for edge in graph[node] if edge not in graph}
        if unknown:
            raise PlanError("unbound_assignment", "$company.milestones", f"unknown dependencies: {sorted(unknown)}")
        if not ready:
            raise PlanError("dependency_cycle", "$company.milestones", f"cycle includes {sorted(remaining)}")
        remaining -= ready


def _parse_milestones(raw: dict[str, JsonValue]) -> set[str]:
    milestones: dict[str, tuple[str, ...]] = {}
    for index, item in enumerate(item_values(raw.get("milestones"), "$company.milestones")):
        path = f"$company.milestones[{index}]"
        milestone = object_value(item, path)
        require_keys(milestone, frozenset({"id", "objective", "depends_on"}), path)
        milestone_id = text_value(milestone.get("id"), f"{path}.id")
        text_value(milestone.get("objective"), f"{path}.objective")
        if milestone_id in milestones:
            raise PlanError("duplicate_leaf_ownership", milestone_id, "milestone id is duplicated")
        milestones[milestone_id] = text_values(milestone.get("depends_on"), f"{path}.depends_on", allow_empty=True)
    if not milestones:
        raise PlanError("malformed_input", "$company.milestones", "must not be empty")
    _check_dag(milestones)
    return set(milestones)


def _parse_assignments(raw: dict[str, JsonValue], leaves: set[str]) -> dict[str, Assignment]:
    assignments: dict[str, Assignment] = {}
    owned_leaves: set[str] = set()
    for index, item in enumerate(item_values(raw.get("assignments"), "$company.assignments")):
        assignment = _parse_assignment(item, index)
        if assignment.id in assignments or assignment.leaf_id in owned_leaves:
            raise PlanError("duplicate_leaf_ownership", assignment.leaf_id, "assignment or leaf is already owned")
        if assignment.leaf_id not in leaves:
            raise PlanError("unbound_assignment", assignment.id, "leaf does not exist")
        assignments[assignment.id] = assignment
        owned_leaves.add(assignment.leaf_id)
    if not assignments:
        raise PlanError("malformed_input", "$company.assignments", "must not be empty")
    return assignments


def _validate_decisions(raw: dict[str, JsonValue], env: Mapping[str, str]) -> None:
    for index, value in enumerate(item_values(raw.get("decision_register"), "$company.decision_register")):
        path = f"$company.decision_register[{index}]"
        decision = object_value(value, path)
        require_keys(decision, frozenset({"id", "status", "summary", "owner", "evidence_refs"}), path)
        _, status, _, owner = (text_value(decision.get(field), f"{path}.{field}") for field in ("id", "status", "summary", "owner"))
        if status not in {"proposed", "approved", "rejected", "superseded"} or owner not in {"uigwe", "sejong", "planning"}:
            raise PlanError("malformed_input", path, "unsupported status or owner")
        for reference in text_values(decision.get("evidence_refs"), f"{path}.evidence_refs"):
            runtime_reference(reference, f"{path}.evidence_refs[]", env)


def _validate_deltas(raw: dict[str, JsonValue], env: Mapping[str, str]) -> None:
    for index, value in enumerate(item_values(raw.get("planning_deltas"), "$company.planning_deltas")):
        path = f"$company.planning_deltas[{index}]"
        delta = object_value(value, path)
        require_keys(delta, frozenset({"id", "kind", "summary", "changed_fields", "uigwe_reentry"}), path)
        _, kind, _ = (text_value(delta.get(field), f"{path}.{field}") for field in ("id", "kind", "summary"))
        if kind not in {"schedule", "dependency", "material"}:
            raise PlanError("malformed_input", f"{path}.kind", "unsupported delta kind")
        changed = text_values(delta.get("changed_fields"), f"{path}.changed_fields")
        for field in changed:
            if CHANGE_PATH_PATTERN.fullmatch(field) is None:
                raise PlanError("malformed_input", f"{path}.changed_fields", f"invalid change path: {field}")
            tokens = frozenset(re.findall(r"[A-Za-z_][A-Za-z0-9_-]*", field))
            if tokens & DELTA_PROTECTED_FIELDS:
                raise PlanError("forbidden_planning_delta", f"{path}.changed_fields", "Planning cannot mutate role-owned assignment fields")
        material = kind == "material" or any(field.split(".", 1)[0] in MATERIAL_FIELDS for field in changed)
        if material and delta.get("uigwe_reentry") is None:
            raise PlanError("uigwe_reentry_required", path, "material Planning delta requires Uigwe re-entry")
        if delta.get("uigwe_reentry") is not None:
            verify_uigwe_binding(delta.get("uigwe_reentry"), f"{path}.uigwe_reentry", env)


def _parse_company(path: Path, env: Mapping[str, str]) -> CompanyPlan:
    raw = load_object(path)
    require_keys(raw, COMPANY_FIELDS, "$company")
    if raw.get("format") != "agent-company.company-plan/v0.2":
        raise PlanError("malformed_input", "$company.format", "unsupported format")
    if raw.get("material_ambiguity") is not True or raw.get("uigwe_binding") is None:
        raise PlanError("uigwe_binding_required", "$company.uigwe_binding", "company objective and done criteria require byte-bound Uigwe authority")
    verify_uigwe_binding(raw.get("uigwe_binding"), "$company.uigwe_binding", env)
    leaves = _parse_milestones(raw)
    assignments = _parse_assignments(raw, leaves)
    _ = text_value(raw.get("job_id"), "$company.job_id"), text_value(raw.get("objective"), "$company.objective")
    for field in ("company_success_criteria", "company_stop_criteria", "reentry_triggers"):
        text_values(raw.get(field), f"$company.{field}")
    runtime_reference(raw.get("sejong_synthesis_ref"), "$company.sejong_synthesis_ref", env)
    _validate_decisions(raw, env)
    _validate_deltas(raw, env)
    return CompanyPlan(path, file_sha256(path, "stale_state"), text_value(raw.get("plan_id"), "$company.plan_id"), assignments)


def _parse_role(path: Path, company: CompanyPlan, env: Mapping[str, str]) -> RolePlanBinding:
    raw = load_object(path)
    missing = set(ROLE_FIELDS - raw.keys())
    extra = set(
        raw.keys() - (ROLE_FIELDS | ROLE_CONTRACT_FIELDS | ROLE_QA_FIELDS),
    )
    if missing or extra:
        raise PlanError("malformed_input", str(path), f"missing={sorted(missing)}; extra={sorted(extra)}")
    if raw.get("format") != "agent-company.role-plan/v0.2":
        raise PlanError("malformed_input", str(path), "unsupported role-plan format")
    role_plan_id = text_value(raw.get("role_plan_id"), f"{path}.role_plan_id")
    if Path(text_value(raw.get("company_plan_ref"), f"{path}.company_plan_ref")).resolve() != company.path:
        raise PlanError("stale_state", f"{path}.company_plan_ref", "does not bind the checked company plan")
    if text_value(raw.get("company_plan_sha256"), f"{path}.company_plan_sha256") != company.sha256 or text_value(raw.get("company_plan_id"), f"{path}.company_plan_id") != company.id:
        raise PlanError("stale_state", str(path), "company plan identity or bytes changed")
    assignment_id = text_value(raw.get("assignment_id"), f"{path}.assignment_id")
    assignment = company.assignments.get(assignment_id)
    if assignment is None:
        raise PlanError("unbound_assignment", f"{path}.assignment_id", "assignment does not exist")
    leaf, role = text_value(raw.get("leaf_id"), f"{path}.leaf_id"), text_value(raw.get("role"), f"{path}.role")
    if leaf != assignment.leaf_id or role != assignment.role:
        raise PlanError("unbound_assignment", str(path), "role or leaf disagrees with assignment")
    qa_verification = qa_plan_binding(raw, role, path)
    try:
        operating_contract = bind_operating_contract(
            role,
            raw.get("operating_contract_ref"),
            raw.get("operating_contract_sha256"),
        )
    except OperatingContractError as exc:
        raise PlanError(exc.code, f"{path}.operating_contract", exc.detail) from exc
    requested_fields: dict[str, tuple[str, ...]] = {}
    for field, allowed in (("read_scope", assignment.read_scope), ("write_scope", assignment.write_scope), ("outputs", assignment.outputs)):
        values = text_values(raw.get(field), f"{path}.{field}")
        requested_fields[field] = values
        requested = frozenset(values)
        if not requested <= allowed:
            raise PlanError("scope_widening", f"{path}.{field}", f"outside assignment: {sorted(requested - allowed)}")
    forbidden_values = text_values(
        raw.get("forbidden_mutations"),
        f"{path}.forbidden_mutations",
    )
    forbidden = frozenset(forbidden_values)
    if not (required := PROTECTED_MUTATIONS | assignment.forbidden_mutations) <= forbidden:
        raise PlanError("forbidden_mutation", f"{path}.forbidden_mutations", f"missing protections: {sorted(required - forbidden)}")
    inputs = text_values(raw.get("inputs"), f"{path}.inputs")
    _ = text_values(raw.get("local_approach"), f"{path}.local_approach")
    role_local_qa = text_values(raw.get("role_local_qa"), f"{path}.role_local_qa")
    escalation_triggers = text_values(
        raw.get("escalation_triggers"),
        f"{path}.escalation_triggers",
    )
    receipt = receipt_binding(raw.get("execution_receipt_binding"), f"{path}.execution_receipt_binding", env)
    if (receipt.role_plan_id, receipt.assignment_id, receipt.role) != (role_plan_id, assignment_id, role):
        raise PlanError("unbound_receipt", f"{path}.execution_receipt_binding", "receipt identity does not bind this role plan")
    return RolePlanBinding(
        role_plan_id,
        path,
        file_sha256(path, "stale_state"),
        assignment_id,
        leaf,
        role,
        requested_fields["read_scope"],
        requested_fields["write_scope"],
        requested_fields["outputs"],
        forbidden_values,
        receipt,
        operating_contract,
        inputs,
        role_local_qa,
        escalation_triggers,
        qa_verification,
    )


def check_plan_files(company_path: Path, role_paths: Sequence[Path], env: Mapping[str, str]) -> PlanCheck:
    company = _parse_company(company_path.resolve(), env)
    bound_assignments: set[str] = set()
    bound_leaves: set[str] = set()
    receipt_refs: set[Path] = set()
    receipt_ids: set[str] = set()
    role_bindings: list[RolePlanBinding] = []
    for path in role_paths:
        binding = _parse_role(path.resolve(), company, env)
        if binding.leaf_id in bound_leaves:
            raise PlanError("duplicate_leaf_ownership", str(path), f"leaf {binding.leaf_id} is already owned")
        if binding.receipt.resolved_ref in receipt_refs or binding.receipt.receipt_id in receipt_ids:
            raise PlanError("duplicate_receipt_binding", str(path), "receipt ref and identity must be unique per role plan")
        bound_assignments.add(binding.assignment_id)
        bound_leaves.add(binding.leaf_id)
        receipt_refs.add(binding.receipt.resolved_ref)
        receipt_ids.add(binding.receipt.receipt_id)
        role_bindings.append(binding)
    if bound_assignments != set(company.assignments):
        raise PlanError("assignment_coverage", "$roles", f"missing assignments: {sorted(set(company.assignments) - bound_assignments)}")
    return PlanCheck(company.id, len(company.assignments), len(role_paths), tuple(role_bindings))
