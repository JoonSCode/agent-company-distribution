#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Run through the Markdown report suite:
#      uv run scripts/test_agent_company_markdown_report.py
# 2. This module owns canonical CEO-report Markdown rendering.
# ─────────────────

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from agent_company_deps import JsonValue
from agent_company_job_policy import PolicyError, object_list, string_list, text


ROOT: Final[Path] = Path(__file__).resolve().parents[1]
REPORT_TEMPLATE_PATH: Final[Path] = ROOT / "reports" / "ceo-report.template.md"
REPORT_STATES: Final = ("verified", "executed", "failed", "blocked", "unverified")
TEMPLATE_TOKENS: Final = frozenset({
    "job_id", "job_type", "objective", "overall_status", "decision_summary",
    "user_decisions", "verified_deliveries", "executed_deliveries",
    "failed_deliveries", "blocked_deliveries", "unverified_deliveries",
    "external_actions", "verified_claims", "executed_claims", "failed_claims",
    "blocked_claims", "unverified_claims", "risks", "next_actions",
})
TOKEN_PATTERN: Final = re.compile(r"\{\{([^{}]+)\}\}")


def load_ceo_report_template() -> str:
    try:
        return REPORT_TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise PolicyError(
            f"cannot read CEO report template {REPORT_TEMPLATE_PATH}: {exc}",
        ) from exc


def _bullets(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values) if values else "- None recorded."


def _evidence(evidence_refs: list[str], indent: str = "  ") -> str:
    if not evidence_refs:
        return f"{indent}- Evidence: None recorded."
    items = "\n".join(f"{indent}  - `{ref}`" for ref in evidence_refs)
    return f"{indent}- Evidence:\n{items}"


def _deliveries_for_state(deliveries: list[dict[str, JsonValue]], state: str) -> str:
    matching = [delivery for delivery in deliveries if delivery.get("state") == state]
    if not matching:
        return "- None recorded."
    return "\n\n".join("\n".join((
        f"- Role: `{text(item.get('role'), 'delivery role')}`",
        f"  - Worker ref: `{text(item.get('worker_ref'), 'delivery worker_ref')}`",
        f"  - State: `{text(item.get('state'), 'delivery state')}`",
        f"  - Summary: {text(item.get('summary'), 'delivery summary')}",
        _evidence(string_list(item.get("evidence_refs"), "delivery evidence_refs")),
    )) for item in matching)


def _claims_for_state(claims: list[dict[str, JsonValue]], state: str) -> str:
    matching = [claim for claim in claims if claim.get("state") == state]
    if not matching:
        return "- None recorded."
    return "\n\n".join("\n".join((
        f"- Claim: {text(item.get('claim'), 'claim')}",
        _evidence(string_list(item.get("evidence_refs"), "claim evidence_refs")),
    )) for item in matching)


def _external_actions(actions: list[dict[str, JsonValue]]) -> str:
    if not actions:
        return "- None recorded."
    return "\n\n".join("\n".join((
        f"- Action: `{text(item.get('action_id'), 'action id')}`",
        f"  - Name: {text(item.get('action_name'), 'action name')}",
        f"  - Target: {text(item.get('target'), 'action target')}",
        f"  - State: `{text(item.get('state'), 'action state')}`",
        _evidence(string_list(item.get("evidence_refs"), "action evidence_refs")),
    )) for item in actions)


def render_ceo_report_markdown(report: dict[str, JsonValue], template: str) -> str:
    template_tokens = frozenset(TOKEN_PATTERN.findall(template))
    missing = sorted(TEMPLATE_TOKENS - template_tokens)
    unexpected = sorted(template_tokens - TEMPLATE_TOKENS)
    if missing or unexpected:
        raise PolicyError(
            f"CEO report template token drift: missing={missing}, unexpected={unexpected}",
        )
    deliveries = object_list(report.get("role_deliveries"), "role_deliveries")
    claims = object_list(report.get("claims"), "claims")
    replacements = {
        "job_id": text(report.get("job_id"), "job_id"),
        "job_type": text(report.get("job_type"), "job_type"),
        "objective": text(report.get("objective"), "objective"),
        "overall_status": text(report.get("overall_status"), "overall_status"),
        "decision_summary": text(report.get("decision_summary"), "decision_summary"),
        "user_decisions": _bullets(string_list(report.get("user_decisions"), "user_decisions")),
        "external_actions": _external_actions(
            object_list(report.get("external_actions"), "external_actions"),
        ),
        "risks": _bullets(string_list(report.get("risks"), "risks")),
        "next_actions": _bullets(string_list(report.get("next_actions"), "next_actions")),
    }
    for state in REPORT_STATES:
        replacements[f"{state}_deliveries"] = _deliveries_for_state(deliveries, state)
        replacements[f"{state}_claims"] = _claims_for_state(claims, state)
    return TOKEN_PATTERN.sub(lambda token: replacements[token.group(1)], template).rstrip() + "\n"
