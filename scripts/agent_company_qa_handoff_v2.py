from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportPrivateUsage=false
import json

from agent_company_deps import JsonValue
from agent_company_qa_handoff_v2_base import (
    MAX_BYTES,
    QaV2Error,
    QaVerificationV2,
    _candidate,
    _criteria,
    _fields,
    _object,
    _references,
    _text,
)
from agent_company_qa_handoff_v2_decision import decisions, readiness
from agent_company_qa_handoff_v2_records import (
    Criterion,
    availability_reference_ids,
    blockers,
    eligible_reference_ids,
    evidence_facts,
    observations,
    risk_matrix,
)


def parse_qa_verification_v2(value: JsonValue | None) -> QaVerificationV2:
    verification = _object(value, "qa_verification")
    encoded = json.dumps(
        verification,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    if len(encoded) > MAX_BYTES:
        raise QaV2Error("qa_verification exceeds 20KB canonical size")
    _fields(
        verification,
        frozenset(
            {
                "format", "candidate", "references", "criteria", "observations",
                "evidence_facts", "risk_boundary_matrix", "decisions", "blockers",
                "readiness",
            }
        ),
        "qa_verification",
    )
    if _text(verification.get("format"), "qa_verification.format") != "agent-company.qa-verification/v0.2":
        raise QaV2Error("qa_verification format is unsupported")
    target = _candidate(verification.get("candidate"), "candidate")
    raw_references = verification.get("references")
    reference_ids = _references(raw_references)
    eligible_ids = eligible_reference_ids(raw_references)
    availability_ids = availability_reference_ids(raw_references)
    raw_criteria = _criteria(verification.get("criteria"))
    criteria = tuple(
        Criterion(identifier, surface, qualifier, states)
        for identifier, _, surface, qualifier, states in raw_criteria
    )
    criterion_ids = tuple(item.identifier for item in criteria)
    facts, fact_ids = evidence_facts(
        verification.get("evidence_facts"),
        frozenset(reference_ids),
    )
    observed = observations(
        verification.get("observations"),
        frozenset(criterion_ids),
        fact_ids,
        frozenset(reference_ids),
    )
    risk_matrix(verification.get("risk_boundary_matrix"), criterion_ids)
    open_ids = blockers(
        verification.get("blockers"),
        frozenset(criterion_ids),
        frozenset(reference_ids),
    )
    statuses = decisions(
        verification.get("decisions"),
        criteria,
        observed,
        target,
        facts,
        eligible_ids,
        availability_ids,
    )
    readiness_value, authorizes = readiness(
        verification.get("readiness"),
        open_ids,
        statuses,
    )
    return QaVerificationV2(
        authorizes,
        readiness_value,
        statuses,
        reference_ids,
        tuple(
            (fact.identifier, fact.provenance, fact.claim_scope)
            for fact in facts
        ),
    )
