#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Imported by agent_company_telemetry_domain.py.
# 3. Test: python3 scripts/test_agent_company_telemetry.py
# ─────────────────

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

import re
from dataclasses import asdict, dataclass
from typing import Final, final, override

from agent_company_attempt_receipt import (
    AttemptReceipt,
)
from agent_company_attempt_receipt_json import attempt_receipt_json
from agent_company_attempt_receipt_parse import parse_attempt_receipt
from agent_company_attempt_receipt_values import AttemptReceiptError
from agent_company_privacy import JsonObject, PrivacyError, parse_rfc3339, reject_sensitive


FORMAT: Final[str] = "agent-company.metric-event/v0.2"
REQUIRED: Final = frozenset({
    "format", "event_id", "occurred_at", "task_class", "lane", "core_route", "core_backend",
    "role_count", "worker_count", "elapsed_ms", "retries", "outcome", "verification",
})
ID: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
NAME: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


@final
class TelemetryContractError(Exception):
    """Typed telemetry-contract failure."""

    code: str
    detail: str

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)
        self.code = code
        self.detail = detail

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class MetricEvent:
    event_id: str
    occurred_at: str
    task_class: str
    lane: str
    core_route: str
    core_backend: str
    role_count: int
    worker_count: int
    elapsed_ms: int
    retries: int
    outcome: str
    verification: str
    tool_count: int | None = None
    token_count: int | None = None
    attempt_receipt: AttemptReceipt | None = None


@dataclass(frozen=True, slots=True)
class TelemetryWriteResult:
    written: bool
    warning: str | None
    pruned_count: int


def _text(values: JsonObject, name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or NAME.fullmatch(value) is None:
        raise TelemetryContractError("malformed_input", f"{name} is invalid")
    return value


def _event_id(values: JsonObject) -> str:
    value = values.get("event_id")
    if not isinstance(value, str) or ID.fullmatch(value) is None:
        raise TelemetryContractError("malformed_input", "event_id is invalid")
    return value


def _count(values: JsonObject, name: str, *, optional: bool = False) -> int | None:
    value = values.get(name)
    if optional and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TelemetryContractError("malformed_input", f"{name} must be a non-negative integer")
    return value


def _required_count(values: JsonObject, name: str) -> int:
    value = _count(values, name)
    if value is None:
        raise TelemetryContractError("malformed_input", f"{name} is required")
    return value


def parse_metric_event(payload: JsonObject) -> MetricEvent:
    try:
        reject_sensitive(payload)
    except PrivacyError as exc:
        raise TelemetryContractError(exc.code, exc.detail) from exc
    fields = frozenset(payload)
    optional = {"tool_count", "token_count", "attempt_receipt"}
    if fields != REQUIRED | (fields & optional) or payload.get("format") != FORMAT:
        raise TelemetryContractError("malformed_input", "event fields or format are invalid")
    occurred_at = payload.get("occurred_at")
    if not isinstance(occurred_at, str):
        raise TelemetryContractError("malformed_input", "occurred_at must be text")
    try:
        occurred_at_value = parse_rfc3339(occurred_at, "occurred_at")
    except PrivacyError as exc:
        raise TelemetryContractError(exc.code, exc.detail) from exc
    lane, outcome, verification = _text(payload, "lane"), _text(payload, "outcome"), _text(payload, "verification")
    if lane not in {"direct", "role", "squad"}:
        raise TelemetryContractError("malformed_input", "lane is invalid")
    if outcome not in {"succeeded", "partial", "failed", "cancelled"}:
        raise TelemetryContractError("malformed_input", "outcome is invalid")
    if verification not in {"passed", "partial", "failed", "not-run"}:
        raise TelemetryContractError("malformed_input", "verification is invalid")
    try:
        attempt_receipt = (
            parse_attempt_receipt(payload["attempt_receipt"])
            if "attempt_receipt" in payload
            else None
        )
    except AttemptReceiptError as exc:
        raise TelemetryContractError(exc.code, exc.detail) from exc
    token_count = _count(payload, "token_count", optional=True)
    if (
        attempt_receipt is not None
        and token_count is not None
        and token_count != attempt_receipt.usage.input_tokens + attempt_receipt.usage.output_tokens
    ):
        raise TelemetryContractError("malformed_input", "token_count must equal receipt input plus output tokens")
    if attempt_receipt is not None:
        observation = attempt_receipt.verification
        if verification == "passed" and (
            observation.quality_score is None
            or observation.critical_regression is not False
        ):
            raise TelemetryContractError(
                "malformed_input",
                "passed verification requires measured quality without a critical regression",
            )
        if verification == "not-run" and observation.quality_score is not None:
            raise TelemetryContractError(
                "malformed_input",
                "not-run verification cannot carry a verification observation",
            )
        if verification in {"partial", "failed"} and observation.quality_score is None:
            raise TelemetryContractError(
                "malformed_input",
                f"{verification} verification requires a measured verification observation",
            )
        if observation.critical_regression is True and outcome == "succeeded":
            raise TelemetryContractError(
                "malformed_input",
                "a critical verification regression cannot be a succeeded outcome",
            )
        if observation.verified_at is not None:
            try:
                verified_at = parse_rfc3339(observation.verified_at, "verified_at")
            except PrivacyError as exc:
                raise TelemetryContractError(exc.code, exc.detail) from exc
            if verified_at > occurred_at_value:
                raise TelemetryContractError(
                    "malformed_input",
                    "verified_at cannot be later than occurred_at",
                )
    return MetricEvent(
        _event_id(payload), occurred_at, _text(payload, "task_class"), lane,
        _text(payload, "core_route"), _text(payload, "core_backend"),
        _required_count(payload, "role_count"), _required_count(payload, "worker_count"),
        _required_count(payload, "elapsed_ms"), _required_count(payload, "retries"), outcome, verification,
        _count(payload, "tool_count", optional=True), token_count, attempt_receipt,
    )


def event_json(event: MetricEvent) -> JsonObject:
    value: JsonObject = {"format": FORMAT, **asdict(event)}
    if event.tool_count is None:
        del value["tool_count"]
    if event.token_count is None:
        del value["token_count"]
    if event.attempt_receipt is None:
        del value["attempt_receipt"]
    else:
        value["attempt_receipt"] = attempt_receipt_json(event.attempt_receipt)
    return value
