#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv if needed.
# 2. Check evidence: python3 scripts/agent_company_qa_release.py check --evidence FILE
# 3. A non-passed QA state exits 1; malformed/private evidence exits 2.
# ─────────────────

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import assert_never

from agent_company_plan_models import PlanError
from agent_company_qa_release_parse import parse_evidence
from agent_company_qa_release_report import evaluate
from agent_company_qa_release_types import ObservationStatus


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check")
    check.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = evaluate(parse_evidence(args.evidence))
    except PlanError as exc:
        print(json.dumps({"status": "error", "code": exc.code, "path": exc.path, "detail": exc.detail}, sort_keys=True))
        return 2
    print(json.dumps(asdict(report), sort_keys=True))
    match report.status:
        case ObservationStatus.PASSED:
            return 0
        case ObservationStatus.FAILED | ObservationStatus.BLOCKED | ObservationStatus.UNVERIFIED:
            return 1
        case unreachable:
            assert_never(unreachable)


if __name__ == "__main__":
    raise SystemExit(main())
