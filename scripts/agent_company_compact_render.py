#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Import render_compact_report_markdown from this module.
# ─────────────────

"""Render a revalidated compact CEO projection without Markdown injection."""

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

import hashlib
import re
from pathlib import Path
from typing import Final

from agent_company_compact_models import CompactReport, Risk
from agent_company_compact_evidence import contains_unsafe_control, parse_evidence_ref
from agent_company_compact_projection import validate_compact_report
from agent_company_projection_policy import PolicyError


ROOT: Final[Path] = Path(__file__).resolve().parents[1]
TEMPLATE_PATH: Final[Path] = ROOT / "reports" / "compact-ceo-report.template.md"
TOKEN_PATTERN: Final = re.compile(r"\{\{([^{}]+)\}\}")
TEMPLATE_TOKENS: Final = frozenset({
    "job_id", "lane", "outcome", "verification", "decision_required",
    "decision_prompt", "material_risks", "next_action", "evidence_links",
    "detailed_report_ref",
})
MARKDOWN_META: Final = frozenset("\\`*_[]<>#|")
TEMPLATE_SHA256: Final[str] = "a60c23cc954d649afee87e67040acc65b38baaa4b96abdc47a722a6a8ef40591"


def load_compact_report_template() -> str:
    try:
        payload = TEMPLATE_PATH.read_bytes()
        template = payload.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PolicyError(f"cannot read compact CEO report template {TEMPLATE_PATH}: {exc}") from exc
    if hashlib.sha256(payload).hexdigest() != TEMPLATE_SHA256:
        raise PolicyError("compact CEO template authority digest mismatch")
    return template


def _text(value: str, label: str) -> str:
    if not value or contains_unsafe_control(value):
        raise PolicyError(f"{label} contains unsafe report characters")
    return "".join(f"\\{character}" if character in MARKDOWN_META else character for character in value)


def _ref(value: str, label: str) -> str:
    return parse_evidence_ref(value, label)


def _risks(risks: tuple[Risk, ...]) -> str:
    if not risks:
        return "- None recorded."
    return "\n".join(
        f"- `{risk.state.value}` {_text(risk.summary, 'risk summary')}"
        + "".join(f"\n  - `{_ref(ref, 'risk evidence ref')}`" for ref in risk.evidence_refs)
        for risk in risks
    )


def _links(links: tuple[str, ...]) -> str:
    return "\n".join(f"- `{_ref(link, 'evidence link')}`" for link in links)


def render_compact_report_markdown(report: CompactReport, template: str) -> str:
    report = validate_compact_report(report)
    tokens = frozenset(TOKEN_PATTERN.findall(template))
    if tokens != TEMPLATE_TOKENS:
        raise PolicyError(
            f"compact CEO template token drift: missing={sorted(TEMPLATE_TOKENS - tokens)}, unexpected={sorted(tokens - TEMPLATE_TOKENS)}"
        )
    if hashlib.sha256(template.encode()).hexdigest() != TEMPLATE_SHA256:
        raise PolicyError("compact CEO template authority digest mismatch")
    replacements = {
        "job_id": _text(report.source.report.job_id, "job_id"),
        "lane": report.lane,
        "outcome": _text(report.outcome, "outcome"),
        "verification": report.verification.value,
        "decision_required": "yes" if report.decision_required else "no",
        "decision_prompt": _text(report.decision_prompt, "decision prompt"),
        "material_risks": _risks(report.material_risks),
        "next_action": _text(report.next_action, "next action"),
        "evidence_links": _links(report.evidence_links),
        "detailed_report_ref": _ref(report.source.ref, "detailed report ref"),
    }
    return TOKEN_PATTERN.sub(lambda token: replacements[token.group(1)], template).rstrip() + "\n"
