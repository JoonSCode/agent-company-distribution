#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Use through agent_company_memory.py or agent_company_telemetry.py.
# 3. Test: python3 scripts/test_agent_company_privacy_suite.py --case all
# ─────────────────

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

import json
import sys
from dataclasses import asdict
from pathlib import Path

from agent_company_memory_domain import append_record, load_records
from agent_company_memory_models import FORMAT as MEMORY_FORMAT, MemoryContractError
from agent_company_privacy import PrivacyError, parse_json, parse_rfc3339
from agent_company_telemetry_domain import load_events, record_event
from agent_company_telemetry_models import TelemetryContractError, event_json


def _option(args: list[str], name: str) -> str | None:
    try:
        index = args.index(name)
    except ValueError:
        return None
    return args[index + 1] if index + 1 < len(args) else None


def memory_main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        command = args[0] if args else ""
        role = _option(args, "--role")
        if command == "append":
            record_path = _option(args, "--record")
            if record_path is None:
                raise MemoryContractError("malformed_input", "append requires --record")
            value = parse_json(Path(record_path).read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise MemoryContractError("malformed_input", "record must be an object")
            record = append_record(value)
            print(json.dumps({"format": MEMORY_FORMAT, **asdict(record)}, sort_keys=True))
        elif command == "list" and role is not None:
            records = load_records(requesting_role=role)
            print(json.dumps([{"format": MEMORY_FORMAT, **asdict(item)} for item in records], sort_keys=True))
        else:
            raise MemoryContractError("malformed_input", "expected append or list --role ROLE")
    except (json.JSONDecodeError, OSError, MemoryContractError) as exc:
        print(f"memory error: {exc}", file=sys.stderr)
        return 2
    return 0


def telemetry_main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        command = args[0] if args else ""
        role = _option(args, "--role")
        if command == "append":
            event_path = _option(args, "--event")
            if event_path is None:
                raise TelemetryContractError("malformed_input", "append requires --event")
            value = parse_json(Path(event_path).read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise TelemetryContractError("malformed_input", "event must be an object")
            now_text = _option(args, "--now")
            now = parse_rfc3339(now_text, "now") if now_text is not None else None
            result = record_event(value, now=now)
            print(json.dumps(asdict(result), sort_keys=True))
        elif command == "list" and role is not None:
            print(json.dumps([event_json(item) for item in load_events(requesting_role=role)], sort_keys=True))
        else:
            raise TelemetryContractError("malformed_input", "expected append or list --role ROLE")
    except (json.JSONDecodeError, OSError, PrivacyError, TelemetryContractError) as exc:
        print(f"telemetry error: {exc}", file=sys.stderr)
        return 2
    return 0
