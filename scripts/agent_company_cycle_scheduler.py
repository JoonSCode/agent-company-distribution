#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["jsonschema>=4.25,<5"]
# ///

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

from agent_company_cycle_models import CycleError, JsonObject, TickRequest, canonical_time
from agent_company_cycle_policy import tick
from agent_company_cycle_store import mutate_state, read_state
from agent_company_deps import JsonValue


def _integer(value: JsonValue, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CycleError("malformed_state", f"{label} must be a non-negative integer")
    return value


def run(state_path: Path, handoff_dir: Path, now: str | None, tick_key: str | None) -> JsonObject:
    state = read_state(state_path)
    timestamp = canonical_time(
        now or datetime.now(timezone.utc).isoformat(), "now",
    )
    key = tick_key or f"scheduled-{hashlib.sha256(timestamp.encode()).hexdigest()[:20]}"
    request = TickRequest(timestamp, key, str(handoff_dir))
    return mutate_state(
        state_path,
        _integer(state.get("revision"), "revision"),
        _integer(state.get("fencing_token"), "fencing_token"),
        lambda current: tick(current, request),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one scheduler-safe Agent Company tick without installing a host service.",
    )
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--handoff-dir", required=True, type=Path)
    parser.add_argument("--now")
    parser.add_argument("--tick-key")
    args = parser.parse_args()
    try:
        result = run(args.state, args.handoff_dir, args.now, args.tick_key)
    except CycleError as exc:
        print(json.dumps({"status": "error", "code": exc.code, "detail": exc.detail}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
