#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Import the byte-binding, projection, serialization, and rendering API.
# ─────────────────

"""Public facade for secure compact CEO report projection."""

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

from agent_company_compact_canonical import bind_canonical_report
from agent_company_compact_models import CanonicalBinding, CompactReport, ValidatedRoute
from agent_company_compact_projection import build_compact_report, compact_report_json
from agent_company_compact_render import (
    load_compact_report_template,
    render_compact_report_markdown,
)
from agent_company_compact_route import bind_route_decision


__all__ = [
    "CanonicalBinding",
    "CompactReport",
    "ValidatedRoute",
    "bind_canonical_report",
    "bind_route_decision",
    "build_compact_report",
    "compact_report_json",
    "load_compact_report_template",
    "render_compact_report_markdown",
]
