#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Append: python3 scripts/agent_company_memory.py append --record record.json
# 3. List: python3 scripts/agent_company_memory.py list --role planning
# ─────────────────

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

from agent_company_memory_domain import append_record, delete_record, load_records, runtime_home
from agent_company_memory_models import (
    FORMAT,
    Freshness,
    MemoryContractError,
    MemoryRecord,
    Source,
    memory_json,
    parse_memory_record,
    validate_memory_graph,
)
from agent_company_privacy import JsonObject, JsonValue
from agent_company_privacy_cli import memory_main

__all__ = [
    "FORMAT", "Freshness", "JsonObject", "JsonValue", "MemoryContractError", "MemoryRecord", "Source",
    "append_record", "delete_record", "load_records", "memory_json", "parse_memory_record", "runtime_home",
    "validate_memory_graph",
]


if __name__ == "__main__":
    raise SystemExit(memory_main())
