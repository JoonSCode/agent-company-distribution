from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportPrivateUsage=false, reportUnusedCallResult=false
from dataclasses import dataclass

from agent_company_deps import JsonValue
from agent_company_qa_handoff_v2_base import (
    QaV2Error,
    _candidate,
    _fields,
    _list,
    _object,
    _text,
    _texts,
)


@dataclass(frozen=True, slots=True)
class Criterion:
    identifier: str
    surface: str
    qualifier: str
    permission_states: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceFact:
    identifier: str
    provenance: str
    claim_scope: str
    reference_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Observation:
    identifier: str
    criterion_id: str
    provenance: str
    candidate: dict[str, JsonValue]
    surface: str
    qualifier: str
    coverage: str
    availability: str
    result: str
    permission_states: tuple[str, ...]
    fact_ids: tuple[str, ...]
    reference_ids: tuple[str, ...]


def eligible_reference_ids(value: JsonValue | None) -> frozenset[str]:
    eligible: set[str] = set()
    for index, raw in enumerate(_list(value, "references")):
        item = _object(raw, f"references[{index}]")
        if item.get("resolution") == "exact":
            eligible.add(_text(item.get("id"), f"references[{index}].id"))
    return frozenset(eligible)


def availability_reference_ids(value: JsonValue | None) -> frozenset[str]:
    eligible: set[str] = set()
    for index, raw in enumerate(_list(value, "references")):
        item = _object(raw, f"references[{index}]")
        if item.get("resolution") in {"exact", "unresolved"}:
            eligible.add(_text(item.get("id"), f"references[{index}].id"))
    return frozenset(eligible)


def evidence_facts(
    value: JsonValue | None,
    reference_ids: frozenset[str],
) -> tuple[tuple[EvidenceFact, ...], frozenset[str]]:
    facts: list[EvidenceFact] = []
    for index, raw in enumerate(_list(value, "evidence_facts")):
        item = _object(raw, f"evidence_facts[{index}]")
        _fields(
            item,
            frozenset({"id", "provenance", "claim_scope", "statement", "ref_ids"}),
            f"evidence_facts[{index}]",
        )
        identifier = _text(item.get("id"), f"evidence_facts[{index}].id")
        provenance = _text(item.get("provenance"), f"evidence_facts[{index}].provenance")
        if provenance not in {"direct", "reported"}:
            raise QaV2Error("evidence fact provenance must be direct or reported")
        scope = _text(item.get("claim_scope"), f"evidence_facts[{index}].claim_scope")
        _text(item.get("statement"), f"evidence_facts[{index}].statement")
        refs = _texts(item.get("ref_ids"), f"evidence_facts[{index}].ref_ids")
        if not frozenset(refs) <= reference_ids:
            raise QaV2Error("evidence fact references unknown normalized reference IDs")
        facts.append(EvidenceFact(identifier, provenance, scope, refs))
    identifiers = frozenset(item.identifier for item in facts)
    if len(identifiers) != len(facts):
        raise QaV2Error("evidence fact IDs must be unique")
    return tuple(facts), identifiers


def observations(
    value: JsonValue | None,
    criterion_ids: frozenset[str],
    fact_ids: frozenset[str],
    reference_ids: frozenset[str],
) -> tuple[Observation, ...]:
    result: list[Observation] = []
    expected = frozenset(
        {
            "id", "criterion_id", "provenance", "candidate", "surface",
            "qualifier", "coverage", "availability", "result",
            "permission_states", "fact_ids", "ref_ids",
        }
    )
    for index, raw in enumerate(_list(value, "observations")):
        item = _object(raw, f"observations[{index}]")
        _fields(item, expected, f"observations[{index}]")
        identifier = _text(item.get("id"), f"observations[{index}].id")
        criterion_id = _text(item.get("criterion_id"), f"observations[{index}].criterion_id")
        if criterion_id not in criterion_ids:
            raise QaV2Error("observation references unknown criterion ID")
        provenance = _text(item.get("provenance"), f"observations[{index}].provenance")
        if provenance not in {"direct", "reported"}:
            raise QaV2Error("observation provenance must be direct or reported")
        candidate = _candidate(item.get("candidate"), f"observations[{index}].candidate")
        surface = _text(item.get("surface"), f"observations[{index}].surface")
        qualifier = _text(item.get("qualifier"), f"observations[{index}].qualifier")
        coverage = _text(item.get("coverage"), f"observations[{index}].coverage")
        availability = _text(item.get("availability"), f"observations[{index}].availability")
        observed_result = _text(item.get("result"), f"observations[{index}].result")
        if coverage not in {"full", "partial"} or availability not in {"available", "unavailable"}:
            raise QaV2Error("observation coverage or availability is unsupported")
        if observed_result not in {"passed", "failed", "unobserved"}:
            raise QaV2Error("observation result is unsupported")
        if availability == "unavailable" and observed_result != "unobserved":
            raise QaV2Error("unavailable surface must remain unobserved")
        states = _texts(item.get("permission_states"), f"observations[{index}].permission_states")
        facts = _texts(item.get("fact_ids"), f"observations[{index}].fact_ids")
        refs = _texts(item.get("ref_ids"), f"observations[{index}].ref_ids")
        if not frozenset(facts) <= fact_ids or not frozenset(refs) <= reference_ids:
            raise QaV2Error("observation references unknown fact or normalized reference ID")
        result.append(
            Observation(
                identifier, criterion_id, provenance, candidate, surface,
                qualifier, coverage, availability, observed_result, states,
                facts, refs,
            )
        )
    if len({item.identifier for item in result}) != len(result):
        raise QaV2Error("observation IDs must be unique")
    return tuple(result)


def risk_matrix(value: JsonValue | None, criterion_ids: tuple[str, ...]) -> None:
    observed: list[str] = []
    expected = frozenset(
        {"criterion_id", "risk_id", "boundary_id", "impact", "non_substitute_surface"}
    )
    for index, raw in enumerate(_list(value, "risk_boundary_matrix")):
        item = _object(raw, f"risk_boundary_matrix[{index}]")
        _fields(item, expected, f"risk_boundary_matrix[{index}]")
        observed.append(_text(item.get("criterion_id"), f"risk_boundary_matrix[{index}].criterion_id"))
        _text(item.get("risk_id"), f"risk_boundary_matrix[{index}].risk_id")
        _text(item.get("boundary_id"), f"risk_boundary_matrix[{index}].boundary_id")
        impact = _text(item.get("impact"), f"risk_boundary_matrix[{index}].impact")
        if impact not in {"low", "medium", "high", "critical"}:
            raise QaV2Error("risk impact is unsupported")
        _text(item.get("non_substitute_surface"), f"risk_boundary_matrix[{index}].non_substitute_surface")
    if tuple(observed) != criterion_ids:
        raise QaV2Error("risk boundary matrix must cover every criterion exactly once in order")


def blockers(
    value: JsonValue | None,
    criterion_ids: frozenset[str],
    reference_ids: frozenset[str],
) -> tuple[str, ...]:
    identifiers: list[str] = []
    open_ids: list[str] = []
    expected = frozenset({"id", "criterion_id", "status", "owner", "next_check", "ref_ids"})
    for index, raw in enumerate(_list(value, "blockers")):
        item = _object(raw, f"blockers[{index}]")
        _fields(item, expected, f"blockers[{index}]")
        identifier = _text(item.get("id"), f"blockers[{index}].id")
        identifiers.append(identifier)
        if _text(item.get("criterion_id"), f"blockers[{index}].criterion_id") not in criterion_ids:
            raise QaV2Error("blocker references unknown criterion ID")
        status = _text(item.get("status"), f"blockers[{index}].status")
        if status == "open":
            open_ids.append(identifier)
        elif status != "resolved":
            raise QaV2Error("blocker status must be open or resolved")
        _text(item.get("owner"), f"blockers[{index}].owner")
        _text(item.get("next_check"), f"blockers[{index}].next_check")
        refs = frozenset(_texts(item.get("ref_ids"), f"blockers[{index}].ref_ids"))
        if not refs <= reference_ids:
            raise QaV2Error("blocker references unknown normalized reference ID")
    if len(identifiers) != len(set(identifiers)):
        raise QaV2Error("blocker IDs must be unique")
    return tuple(open_ids)
