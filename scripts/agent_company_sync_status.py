#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations
# pyright: reportAny=false, reportImplicitRelativeImport=false, reportUnusedCallResult=false

import argparse
import json
import os
from pathlib import Path

from agent_company_core_sync import build_sync_status


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report Agent Company and installed King Sejong synchronization without changing runtime state."
    )
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--sejong-home", type=Path)
    parser.add_argument("--core-source", type=Path)
    args = parser.parse_args()
    env = os.environ.copy()
    if args.codex_home is not None:
        env["CODEX_HOME"] = str(args.codex_home.expanduser().resolve())
    if args.sejong_home is not None:
        env["SEJONG_HOME"] = str(args.sejong_home.expanduser().resolve())
    if args.core_source is not None:
        env["AGENT_COMPANY_DEP_MODE"] = "local"
        env["AGENT_COMPANY_KING_SEJONG_LOCAL_PATH"] = str(args.core_source.expanduser().resolve())
    print(json.dumps(build_sync_status(env=env), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
