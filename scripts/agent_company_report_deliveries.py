from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
from dataclasses import dataclass

import agent_company_report_evidence as evidence
import agent_company_report_status as status
from agent_company_deps import JsonValue
from agent_company_handoff_validation import HandoffValidation, validate_worker_handoff
from agent_company_job_policy import PolicyError, string_list, text
from agent_company_knowledge_verification import KnowledgeVerificationBinding
from agent_company_report_verification import VerificationEvidence


@dataclass(frozen=True, slots=True)
class DeliveryProjection:
    deliveries: tuple[dict[str, JsonValue], ...]
    claims: tuple[dict[str, JsonValue], ...]
    states: tuple[str, ...]
    risks: tuple[str, ...]


def _knowledge_matches(
    handoff: HandoffValidation,
    knowledge: KnowledgeVerificationBinding,
) -> bool:
    actual = (
        handoff.context_id,
        handoff.knowledge_receipt_id,
        handoff.required_reference_ids,
    )
    expected = (
        knowledge.context_id,
        knowledge.knowledge_receipt_id,
        knowledge.required_reference_ids,
    )
    if actual != expected:
        raise PolicyError("knowledge verification does not bind the worker handoff")
    return True


def project_deliveries(
    assignments: list[dict[str, JsonValue]],
    terminals: dict[str, dict[str, JsonValue]],
    verification: VerificationEvidence,
    selected_roles: list[str],
) -> DeliveryProjection:
    deliveries: list[dict[str, JsonValue]] = []
    claims: list[dict[str, JsonValue]] = []
    states: list[str] = []
    risks: list[str] = []
    assignment_roles = [text(item.get("role"), "assignment role") for item in assignments]
    verified = verification.authorizes_verified_projection
    for assignment in assignments:
        worker_id = text(assignment.get("worker_id"), "worker_id")
        receipt = terminals.get(worker_id)
        if receipt is None:
            delivery_state = "unverified"
            worker_ref = f"unassigned:{worker_id}"
            summary = f"No terminal Core receipt for {worker_id}."
            evidence_refs: list[str] = []
        else:
            terminal_status = status.enum_value(
                status.TerminalStatus,
                receipt.get("terminal_status"),
                "terminal_status",
            )
            delivery_state = status.terminal_state(terminal_status)
            worker_ref = text(receipt.get("backend_worker_ref"), "backend_worker_ref")
            summary = text(receipt.get("summary"), "receipt summary")
            evidence_refs = evidence.project_evidence_refs(
                string_list(receipt.get("evidence_refs"), "receipt evidence_refs"),
                "receipt evidence",
            )
            if terminal_status is status.TerminalStatus.COMPLETED:
                handoff = validate_worker_handoff(assignment, receipt)
                if not handoff.valid:
                    delivery_state = "unverified"
                    summary = (
                        f"Completed Core receipt for {worker_id} has invalid "
                        f"worker handoff: {handoff.reason}"
                    )
                elif handoff.outcome == "blocked":
                    delivery_state = "blocked"
                    summary = (
                        f"Completed Core receipt for {worker_id} carries "
                        "a blocked handoff outcome."
                    )
                elif verified and handoff.assignment_bound:
                    knowledge = verification.knowledge_verified.get(worker_id)
                    if knowledge is not None and _knowledge_matches(handoff, knowledge):
                        delivery_state = "verified"
                if handoff.model_routing_receipt is not None:
                    routing = handoff.model_routing_receipt
                    evidence_refs = list(dict.fromkeys([
                        *evidence_refs,
                        *evidence.project_evidence_refs(
                            [routing.reference],
                            "model routing receipt",
                        ),
                        f"sha256://model-routing-receipt/{routing.sha256}",
                    ]))
            if delivery_state == "verified":
                evidence_refs = list(dict.fromkeys([
                    *evidence_refs,
                    *verification.refs,
                ]))
        states.append(delivery_state)
        if delivery_state in {"failed", "blocked", "unverified"}:
            risks.append(summary)
        delivery: dict[str, JsonValue] = {
            "role": text(assignment.get("role"), "role"),
            "worker_ref": worker_ref,
            "state": delivery_state,
            "summary": summary,
            "evidence_refs": list(evidence_refs),
        }
        deliveries.append(delivery)
        claims.append({
            "claim": summary,
            "state": delivery_state,
            "evidence_refs": list(evidence_refs),
        })
    for role in selected_roles:
        if role in assignment_roles:
            continue
        summary = f"Selected role {role} has no delegation assignment."
        deliveries.append({
            "role": role,
            "worker_ref": f"unassigned-role:{role}",
            "state": "unverified",
            "summary": summary,
            "evidence_refs": [],
        })
        claims.append({
            "claim": summary,
            "state": "unverified",
            "evidence_refs": [],
        })
        states.append("unverified")
        risks.append(summary)
    return DeliveryProjection(
        tuple(deliveries),
        tuple(claims),
        tuple(states),
        tuple(risks),
    )
