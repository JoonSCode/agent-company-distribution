#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/sync-status.py --json
# 3. Or run with system Python when stdlib-only execution is preferred:
#      python3 scripts/sync-status.py --json
# ──────────────────

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

from agent_company_sync_report import sync_status


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="sync-status.py")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--device-home", action="append", type=Path, default=[])
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    payload = sync_status(args.device_home)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"sync-status: {payload['status']} ({payload['device_count']} device(s))")
    return 1 if payload.get("material_failure") is True else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
