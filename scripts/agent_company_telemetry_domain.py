#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Use through agent_company_telemetry.py.
# 3. Test: python3 scripts/test_agent_company_telemetry.py
# ─────────────────

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

import json
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent_company_privacy import JsonValue, PrivacyError, ensure_role, parse_json, parse_rfc3339
from agent_company_private_storage import PrivateDirectory, StorageError, locked, private_directory, quarantine
from agent_company_telemetry_models import (
    MetricEvent,
    TelemetryContractError,
    TelemetryWriteResult,
    event_json,
    parse_metric_event,
)


def runtime_home(codex_home: Path | None = None) -> Path:
    return codex_home or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()


def _decode(raw: bytes) -> list[MetricEvent]:
    events: list[MetricEvent] = []
    try:
        for line in raw.decode().splitlines():
            value = parse_json(line)
            if not isinstance(value, dict):
                raise TelemetryContractError("corrupt_event", "event line must be an object")
            events.append(parse_metric_event(value))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelemetryContractError("corrupt_event", "event store is not valid JSONL") from exc
    return events


def _read_all(directory: PrivateDirectory) -> tuple[list[MetricEvent], dict[str, list[MetricEvent]]]:
    by_file: dict[str, list[MetricEvent]] = {}
    all_events: list[MetricEvent] = []
    for name in directory.names():
        if len(name) != 13 or not name.endswith(".jsonl"):
            continue
        raw = directory.read(name)
        if raw is None:
            continue
        try:
            events = _decode(raw)
        except TelemetryContractError:
            quarantine(directory, name, raw, "semantic-or-syntax-corruption")
            raise
        by_file[name] = events
        all_events.extend(events)
    if len({event.event_id for event in all_events}) != len(all_events):
        for name in tuple(by_file):
            raw = directory.read(name)
            if raw is not None:
                quarantine(directory, name, raw, "duplicate-event-id")
        raise TelemetryContractError("semantic_corruption", "duplicate event_id across rotation")
    return all_events, by_file


def _write_grouped(directory: PrivateDirectory, events: list[MetricEvent]) -> None:
    grouped: defaultdict[str, list[MetricEvent]] = defaultdict(list)
    for event in events:
        month = parse_rfc3339(event.occurred_at, "occurred_at").strftime("%Y-%m.jsonl")
        grouped[month].append(event)
    existing = {name for name in directory.names() if len(name) == 13 and name.endswith(".jsonl")}
    for name, items in grouped.items():
        payload = "".join(json.dumps(event_json(item), sort_keys=True) + "\n" for item in items).encode()
        directory.atomic_replace(name, payload)
    for name in existing - set(grouped):
        directory.remove(name)


def record_event(
    payload: dict[str, JsonValue],
    codex_home: Path | None = None,
    *,
    now: datetime | None = None,
) -> TelemetryWriteResult:
    try:
        event = parse_metric_event(payload)
        current = (now or datetime.now(UTC)).astimezone(UTC)
        event_time = parse_rfc3339(event.occurred_at, "occurred_at")
        if event_time < current - timedelta(days=90) or event_time > current + timedelta(minutes=5):
            raise TelemetryContractError("retention_rejected", "event is outside retention or future-skew bounds")
        with private_directory(runtime_home(codex_home), "telemetry") as directory:
            with locked(directory, ".telemetry.lock"):
                events, _ = _read_all(directory)
                retained = [item for item in events if parse_rfc3339(item.occurred_at, "occurred_at") >= current - timedelta(days=90)]
                pruned = len(events) - len(retained)
                if event.event_id in {item.event_id for item in retained}:
                    raise TelemetryContractError("duplicate_event", "event_id already exists")
                _write_grouped(directory, [*retained, event])
        return TelemetryWriteResult(True, None, pruned)
    except (OSError, PrivacyError, StorageError, TelemetryContractError):
        message = "telemetry warning: privacy, storage, uniqueness, or time validation rejected the event"
        print(message, file=sys.stderr)
        return TelemetryWriteResult(False, message, 0)


def load_events(
    *,
    requesting_role: str,
    codex_home: Path | None = None,
    now: datetime | None = None,
) -> list[MetricEvent]:
    try:
        _ = ensure_role(requesting_role)
        current = (now or datetime.now(UTC)).astimezone(UTC)
        with private_directory(runtime_home(codex_home), "telemetry") as directory:
            with locked(directory, ".telemetry.lock"):
                events, _ = _read_all(directory)
                retained = [item for item in events if parse_rfc3339(item.occurred_at, "occurred_at") >= current - timedelta(days=90)]
                _write_grouped(directory, retained)
                return retained
    except PrivacyError as exc:
        raise TelemetryContractError(exc.code, exc.detail) from exc
    except TelemetryContractError:
        return []


def prune_telemetry(codex_home: Path | None = None, *, now: datetime | None = None) -> int:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    with private_directory(runtime_home(codex_home), "telemetry") as directory:
        with locked(directory, ".telemetry.lock"):
            events, _ = _read_all(directory)
            retained = [item for item in events if parse_rfc3339(item.occurred_at, "occurred_at") >= current - timedelta(days=90)]
            _write_grouped(directory, retained)
            return len(events) - len(retained)
