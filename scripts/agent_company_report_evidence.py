from __future__ import annotations

import hashlib
from pathlib import Path

from agent_company_deps import JsonValue
from agent_company_job_policy import PolicyError, string_list
from agent_company_privacy import PrivacyError, reject_sensitive


def project_evidence_refs(values: list[str], label: str) -> list[str]:
    projected: list[str] = []
    for value in values:
        if "://" in value and not value.startswith("file://"):
            projected.append(value)
            continue
        if value.startswith("file://"):
            raise PolicyError(f"{label} must not expose a raw file URI")
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            raise PolicyError(f"{label} is not a local evidence file: {value}")
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise PolicyError(f"cannot read {label}: {value}") from exc
        projected.append(f"sha256://evidence/{digest}")
    return list(dict.fromkeys(projected))


def require_safe_report(report: dict[str, JsonValue]) -> dict[str, JsonValue]:
    try:
        reject_sensitive(report)
    except PrivacyError as exc:
        raise PolicyError("CEO report failed privacy validation") from exc
    return report


def project_user_decisions(gate: JsonValue) -> list[str]:
    if not isinstance(gate, dict) or gate.get("status") != "approved":
        return []
    packet_refs = project_evidence_refs(
        string_list(gate.get("packet_refs"), "packet_refs"),
        "Uigwe packet",
    )
    decisions = [f"Approved Uigwe packet: {ref}" for ref in packet_refs]
    decision_ref = gate.get("decision_ref")
    if isinstance(decision_ref, str) and decision_ref:
        projected = project_evidence_refs([decision_ref], "Uigwe decision")[0]
        decisions.append(f"Decision-bound Uigwe resolution: {projected}")
    return decisions
