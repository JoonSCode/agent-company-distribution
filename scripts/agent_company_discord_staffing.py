from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final, NoReturn

from agent_company_eval_types import (
    EvalContractError,
    JsonObject,
    boolean_value,
    canonical_sha256,
    exact_fields,
    load_object,
    object_value,
    string_list,
    text_value,
)


CORE_FIELDS: Final = frozenset({
    "format", "authority", "task_class", "risk_class", "verification_class",
    "requires_approval", "controller", "implementer", "reviewer", "shadow",
    "decision_sha256",
})
CONTROLLER_FIELDS: Final = frozenset({"slot", "function", "can_mutate"})
IMPLEMENTER_FIELDS: Final = frozenset({"slot", "model", "sandbox", "model_immutable_per_run"})
REVIEWER_FIELDS: Final = frozenset({"slot", "model", "sandbox", "fresh_run_required"})
SHADOW_FIELDS: Final = frozenset({"slot", "model", "sandbox", "state", "canonical_authority"})
POLICY_FIELDS: Final = frozenset({
    "format", "authority", "core_decision_format", "assignments",
    "forbidden_overrides", "promotion",
})
FORBIDDEN: Final = frozenset({
    "selected_route", "model", "sandbox", "approval_gate", "execution_scope",
    "lease", "review_verdict", "completion_status",
})
ASSIGNMENT_FIELDS: Final = {
    "terra": frozenset({"company_role", "function", "may_change_core_decision", "may_modify_code"}),
    "luna": frozenset({"company_role", "function", "authority"}),
    "sol": frozenset({"company_role", "function", "sandbox", "authority"}),
    "antigravity": frozenset({"company_role", "function", "sandbox", "state", "canonical_authority"}),
}
PROMOTION_FIELDS: Final = frozenset({
    "default_state", "automatic_promotion", "requires_repeated_task_class_evidence",
    "requires_fresh_independent_review", "requires_explicit_approval",
})
EXPECTED_ASSIGNMENTS: Final[JsonObject] = {
    "terra": {"company_role": "founder", "function": "controller_projection", "may_change_core_decision": False, "may_modify_code": False},
    "luna": {"company_role": "development", "function": "implementation_worker", "authority": "evidence_only"},
    "sol": {"company_role": "qa-release", "function": "independent_reviewer", "sandbox": "read-only", "authority": "approval_recommendation_only"},
    "antigravity": {"company_role": None, "function": "shadow_second_opinion", "sandbox": "read-only", "state": "shadow", "canonical_authority": False},
}
EXPECTED_PROMOTION: Final[JsonObject] = {
    "default_state": "shadow",
    "automatic_promotion": False,
    "requires_repeated_task_class_evidence": True,
    "requires_fresh_independent_review": True,
    "requires_explicit_approval": True,
}
ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH: Final = ROOT / "policies" / "discord-staffing.json"


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise EvalContractError("bad_arguments", message)


def _validate_core(decision: JsonObject) -> str:
    exact_fields(decision, CORE_FIELDS, "Core model decision")
    supplied = decision["decision_sha256"]
    if not isinstance(supplied, str):
        raise EvalContractError("malformed_input", "Core decision seal must be text")
    unsigned = dict(decision)
    del unsigned["decision_sha256"]
    expected = canonical_sha256(unsigned)
    if supplied != expected:
        raise EvalContractError("core_seal_mismatch", "Core model decision bytes changed after routing")
    if decision["format"] != "sejong.discord-model-route/v0.1-draft" or decision["authority"] != "core_routing":
        raise EvalContractError("malformed_input", "unexpected Core decision authority")
    controller = object_value(decision["controller"], "controller")
    implementer = object_value(decision["implementer"], "implementer")
    reviewer = object_value(decision["reviewer"], "reviewer")
    shadow = object_value(decision["shadow"], "shadow")
    exact_fields(controller, CONTROLLER_FIELDS, "controller")
    exact_fields(implementer, IMPLEMENTER_FIELDS, "implementer")
    exact_fields(reviewer, REVIEWER_FIELDS, "reviewer")
    exact_fields(shadow, SHADOW_FIELDS, "shadow")
    text_value(decision["task_class"], "task_class")
    text_value(decision["risk_class"], "risk_class")
    text_value(decision["verification_class"], "verification_class")
    boolean_value(decision["requires_approval"], "requires_approval")
    if controller["slot"] != "terra" or controller["function"] != "controller_router_only":
        raise EvalContractError("malformed_input", "Terra must remain a non-mutating controller")
    if controller["can_mutate"] is not False:
        raise EvalContractError("malformed_input", "Terra must remain a non-mutating controller")
    if implementer["slot"] != "luna" or implementer["sandbox"] != "workspace-write":
        raise EvalContractError("malformed_input", "Luna must retain the Core implementation sandbox")
    text_value(implementer["model"], "implementer.model")
    if implementer["model_immutable_per_run"] is not True:
        raise EvalContractError("malformed_input", "Luna requires a fixed Core-selected model")
    if reviewer["slot"] != "sol" or reviewer["sandbox"] != "read-only":
        raise EvalContractError("malformed_input", "Sol must be a read-only reviewer")
    text_value(reviewer["model"], "reviewer.model")
    if reviewer["fresh_run_required"] is not True:
        raise EvalContractError("malformed_input", "Sol requires a fresh independent review run")
    if shadow["slot"] != "antigravity" or shadow["sandbox"] != "read-only":
        raise EvalContractError("malformed_input", "Antigravity must remain a read-only shadow")
    text_value(shadow["model"], "shadow.model")
    if shadow["state"] != "shadow" or shadow["canonical_authority"] is not False:
        raise EvalContractError("malformed_input", "Antigravity must remain non-canonical")
    return supplied


def _load_policy(path: Path) -> JsonObject:
    policy = load_object(path)
    exact_fields(policy, POLICY_FIELDS, "Discord staffing policy")
    if (
        policy["format"] != "agent-company.discord-staffing/v0.1-draft"
        or policy["authority"] != "staffing_projection_only"
        or policy["core_decision_format"] != "sejong.discord-model-route/v0.1-draft"
    ):
        raise EvalContractError("malformed_input", "unexpected Discord staffing policy")
    forbidden = frozenset(string_list(policy["forbidden_overrides"], "forbidden_overrides"))
    if forbidden != FORBIDDEN:
        raise EvalContractError("malformed_input", "staffing policy weakens Core authority")
    assignments = object_value(policy["assignments"], "assignments")
    if set(assignments) != set(ASSIGNMENT_FIELDS):
        raise EvalContractError("malformed_input", "staffing assignment slots must be exact")
    for slot, fields in ASSIGNMENT_FIELDS.items():
        exact_fields(object_value(assignments[slot], slot), fields, slot)
    if assignments != EXPECTED_ASSIGNMENTS:
        raise EvalContractError("malformed_input", "staffing assignments differ from the projection contract")
    terra = object_value(assignments.get("terra"), "terra")
    sol = object_value(assignments.get("sol"), "sol")
    antigravity = object_value(assignments.get("antigravity"), "antigravity")
    if terra.get("may_change_core_decision") is not False or terra.get("may_modify_code") is not False:
        raise EvalContractError("malformed_input", "Terra projection cannot route or mutate")
    if sol.get("sandbox") != "read-only" or antigravity.get("canonical_authority") is not False:
        raise EvalContractError("malformed_input", "review projections must preserve Core boundaries")
    promotion = object_value(policy["promotion"], "promotion")
    exact_fields(promotion, PROMOTION_FIELDS, "promotion")
    if promotion != EXPECTED_PROMOTION:
        raise EvalContractError("malformed_input", "staffing promotion must default to manual shadow")
    return policy


def project_staffing(decision: JsonObject, policy_path: Path) -> JsonObject:
    seal = _validate_core(decision)
    policy = _load_policy(policy_path)
    return {
        "format": "agent-company.discord-staffing-projection/v0.1-draft",
        "authority": "staffing_projection_only",
        "core_decision_sha256": seal,
        "assignments": policy["assignments"],
        "forbidden_overrides": policy["forbidden_overrides"],
        "promotion": policy["promotion"],
    }


def _parse_args() -> argparse.Namespace:
    parser = _JsonArgumentParser(add_help=False)
    parser.add_argument("--decision", required=True, type=Path)
    parser.add_argument("--policy", default=DEFAULT_POLICY_PATH, type=Path)
    return parser.parse_args()


def main() -> int:
    try:
        args = _parse_args()
        projection = project_staffing(load_object(args.decision), args.policy)
    except EvalContractError as exc:
        code = exc.code
    except (UnicodeDecodeError, UnicodeEncodeError):
        code = "malformed_input"
    else:
        print(json.dumps(projection, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        return 0
    print(
        json.dumps({"status": "error", "code": code}, separators=(",", ":"), sort_keys=True),
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
