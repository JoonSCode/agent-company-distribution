from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportUnnecessaryComparison=false, reportUnusedCallResult=false
from typing import assert_never

from agent_company_planning_invariant_schema import (
    APPLICABLE_PROOF_FIELDS,
    ASSIGNEE_STATES,
    AUTHORITY_CLASSES,
    CYCLE_REVIEWS,
    DEPENDENCY_DISPOSITIONS,
    DEPENDENCY_FIELDS,
    LEAF_FIELDS,
    LINEAGE_FIELDS,
    NOT_APPLICABLE_PROOF_FIELDS,
    RESIDUAL_RISK_AUTHORITIES,
    START_GATE_FIELDS,
    TASK_PACK_BINDINGS,
    DependencyAuthority,
    LeafCriterion,
    PlanningInvariantError,
    PlanningReadiness,
    ProofApplicability,
    ProofCriterion,
    evidence_reference,
    exact_fields,
    member,
    object_value,
    sha256_digest,
    text_list,
    text_value,
)
from agent_company_role_schema import JsonValue


def _start_gate(value: JsonValue | None) -> bool:
    gate = object_value(value, "planning_invariants.start_gate")
    exact_fields(gate, START_GATE_FIELDS, "planning_invariants.start_gate")
    try:
        readiness = PlanningReadiness(text_value(gate.get("planning_readiness"), "planning_invariants.start_gate.planning_readiness"))
    except ValueError as exc:
        raise PlanningInvariantError("planning_invariants.start_gate.planning_readiness cannot authorize leaves") from exc
    if text_value(gate.get("control_timing"), "planning_invariants.start_gate.control_timing") != "before_mutation":
        raise PlanningInvariantError("planning_invariants.start_gate.control_timing must be before_mutation")
    evidence = text_list(gate.get("pre_mutation_evidence"), "planning_invariants.start_gate.pre_mutation_evidence", allow_empty=False)
    for index, reference in enumerate(evidence, start=1):
        evidence_reference(reference, f"planning_invariants.start_gate.pre_mutation_evidence[{index}]")
    disposition = text_value(gate.get("startability_disposition"), "planning_invariants.start_gate.startability_disposition")
    text_value(gate.get("decision_owner"), "planning_invariants.start_gate.decision_owner")
    match readiness:
        case PlanningReadiness.CONDITIONAL:
            if disposition != "bounded_discovery":
                raise PlanningInvariantError("planning_invariants.start_gate.conditional must use bounded_discovery")
            return False
        case PlanningReadiness.READY:
            if disposition != "allowed":
                raise PlanningInvariantError("planning_invariants.start_gate.ready must use allowed")
            return True
        case PlanningReadiness.BLOCKED:
            raise PlanningInvariantError("planning_invariants.start_gate.blocked cannot authorize executable leaves")
        case unreachable:
            assert_never(unreachable)


def _leaves(value: JsonValue | None) -> tuple[LeafCriterion, ...]:
    match value:
        case list() if value:
            leaves: list[LeafCriterion] = []
            leaf_ids: set[str] = set()
            criterion_ids: set[str] = set()
            for index, raw_leaf in enumerate(value, start=1):
                label = f"planning_invariants.executable_leaves[{index}]"
                leaf = object_value(raw_leaf, label)
                exact_fields(leaf, LEAF_FIELDS, label)
                for field in sorted(LEAF_FIELDS - {"dependencies"}):
                    text_value(leaf.get(field), f"{label}.{field}")
                leaf_id, criterion_id = text_value(leaf.get("id"), f"{label}.id"), text_value(leaf.get("criterion_id"), f"{label}.criterion_id")
                if leaf_id in leaf_ids:
                    raise PlanningInvariantError("planning_invariants.executable_leaves.id must be unique")
                if criterion_id in criterion_ids:
                    raise PlanningInvariantError("planning_invariants.executable_leaves.criterion_id must bind one leaf")
                leaf_ids.add(leaf_id)
                criterion_ids.add(criterion_id)
                owner, verifier = text_value(leaf.get("owner"), f"{label}.owner"), text_value(leaf.get("verifier"), f"{label}.verifier")
                if owner == verifier:
                    raise PlanningInvariantError("planning_invariants.executable_leaves.owner must differ from verifier")
                leaves.append(LeafCriterion(leaf_id, criterion_id, text_list(leaf.get("dependencies"), f"{label}.dependencies", allow_empty=True), owner, verifier))
            return tuple(leaves)
        case str() | int() | float() | bool() | None | dict() | list():
            raise PlanningInvariantError("planning_invariants.executable_leaves must be a non-empty list")
        case unreachable:
            assert_never(unreachable)


def _dependencies(value: JsonValue | None) -> tuple[DependencyAuthority, ...]:
    match value:
        case list():
            dependencies: list[DependencyAuthority] = []
            identifiers: set[str] = set()
            for index, raw_dependency in enumerate(value, start=1):
                label = f"planning_invariants.dependency_authority[{index}]"
                dependency = object_value(raw_dependency, label)
                exact_fields(dependency, DEPENDENCY_FIELDS, label)
                identifier = text_value(dependency.get("edge_id"), f"{label}.edge_id")
                if identifier in identifiers:
                    raise PlanningInvariantError("planning_invariants.dependency_authority.edge_id must be unique")
                identifiers.add(identifier)
                for field, allowed in (
                    ("surface_disposition", DEPENDENCY_DISPOSITIONS),
                    ("cycle_review", CYCLE_REVIEWS),
                    ("authority_class", AUTHORITY_CLASSES),
                    ("assignee_state", ASSIGNEE_STATES),
                    ("residual_risk_authority", RESIDUAL_RISK_AUTHORITIES),
                ):
                    member(text_value(dependency.get(field), f"{label}.{field}"), allowed, f"{label}.{field}")
                for field in ("evidence_ref", "recheck_trigger", "fallback"):
                    evidence_reference(dependency.get(field), f"{label}.{field}")
                dependencies.append(
                    DependencyAuthority(
                        identifier,
                        text_value(dependency.get("surface_disposition"), f"{label}.surface_disposition"),
                        text_value(dependency.get("cycle_review"), f"{label}.cycle_review"),
                        text_value(dependency.get("assignee_state"), f"{label}.assignee_state"),
                    )
                )
            return tuple(dependencies)
        case str() | int() | float() | bool() | None | dict():
            raise PlanningInvariantError("planning_invariants.dependency_authority must be a list")
        case unreachable:
            assert_never(unreachable)


def _proof_surfaces(value: JsonValue | None) -> tuple[ProofCriterion, ...]:
    match value:
        case list() if value:
            proofs: list[ProofCriterion] = []
            criteria: set[str] = set()
            for index, raw_surface in enumerate(value, start=1):
                label = f"planning_invariants.proof_surfaces[{index}]"
                surface = object_value(raw_surface, label)
                try:
                    applicability = ProofApplicability(text_value(surface.get("applicability"), f"{label}.applicability"))
                except ValueError as exc:
                    raise PlanningInvariantError(f"{label}.applicability is unsupported") from exc
                match applicability:
                    case ProofApplicability.APPLICABLE:
                        exact_fields(surface, APPLICABLE_PROOF_FIELDS, label)
                        lineage = object_value(surface.get("candidate_lineage"), f"{label}.candidate_lineage")
                        exact_fields(lineage, LINEAGE_FIELDS, f"{label}.candidate_lineage")
                        for field in sorted(LINEAGE_FIELDS):
                            sha256_digest(lineage.get(field), f"{label}.candidate_lineage.{field}")
                        for field in ("criterion_id", "surface", "verifier", "binary_observable"):
                            text_value(surface.get(field), f"{label}.{field}")
                        verifier: str | None = text_value(surface.get("verifier"), f"{label}.verifier")
                    case ProofApplicability.NOT_APPLICABLE:
                        exact_fields(surface, NOT_APPLICABLE_PROOF_FIELDS, label)
                        for field in ("criterion_id", "surface", "reason", "decision_owner"):
                            text_value(surface.get(field), f"{label}.{field}")
                        evidence_reference(surface.get("evidence_ref"), f"{label}.evidence_ref")
                        verifier = None
                    case unreachable:
                        assert_never(unreachable)
                criterion_id = text_value(surface.get("criterion_id"), f"{label}.criterion_id")
                if criterion_id in criteria:
                    raise PlanningInvariantError("planning_invariants.proof_surfaces.criterion_id must bind one surface")
                criteria.add(criterion_id)
                proofs.append(ProofCriterion(criterion_id, verifier))
            return tuple(proofs)
        case str() | int() | float() | bool() | None | dict() | list():
            raise PlanningInvariantError("planning_invariants.proof_surfaces must be a non-empty list")
        case unreachable:
            assert_never(unreachable)


def parse_planning_invariants(value: JsonValue | None) -> None:
    """Reject incomplete Planning controls before they can authorize a handoff."""
    invariants = object_value(value, "planning_invariants")
    exact_fields(invariants, frozenset({"start_gate", "executable_leaves", "dependency_authority", "proof_surfaces"}), "planning_invariants")
    execution_authorized = _start_gate(invariants.get("start_gate"))
    leaves = _leaves(invariants.get("executable_leaves"))
    required_edges = frozenset(dependency for leaf in leaves for dependency in leaf.dependencies)
    dependencies = _dependencies(invariants.get("dependency_authority"))
    dependency_ids = frozenset(dependency.edge_id for dependency in dependencies)
    if not required_edges <= dependency_ids:
        raise PlanningInvariantError("planning_invariants.dependency_authority lacks an executable leaf dependency")
    if execution_authorized:
        for dependency in dependencies:
            if dependency.edge_id in required_edges and (dependency.surface_disposition, dependency.cycle_review, dependency.assignee_state) != ("satisfied", "no_cycle", "assigned"):
                raise PlanningInvariantError("planning_invariants.dependency_authority required edge is not execution-ready")
    proofs = _proof_surfaces(invariants.get("proof_surfaces"))
    proof_criteria = frozenset(proof.criterion_id for proof in proofs)
    required_criteria = frozenset(leaf.criterion_id for leaf in leaves)
    if not proof_criteria <= required_criteria:
        raise PlanningInvariantError("planning_invariants.proof_surfaces contains an unrelated criterion_id")
    if required_criteria != proof_criteria:
        raise PlanningInvariantError("planning_invariants.proof_surfaces lacks an executable leaf criterion_id")
    proof_by_criterion = {proof.criterion_id: proof for proof in proofs}
    for leaf in leaves:
        proof_verifier = proof_by_criterion[leaf.criterion_id].verifier
        if proof_verifier is not None and proof_verifier != leaf.verifier:
            raise PlanningInvariantError("planning_invariants.proof_surfaces verifier must match executable leaf verifier")


def validate_planning_invariants(
    value: JsonValue | None,
    *,
    task_type: str,
    task_pack_id: str,
) -> None:
    """Validate Planning evidence only for a registered task-type/task-pack pair."""
    if (task_type, task_pack_id) not in TASK_PACK_BINDINGS:
        raise PlanningInvariantError("planning task_type and task_pack_id must be a registered pair")
    parse_planning_invariants(value)
