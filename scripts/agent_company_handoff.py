#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/agent_company_handoff.py import handoff.json --json
# 3. Or run with system Python when stdlib-only execution is preferred:
#      python3 scripts/agent_company_handoff.py import handoff.json --json
# ──────────────────

from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import argparse
import json
import sys
from pathlib import Path
from typing import assert_never

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

from agent_company_deps import JsonValue
from agent_company_handoff_parser import (
    FORMAT,
    ROLES,
    HandoffError,
    json_object,
    parse_handoff,
    text_field,
)
from agent_company_handoff_parser import SURFACES as HANDOFF_SURFACES
from agent_company_handoff_role_evidence import (
    INTEGRATED_ROLES,
    RoleEvidenceError,
    blocked_role_evidence,
    completed_role_evidence,
    validate_role_evidence,
)
from agent_company_handoff_version_validation import (
    EXECUTION_HANDOFF_VERSION,
    QA_EXECUTION_HANDOFF_VERSION,
)
from agent_company_handoff_version_validation import (
    LEGACY_EXECUTION_HANDOFF_VERSION as HANDOFF_LEGACY_EXECUTION_HANDOFF_VERSION,
)
from agent_company_knowledge_context import (
    issue_default_context,
    validate_knowledge_context,
)
from agent_company_knowledge_receipt import build_default_receipt
from agent_company_operating_contracts import operating_contract_payload

LEGACY_EXECUTION_HANDOFF_VERSION = HANDOFF_LEGACY_EXECUTION_HANDOFF_VERSION
SURFACES = HANDOFF_SURFACES


def default_qa_verification() -> dict[str, JsonValue]:
    return {
        "format": "agent-company.qa-verification/v0.2",
        "candidate": {
            "binding": "unknown",
            "reason": "The generated template is not bound to release-candidate bytes.",
        },
        "references": [
            {
                "id": "pending-observation",
                "resolution": "unresolved",
                "ref": "artifact://qa/pending-observation",
                "reason": "No direct observation has been executed.",
            }
        ],
        "criteria": [
            {
                "id": "named-release-criterion",
                "kind": "acceptance",
                "claim": "The named release criterion holds on its required surface.",
                "required_surface": "automated",
                "required_qualifier": "automated",
                "required_permission_states": [],
                "expected_observable": "The named binary assertion reaches a terminal result.",
            }
        ],
        "observations": [],
        "evidence_facts": [],
        "risk_boundary_matrix": [
            {
                "criterion_id": "named-release-criterion",
                "risk_id": "unobserved-release-regression",
                "boundary_id": "matching-surface-only",
                "impact": "high",
                "non_substitute_surface": "worker completion report",
            }
        ],
        "decisions": [
            {
                "criterion_id": "named-release-criterion",
                "status": "unverified",
                "observation_ids": [],
            }
        ],
        "blockers": [
            {
                "id": "matching-surface-observation-pending",
                "criterion_id": "named-release-criterion",
                "status": "open",
                "owner": "qa-release",
                "next_check": "Bind the exact candidate and run the declared matching-surface check.",
                "ref_ids": ["pending-observation"],
            }
        ],
        "readiness": {
            "decision": "reject",
            "open_blocker_ids": ["matching-surface-observation-pending"],
        },
    }


def default_handoff(
    role: str,
    objective: str,
    *,
    knowledge_context: JsonValue | None = None,
    knowledge_receipt: JsonValue | None = None,
    qa_verification: JsonValue | None = None,
    role_evidence: JsonValue | None = None,
    role_evidence_context_binding: JsonValue | None = None,
) -> dict[str, JsonValue]:
    if role not in ROLES:
        raise HandoffError("malformed_input", "unsupported handoff role")
    payload: dict[str, JsonValue] = {
        "format": FORMAT,
        "execution_handoff_version": (
            QA_EXECUTION_HANDOFF_VERSION
            if role == "qa-release"
            else EXECUTION_HANDOFF_VERSION
        ),
        "role": role,
        "objective": objective,
        "scope": {
            "allowed_paths": ["scripts/test_agent_company_standalone.py"],
            "read_refs": ["agent-company.deps.json"],
            "write_refs": [],
            "stop_condition": "return bounded evidence only",
        },
        "known": ["Company evidence preserves user authority, Orca permissions and independent acceptance."],
        "inferred": [],
        "unknown": [],
        "actions_taken": ["exported bounded handoff"],
        "artifacts": [],
        "risks": [],
        "next_recommended_surface": "company-lead",
        "forbidden_claims": [
            "final verification authority",
            "gate approval authority",
            "override user authority",
            "self-approve final verification",
        ],
    }
    contract = operating_contract_payload(role)
    if contract is not None:
        payload["operating_contract_binding"] = contract
    context = knowledge_context or issue_default_context(role, objective)
    parsed_context = validate_knowledge_context(role, objective, context)
    payload["knowledge_context_binding"] = context
    payload["knowledge_usage_receipt"] = (
        knowledge_receipt
        if knowledge_receipt is not None
        else build_default_receipt(
            role,
            objective,
            context=context,
        )
    )
    if role == "qa-release":
        payload["qa_verification"] = (
            default_qa_verification()
            if qa_verification is None
            else qa_verification
        )
    elif qa_verification is not None:
        raise HandoffError(
            "malformed_input",
            "qa_verification is unsupported outside qa-release",
        )
    if role in INTEGRATED_ROLES:
        envelope = (
            blocked_role_evidence(
                parsed_context,
                role_evidence_context_binding,
            )
            if role_evidence is None
            else completed_role_evidence(
                parsed_context,
                role_evidence,
                role_evidence_context_binding,
            )
        )
        try:
            validate_role_evidence(
                role=role,
                context=parsed_context,
                value=envelope,
            )
        except RoleEvidenceError as exc:
            raise HandoffError("malformed_input", str(exc)) from exc
        payload["role_evidence"] = envelope
    elif role_evidence is not None or role_evidence_context_binding is not None:
        raise HandoffError(
            "malformed_input",
            f"role_evidence is unsupported for {role}",
        )
    return payload


def default_assignment_handoff(
    assignment: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    role = text_field(assignment, "role")
    objective = text_field(assignment, "objective")
    context = json_object(
        assignment.get("knowledge_context_binding"),
        "knowledge_context_binding",
    )
    return default_handoff(
        role,
        objective,
        knowledge_context=context,
        qa_verification=assignment.get("qa_verification"),
        role_evidence_context_binding=assignment.get(
            "role_evidence_context_binding"
        ),
    )


def write_handoff(path: Path, payload: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agent_company_handoff.py")
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("path", type=Path)
    export.add_argument("--role", default="development")
    export.add_argument("--objective", default="bounded Agent Company handoff")
    load = sub.add_parser("import")
    load.add_argument("path", type=Path)
    load.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        match str(args.command):
            case "export":
                write_handoff(args.path, default_handoff(args.role, args.objective))
                print(json.dumps({"status": "ok", "path": str(args.path)}, sort_keys=True))
            case "import":
                payload = parse_handoff(args.path)
                if args.json:
                    print(json.dumps({"status": "ok", "handoff": payload}, indent=2, sort_keys=True))
                else:
                    print("handoff: ok")
            case str() as unsupported:
                raise HandoffError("malformed_input", f"unsupported command: {unsupported}")
            case unreachable:
                assert_never(unreachable)
    except HandoffError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
