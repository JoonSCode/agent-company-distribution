#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/agent_company_jobs.py --help
# 3. Or make executable and run:
#      chmod +x scripts/agent_company_jobs.py && ./scripts/agent_company_jobs.py --help
# ─────────────────

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from agent_company_deps import JsonValue
from agent_company_front_door_policy import (
    FrontDoorError,
    FrontDoorRequest,
    project_front_door,
)
from agent_company_job_policy import (
    JobRequest,
    PolicyError,
    approve_uigwe,
    build_delegation_input,
    build_job,
    classify,
    read_object,
    write_object,
    write_text,
)
from agent_company_jobs_parser import build_parser
from agent_company_report import (
    ReportRuntimeBindings,
    build_ceo_report,
    load_ceo_report_template,
    render_ceo_report_markdown,
)
from agent_company_route_authority import RouteAuthorityRequest, load_route_authority
from agent_company_route_contract import RoutingError


@dataclass(frozen=True, slots=True)
class ReportPublication:
    json_output: Path
    report: dict[str, JsonValue]
    markdown_output: Path
    markdown: str


def _publish_report_pair(publication: ReportPublication) -> None:
    json_output = publication.json_output
    report = publication.report
    markdown_output = publication.markdown_output
    markdown = publication.markdown
    for path, label in ((json_output, "canonical JSON"), (markdown_output, "Markdown derivative")):
        if path.exists() and not path.is_file():
            raise PolicyError(f"{label} output must be a regular file path: {path}")
    previous_markdown: str | None = None
    markdown_existed = markdown_output.exists()
    if markdown_existed:
        try:
            previous_markdown = markdown_output.read_text(encoding="utf-8")
        except OSError as exc:
            raise PolicyError(f"cannot snapshot Markdown output {markdown_output}: {exc}") from exc
    write_text(markdown_output, markdown)
    try:
        write_object(json_output, report)
    except PolicyError as publish_error:
        try:
            if markdown_existed and previous_markdown is not None:
                write_text(markdown_output, previous_markdown)
            else:
                markdown_output.unlink(missing_ok=True)
        except (OSError, PolicyError) as rollback_error:
            raise PolicyError(
                f"canonical JSON publication failed and Markdown rollback failed: "
                f"publish={publish_error}; rollback={rollback_error}"
            ) from rollback_error
        raise


def publish_report_pair(
    json_output: Path, report: dict[str, JsonValue],
    markdown_output: Path, markdown: str,
) -> None:
    """Preserve the v0.1 public adapter while grouping publication state internally."""
    _publish_report_pair(ReportPublication(json_output, report, markdown_output, markdown))


def run(args: argparse.Namespace) -> dict[str, JsonValue]:
    if args.command == "classify":
        return {"format": "agent-company.classification/v0.1", "job_type": classify(args.request)}
    if args.command == "create-job":
        job_type = args.job_type or classify(args.source_request)
        job = build_job(JobRequest(
            args.job_id, job_type, args.objective, args.source_request,
            tuple(args.activate_role or []), tuple(args.ambiguity or []),
            args.company_plan_topology,
            initiative_origin=args.initiative_origin,
            initiative_id=args.initiative_id,
            target_kind=args.target_kind,
            target_ref=args.target_ref,
            commercial_hypothesis=args.commercial_hypothesis,
            success_metrics=tuple(
                args.success_metric
                or ["commercial evidence is gathered or explicitly remains unknown"]
            ),
            failure_metrics=tuple(
                args.failure_metric
                or ["guardrail breach or negative commercial evidence is recorded"]
            ),
            guardrails=tuple(
                args.guardrail
                or [
                    "external mutation, publication, and spend require explicit CEO approval",
                    "independent matching-surface verification is required",
                ]
            ),
        ))
        write_object(args.output, job)
        return {"status": "ok", "job_id": args.job_id, "job_type": job_type, "path": str(args.output)}
    if args.command == "front-door":
        authority = load_route_authority(RouteAuthorityRequest(
            args.core_decision,
            args.core_decision_sha256,
            Path(os.environ.get("SEJONG_HOME", "~/.codex/sejong")).expanduser(),
            args.external_mutation,
            args.approval_required,
            args.external_action_ledger,
            args.external_action_ledger_sha256,
            args.external_action_id,
        ))
        core_ref = Path(authority.core.reference).as_uri()
        request = FrontDoorRequest(
            authority.core.value,
            tuple(args.role or []),
            args.external_mutation,
            args.approval_required,
            core_ref,
            authority.core.sha256,
            authority.approval,
        )
        projection = project_front_door(
            read_object(args.route_decision), request, args.objective,
        )
        write_object(args.output, projection)
        return {"status": "ok", "lane": projection["lane"], "path": str(args.output)}
    if args.command == "approve-uigwe":
        decision_ref: Path = args.decision_ref
        job = approve_uigwe(
            read_object(args.job),
            read_object(decision_ref),
            str(decision_ref.expanduser().resolve()),
        )
        write_object(args.job, job)
        return {"status": "ok", "job_id": job["job_id"], "path": str(args.job)}
    if args.command == "delegation-input":
        specialist_requests = tuple(
            read_object(path) for path in (args.specialist_request or [])
        )
        projection = build_delegation_input(
            read_object(args.job),
            specialist_requests=specialist_requests,
            company_plan_path=args.company_plan,
            role_plan_paths=tuple(args.role_plan or []),
            env=os.environ,
        )
        write_object(args.output, projection)
        return {"status": "ok", "job_id": projection["job_id"], "path": str(args.output)}
    if args.command == "report":
        markdown_output: Path | None = args.markdown_output
        if markdown_output is not None:
            try:
                outputs_collide = args.output.resolve() == markdown_output.resolve()
            except OSError as exc:
                raise PolicyError(
                    f"cannot resolve output paths {args.output} and {markdown_output}: {exc}"
                ) from exc
            if outputs_collide:
                raise PolicyError("JSON and Markdown output paths must be different")
        verification = read_object(args.verification_run) if args.verification_run else None
        external_action_ledger = (
            read_object(args.external_action_ledger) if args.external_action_ledger else None
        )
        report = build_ceo_report(
            read_object(args.delegation_input),
            ReportRuntimeBindings(
                job=read_object(args.job),
                job_ref=os.path.abspath(args.job.expanduser()),
                core_run=read_object(args.core_run),
                core_run_ref=os.path.abspath(args.core_run.expanduser()),
                delegation_input_ref=os.path.abspath(
                    args.delegation_input.expanduser()
                ),
                verification_run=verification,
                verification_run_ref=(
                    os.path.abspath(args.verification_run.expanduser())
                    if args.verification_run else None
                ),
                external_action_ledger=external_action_ledger,
                external_action_ledger_ref=(
                    os.path.abspath(args.external_action_ledger.expanduser())
                    if args.external_action_ledger else None
                ),
            ),
        )
        if markdown_output is not None:
            markdown = render_ceo_report_markdown(report, load_ceo_report_template())
            publish_report_pair(args.output, report, markdown_output, markdown)
            return {
                "status": "ok",
                "job_id": report["job_id"],
                "overall_status": report["overall_status"],
                "path": str(args.output),
                "markdown_path": str(markdown_output),
            }
        write_object(args.output, report)
        return {"status": "ok", "job_id": report["job_id"], "overall_status": report["overall_status"], "path": str(args.output)}
    raise PolicyError(f"unsupported command: {args.command}")


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = run(args)
    except (PolicyError, FrontDoorError, RoutingError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
