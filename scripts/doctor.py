#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/doctor.py --json
# 3. Or run with system Python when stdlib-only execution is preferred:
#      python3 scripts/doctor.py --json
# ──────────────────

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Final

from agent_company_status_checks import enrich_runtime_status
from agent_company_profiles import check_profiles
from agent_company_runtime import JsonValue, runtime_report


ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES_DIR: Final[Path] = ROOT / "agents"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="doctor.py",
        description="Agent Company doctor checks.",
    )
    parser.add_argument("--check-profiles", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--profiles-dir",
        type=Path,
        default=DEFAULT_PROFILES_DIR,
    )
    return parser.parse_args(argv)


def emit(payload: dict[str, JsonValue], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"{payload.get('check', 'doctor')}: {payload.get('status', 'unknown')}")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.check_profiles:
        check = check_profiles(args.profiles_dir)
        payload: dict[str, JsonValue] = asdict(check)
        emit(payload, as_json=args.json)
        return 0 if check.status == "ok" else 1
    payload = enrich_runtime_status(runtime_report(write_doctor_timestamp=True))
    emit(payload, as_json=args.json)
    return 1 if payload.get("material_failure") is True else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
