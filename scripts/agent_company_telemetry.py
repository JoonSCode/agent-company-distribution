#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Append: python3 scripts/agent_company_telemetry.py append --event event.json
# 3. List: python3 scripts/agent_company_telemetry.py list --role qa-release
# ─────────────────

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

from agent_company_privacy import JsonObject, JsonValue
from agent_company_privacy_cli import telemetry_main
from agent_company_telemetry_domain import load_events, prune_telemetry, record_event, runtime_home
from agent_company_telemetry_models import (
    FORMAT,
    MetricEvent,
    TelemetryContractError,
    TelemetryWriteResult,
    event_json,
    parse_metric_event,
)

__all__ = [
    "FORMAT", "JsonObject", "JsonValue", "MetricEvent", "TelemetryContractError", "TelemetryWriteResult",
    "event_json", "load_events", "parse_metric_event", "prune_telemetry", "record_event", "runtime_home",
]


if __name__ == "__main__":
    raise SystemExit(telemetry_main())
