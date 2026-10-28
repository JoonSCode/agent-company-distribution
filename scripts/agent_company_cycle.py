#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["jsonschema>=4.25,<5"]
# ///

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

from agent_company_commercial import record_observation, register_app
from agent_company_cycle_models import (
    AdvanceRequest,
    AppRequest,
    CloseRequest,
    CycleError,
    InitiativeRequest,
    JsonObject,
    Mutation,
    ObservationRequest,
    TickRequest,
)
from agent_company_cycle_policy import default_state, enqueue, tick
from agent_company_cycle_store import initialize_state, mutate_state, read_state
from agent_company_cycle_transitions import advance, close


def _state_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state", required=True, type=Path)


def _cas_arguments(parser: argparse.ArgumentParser) -> None:
    _state_argument(parser)
    parser.add_argument("--expected-revision", required=True, type=int)
    parser.add_argument("--expected-fencing-token", required=True, type=int)


def parse_metric(value: str) -> tuple[str, float]:
    name, separator, raw_value = value.partition("=")
    if not separator or not name or not raw_value:
        raise argparse.ArgumentTypeError("metric must be name=value")
    try:
        number = float(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("metric value must be numeric") from exc
    return name, number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one deterministic, resumable Agent Company cycle transition.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init")
    _state_argument(initialize)
    initialize.add_argument("--now", required=True)
    initialize.add_argument("--next-tick-at", required=True)
    app = commands.add_parser("register-app")
    _cas_arguments(app)
    app.add_argument("--app-id", required=True)
    app.add_argument("--name", required=True)
    app.add_argument("--kind", choices=("existing-app", "new-opportunity"), required=True)
    app.add_argument(
        "--lifecycle",
        choices=("discovery", "build", "released", "growth", "maintenance", "paused", "retired"),
        required=True,
    )
    app.add_argument("--repository-ref")
    observation = commands.add_parser("observe")
    _cas_arguments(observation)
    observation.add_argument("--app-id", required=True)
    observation.add_argument("--observation-id", required=True)
    observation.add_argument("--captured-at", required=True)
    observation.add_argument("--source-ref", required=True)
    observation.add_argument("--source-sha256", required=True)
    observation.add_argument("--evidence-status", choices=("pending", "observed"), required=True)
    observation.add_argument("--currency", required=True)
    observation.add_argument(
        "--attribution", choices=("unknown", "unattributed", "attributed"), required=True,
    )
    observation.add_argument("--confidence", required=True, type=float)
    observation.add_argument("--freshness", choices=("fresh", "stale", "unknown"), required=True)
    observation.add_argument("--limitation", action="append", required=True)
    observation.add_argument("--metric", action="append", type=parse_metric, default=[])
    queue = commands.add_parser("enqueue")
    _cas_arguments(queue)
    queue.add_argument("--now", required=True)
    queue.add_argument("--initiative-id", required=True)
    queue.add_argument("--origin", choices=("ceo-directed", "company-initiated"), required=True)
    queue.add_argument("--app-id")
    queue.add_argument(
        "--job-type",
        choices=("new-app", "improvement", "planning", "promotion", "release", "incident", "portfolio"),
        required=True,
    )
    queue.add_argument("--priority", required=True, type=int)
    queue.add_argument("--objective", required=True)
    queue.add_argument("--commercial-hypothesis", required=True)
    queue.add_argument("--success-metric", action="append", required=True)
    queue.add_argument("--failure-metric", action="append", required=True)
    queue.add_argument("--guardrail", action="append", required=True)
    tick_parser = commands.add_parser("tick")
    _cas_arguments(tick_parser)
    tick_parser.add_argument("--now", required=True)
    tick_parser.add_argument("--tick-key", required=True)
    tick_parser.add_argument("--handoff-dir", required=True, type=Path)
    advance_parser = commands.add_parser("advance")
    _cas_arguments(advance_parser)
    advance_parser.add_argument("--cycle-id", required=True)
    advance_parser.add_argument(
        "--phase",
        choices=("planning", "delegating", "executing", "verifying", "commercial-review", "awaiting-approval"),
        required=True,
    )
    advance_parser.add_argument("--now", required=True)
    advance_parser.add_argument("--evidence-ref", required=True)
    advance_parser.add_argument("--plan-sha256")
    close_parser = commands.add_parser("close")
    _cas_arguments(close_parser)
    close_parser.add_argument("--cycle-id", required=True)
    close_parser.add_argument("--outcome", choices=("completed", "stopped"), required=True)
    close_parser.add_argument("--now", required=True)
    close_parser.add_argument("--next-tick-at", required=True)
    close_parser.add_argument("--evidence-ref", required=True)
    status = commands.add_parser("status")
    _state_argument(status)
    return parser


def _mutate(
    args: argparse.Namespace,
    transform: Callable[[JsonObject], Mutation],
) -> JsonObject:
    return mutate_state(
        args.state,
        args.expected_revision,
        args.expected_fencing_token,
        transform,
    )


def run(args: argparse.Namespace) -> JsonObject:
    if args.command == "init":
        return initialize_state(args.state, default_state(args.now, args.next_tick_at))
    if args.command == "register-app":
        request = AppRequest(
            args.app_id, args.name, args.kind, args.lifecycle, args.repository_ref,
        )
        return _mutate(args, lambda state: register_app(state, request))
    if args.command == "observe":
        request = ObservationRequest(
            args.app_id,
            args.observation_id,
            args.captured_at,
            args.source_ref,
            args.source_sha256,
            args.evidence_status,
            args.currency,
            args.attribution,
            args.confidence,
            args.freshness,
            tuple(args.limitation),
            tuple(args.metric),
        )
        return _mutate(args, lambda state: record_observation(state, request))
    if args.command == "enqueue":
        request = InitiativeRequest(
            args.initiative_id,
            args.origin,
            args.app_id,
            args.job_type,
            args.priority,
            args.objective,
            args.commercial_hypothesis,
            tuple(args.success_metric),
            tuple(args.failure_metric),
            tuple(args.guardrail),
            args.now,
        )
        return _mutate(args, lambda state: enqueue(state, request))
    if args.command == "tick":
        request = TickRequest(args.now, args.tick_key, str(args.handoff_dir))
        return _mutate(args, lambda state: tick(state, request))
    if args.command == "advance":
        request = AdvanceRequest(
            args.cycle_id,
            args.phase,
            args.now,
            args.evidence_ref,
            args.plan_sha256,
        )
        return _mutate(args, lambda state: advance(state, request))
    if args.command == "close":
        request = CloseRequest(
            args.cycle_id,
            args.outcome,
            args.now,
            args.next_tick_at,
            args.evidence_ref,
        )
        return _mutate(args, lambda state: close(state, request))
    if args.command == "status":
        state = read_state(args.state)
        portfolio = state.get("portfolio")
        initiatives = portfolio.get("initiatives") if isinstance(portfolio, dict) else []
        return {
            "status": "ok",
            "path": str(args.state.resolve()),
            "revision": state["revision"],
            "fencing_token": state["fencing_token"],
            "next_tick_at": state["next_tick_at"],
            "active_cycle": state["active_cycle"],
            "initiative_count": len(initiatives) if isinstance(initiatives, list) else 0,
            "cycle_history_count": len(state["cycle_history"]) if isinstance(state["cycle_history"], list) else 0,
        }
    raise CycleError("malformed_input", f"unsupported command: {args.command}")


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = run(args)
    except CycleError as exc:
        print(json.dumps({"status": "error", "code": exc.code, "detail": exc.detail}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
