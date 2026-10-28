#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Read-only Company source/installed/managed-runtime synchronization status."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

from agent_company_sync_report import sync_status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path)
    args = parser.parse_args()
    result = sync_status([args.codex_home] if args.codex_home else [])
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result.get("material_failure") is True else 0


if __name__ == "__main__":
    raise SystemExit(main())
