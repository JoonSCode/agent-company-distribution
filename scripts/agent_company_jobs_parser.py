from __future__ import annotations

import argparse
from pathlib import Path

from agent_company_job_policy import JOB_TYPES, ROLES


def parse_ambiguity(value: str) -> tuple[str, str]:
    question, separator, impact = value.partition("|")
    if not separator or not question or not impact:
        raise argparse.ArgumentTypeError("ambiguity must be question|decision_impact")
    return question, impact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Project Agent Company policy into King Sejong inputs and "
            "evidence-derived CEO reports."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)
    classify_parser = commands.add_parser(
        "classify", help="Classify one app-studio request",
    )
    classify_parser.add_argument("--request", required=True)
    create = commands.add_parser(
        "create-job", help="Create a private company job projection",
    )
    create.add_argument("--output", required=True, type=Path)
    create.add_argument("--job-id", required=True)
    create.add_argument("--job-type", choices=JOB_TYPES)
    create.add_argument("--objective", required=True)
    create.add_argument("--source-request", required=True)
    create.add_argument("--activate-role", action="append", choices=sorted(ROLES))
    create.add_argument("--company-plan-topology", action="store_true")
    create.add_argument("--ambiguity", action="append", type=parse_ambiguity)
    create.add_argument(
        "--initiative-origin",
        choices=("ceo-directed", "company-initiated"),
        default="ceo-directed",
    )
    create.add_argument("--initiative-id")
    create.add_argument(
        "--target-kind",
        choices=("existing-app", "new-app", "portfolio"),
        default="portfolio",
    )
    create.add_argument("--target-ref", default="company://portfolio")
    create.add_argument(
        "--commercial-hypothesis",
        default="Commercial hypothesis is unknown until evidence is gathered",
    )
    create.add_argument("--success-metric", action="append")
    create.add_argument("--failure-metric", action="append")
    create.add_argument("--guardrail", action="append")
    front = commands.add_parser(
        "front-door", help="Validate and project one Core-backed Company route",
    )
    front.add_argument("--core-decision", required=True, type=Path)
    front.add_argument("--core-decision-sha256", required=True)
    front.add_argument("--route-decision", required=True, type=Path)
    front.add_argument("--objective", required=True)
    front.add_argument("--role", action="append", choices=sorted(ROLES))
    front.add_argument("--external-mutation", action="store_true")
    front.add_argument("--approval-required", action="store_true")
    front.add_argument("--external-action-ledger", type=Path)
    front.add_argument("--external-action-ledger-sha256")
    front.add_argument("--external-action-id")
    front.add_argument("--output", required=True, type=Path)
    approve = commands.add_parser(
        "approve-uigwe",
        help="Resume the same job after a decision-bound Uigwe artifact",
    )
    approve.add_argument("--job", required=True, type=Path)
    approve.add_argument("--decision-ref", required=True, type=Path)
    project = commands.add_parser(
        "delegation-input", help="Render company policy as Core delegation input",
    )
    project.add_argument("--job", required=True, type=Path)
    project.add_argument("--output", required=True, type=Path)
    project.add_argument("--specialist-request", action="append", type=Path)
    project.add_argument("--company-plan", type=Path)
    project.add_argument("--role-plan", action="append", type=Path)
    report = commands.add_parser(
        "report", help="Render a truthful CEO report from Core evidence",
    )
    report.add_argument("--job", required=True, type=Path)
    report.add_argument("--delegation-input", required=True, type=Path)
    report.add_argument("--core-run", required=True, type=Path)
    report.add_argument("--verification-run", type=Path)
    report.add_argument("--external-action-ledger", type=Path)
    report.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Canonical machine-readable CEO report JSON",
    )
    report.add_argument(
        "--markdown-output",
        type=Path,
        help="Optional Markdown derivative of the canonical report",
    )
    return parser
