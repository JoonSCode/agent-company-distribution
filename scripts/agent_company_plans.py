#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Check plans:
#      python3 scripts/agent_company_plans.py check --company COMPANY --role ROLE
# 3. Generate a local fixture:
#      python3 scripts/agent_company_plans.py generate-fixture --output-dir DIR
# ─────────────────

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from agent_company_plan_models import JsonValue, PlanError, file_sha256
from agent_company_plan_validation import check_plan_files


FIXTURE_ROOT = Path(__file__).with_name("fixtures") / "agent_company_plans"


def _render(source: Path, destination: Path, replacements: dict[str, str]) -> None:
    rendered = source.read_text(encoding="utf-8")
    for marker, value in replacements.items():
        rendered = rendered.replace(marker, value)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered, encoding="utf-8")


def generate_fixture(output: Path) -> tuple[Path, Path, Path]:
    company = output / "company-plan.json"
    roles = (output / "development-role-plan.json", output / "qa-release-role-plan.json")
    runtime = output / "sejong-home" / "runs" / "agent-company" / "fixture-run"
    packet, decision = runtime / "uigwe-packet.json", runtime / "uigwe-decision.json"
    targets = (company, *roles, packet, decision)
    if any(path.exists() for path in targets):
        raise PlanError("fixture_exists", str(output), "refusing to replace an existing fixture")
    _render(FIXTURE_ROOT / packet.name, packet, {})
    _render(FIXTURE_ROOT / decision.name, decision, {})
    _render(
        FIXTURE_ROOT / company.name,
        company,
        {
            "__UIGWE_PACKET_SHA256__": file_sha256(packet, "fixture_error"),
            "__UIGWE_DECISION_SHA256__": file_sha256(decision, "fixture_error"),
        },
    )
    company_sha256 = file_sha256(company, "fixture_error")
    for role in roles:
        _render(
            FIXTURE_ROOT / role.name,
            role,
            {
                "__COMPANY_PLAN_REF__": str(company.resolve()),
                "__COMPANY_PLAN_SHA256__": company_sha256,
            },
        )
    return company, *roles


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check")
    check.add_argument("--company", required=True, type=Path)
    check.add_argument("--role", required=True, action="append", type=Path)
    fixture = commands.add_parser("generate-fixture")
    fixture.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "check":
            result = check_plan_files(args.company, tuple(args.role), os.environ)
            output: dict[str, JsonValue] = {"status": "ok", "plan_id": result.plan_id, "assignment_count": result.assignment_count, "role_plan_count": result.role_plan_count}
        else:
            generated = generate_fixture(args.output_dir)
            output = {"status": "ok", "generated": [str(path) for path in generated], "sejong_home": str(args.output_dir / "sejong-home")}
    except PlanError as exc:
        print(json.dumps({"status": "error", "code": exc.code, "path": exc.path, "detail": exc.detail}, sort_keys=True))
        return 2 if exc.code == "malformed_input" else 1
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
