from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportPrivateUsage=false
from agent_company_deps import JsonValue
from agent_company_qa_handoff_v2_base import (
    QaV2Error,
    _fields,
    _list,
    _object,
    _text,
    _texts,
)
from agent_company_qa_handoff_v2_records import (
    Criterion,
    EvidenceFact,
    Observation,
)


def _terminal_proof_qualifies(
    observation: Observation,
    facts: dict[str, EvidenceFact],
    eligible_reference_ids: frozenset[str],
) -> bool:
    if not observation.fact_ids or not observation.reference_ids:
        return False
    supporting: list[EvidenceFact] = []
    for identifier in observation.fact_ids:
        fact = facts.get(identifier)
        if fact is None:
            return False
        supporting.append(fact)
    if any(
        fact.provenance != "direct"
        or not fact.reference_ids
        or not frozenset(fact.reference_ids) <= eligible_reference_ids
        for fact in supporting
    ):
        return False
    fact_references = frozenset(
        reference_id
        for fact in supporting
        for reference_id in fact.reference_ids
    )
    return frozenset(observation.reference_ids) == fact_references


def _qualifies(
    observation: Observation,
    criterion: Criterion,
    target: dict[str, JsonValue],
    status: str,
    facts: dict[str, EvidenceFact],
    eligible_reference_ids: frozenset[str],
) -> bool:
    return (
        observation.provenance == "direct"
        and observation.candidate == target
        and target.get("binding") == "exact"
        and observation.surface == criterion.surface
        and observation.qualifier == criterion.qualifier
        and observation.coverage == "full"
        and observation.availability == "available"
        and observation.result == status
        and set(criterion.permission_states) <= set(observation.permission_states)
        and _terminal_proof_qualifies(
            observation,
            facts,
            eligible_reference_ids,
        )
    )


def _blocked_qualifies(
    observation: Observation,
    criterion: Criterion,
    target: dict[str, JsonValue],
    facts: dict[str, EvidenceFact],
    availability_reference_ids: frozenset[str],
) -> bool:
    references = frozenset(observation.reference_ids)
    if not references or not references <= availability_reference_ids:
        return False
    supporting = tuple(
        facts[identifier]
        for identifier in observation.fact_ids
        if identifier in facts
    )
    if observation.fact_ids and len(supporting) != len(observation.fact_ids):
        return False
    if supporting:
        if any(
            fact.provenance != "direct"
            or not fact.reference_ids
            or not frozenset(fact.reference_ids) <= availability_reference_ids
            for fact in supporting
        ):
            return False
        fact_references = frozenset(
            reference_id
            for fact in supporting
            for reference_id in fact.reference_ids
        )
        if references != fact_references:
            return False
    return (
        observation.provenance == "direct"
        and observation.candidate == target
        and target.get("binding") == "exact"
        and observation.surface == criterion.surface
        and observation.qualifier == criterion.qualifier
        and observation.availability == "unavailable"
    )


def decisions(
    value: JsonValue | None,
    criteria: tuple[Criterion, ...],
    observations: tuple[Observation, ...],
    target: dict[str, JsonValue],
    evidence_facts: tuple[EvidenceFact, ...],
    eligible_reference_ids: frozenset[str],
    availability_reference_ids: frozenset[str],
) -> tuple[tuple[str, str], ...]:
    by_id = {item.identifier: item for item in observations}
    by_criterion = {item.identifier: item for item in criteria}
    facts_by_id = {item.identifier: item for item in evidence_facts}
    result: list[tuple[str, str]] = []
    expected = frozenset({"criterion_id", "status", "observation_ids"})
    for index, raw in enumerate(_list(value, "decisions")):
        item = _object(raw, f"decisions[{index}]")
        _fields(item, expected, f"decisions[{index}]")
        criterion_id = _text(item.get("criterion_id"), f"decisions[{index}].criterion_id")
        criterion = by_criterion.get(criterion_id)
        if criterion is None:
            raise QaV2Error("decision references unknown criterion ID")
        status = _text(item.get("status"), f"decisions[{index}].status")
        if status not in {"passed", "failed", "blocked", "unverified"}:
            raise QaV2Error("decision status is unsupported")
        observation_ids = _texts(item.get("observation_ids"), f"decisions[{index}].observation_ids")
        selected: list[Observation] = []
        for identifier in observation_ids:
            observation = by_id.get(identifier)
            if observation is None or observation.criterion_id != criterion_id:
                raise QaV2Error("decision references unknown or cross-criterion observation ID")
            selected.append(observation)
        if status in {"passed", "failed"}:
            if not any(
                _qualifies(
                    observation,
                    criterion,
                    target,
                    status,
                    facts_by_id,
                    eligible_reference_ids,
                )
                for observation in selected
            ):
                matching_permission = any(
                    observation.provenance == "direct"
                    and observation.candidate == target
                    and observation.surface == criterion.surface
                    and observation.qualifier == criterion.qualifier
                    and observation.coverage == "full"
                    and observation.availability == "available"
                    and observation.result == status
                    and not set(criterion.permission_states) <= set(observation.permission_states)
                    and _terminal_proof_qualifies(
                        observation,
                        facts_by_id,
                        eligible_reference_ids,
                    )
                    for observation in selected
                )
                if matching_permission:
                    raise QaV2Error("permission lifecycle coverage is incomplete")
                raise QaV2Error(
                    f"reported or partial evidence cannot become {status}; requires direct full coverage exact candidate matching-surface observation and non-empty direct supporting facts with eligible exact references in causal closure"
                )
        elif status == "blocked":
            if not any(
                _blocked_qualifies(
                    observation,
                    criterion,
                    target,
                    facts_by_id,
                    availability_reference_ids,
                )
                for observation in selected
            ):
                raise QaV2Error(
                    "blocked criterion requires a direct unavailable matching surface, qualifier, and exact candidate lineage with a captured availability reference"
                )
        elif any(
            _blocked_qualifies(
                observation,
                criterion,
                target,
                facts_by_id,
                availability_reference_ids,
            )
            for observation in selected
        ):
            raise QaV2Error("unavailable matching surface must be blocked")
        elif any(
            _qualifies(
                observation,
                criterion,
                target,
                observation.result,
                facts_by_id,
                eligible_reference_ids,
            )
            for observation in selected
        ):
            raise QaV2Error("unverified criterion cannot discard a complete terminal observation")
        result.append((criterion_id, status))
    expected_ids = tuple(item.identifier for item in criteria)
    if tuple(item[0] for item in result) != expected_ids:
        raise QaV2Error("decisions must cover every criterion exactly once in order")
    return tuple(result)


def readiness(
    value: JsonValue | None,
    open_blocker_ids: tuple[str, ...],
    statuses: tuple[tuple[str, str], ...],
) -> tuple[str, bool]:
    item = _object(value, "readiness")
    _fields(item, frozenset({"decision", "open_blocker_ids"}), "readiness")
    decision = _text(item.get("decision"), "readiness.decision")
    if decision not in {"recommend", "reject"}:
        raise QaV2Error("readiness decision must be recommend or reject")
    declared = _texts(item.get("open_blocker_ids"), "readiness.open_blocker_ids")
    if declared != open_blocker_ids:
        raise QaV2Error("readiness open blocker IDs differ from blocker ledger")
    if open_blocker_ids and decision == "recommend":
        raise QaV2Error("open blocker forbids recommend readiness")
    all_passed = all(status == "passed" for _, status in statuses)
    if decision == "recommend" and not all_passed:
        raise QaV2Error("recommend readiness requires every criterion to pass")
    return decision, decision == "recommend" and all_passed and not open_blocker_ids
