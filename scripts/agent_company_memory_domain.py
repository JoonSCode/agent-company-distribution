#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Use through agent_company_memory.py.
# 3. Test: python3 scripts/test_agent_company_memory.py
# ─────────────────

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

import json
import os
from collections.abc import Mapping
from pathlib import Path

from agent_company_memory_models import (
    MemoryContractError,
    MemoryRecord,
    memory_json,
    parse_memory_record,
    validate_memory_graph,
)
from agent_company_privacy import JsonObject, PrivacyError, ensure_role, parse_json
from agent_company_private_storage import PrivateDirectory, StorageError, locked, private_directory, quarantine


def runtime_home(codex_home: Path | None = None) -> Path:
    return codex_home or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()


def _decode(raw: bytes) -> list[MemoryRecord]:
    records: list[MemoryRecord] = []
    try:
        for line in raw.decode().splitlines():
            value = parse_json(line)
            if not isinstance(value, dict):
                raise MemoryContractError("corrupt_record", "record line must be an object")
            records.append(parse_memory_record(value))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MemoryContractError("corrupt_record", "record store is not valid JSONL") from exc
    validate_memory_graph(records)
    return records


def _encoded(records: list[MemoryRecord]) -> bytes:
    return "".join(json.dumps(memory_json(item), sort_keys=True) + "\n" for item in records).encode()


def _reachable(starts: set[str], by_id: Mapping[str, MemoryRecord]) -> set[str]:
    reached: set[str] = set()
    pending = list(starts)
    while pending:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        pending.extend(by_id[current].supersedes)
    return reached


def _retained_after_deletion(target_id: str, records: list[MemoryRecord]) -> list[MemoryRecord]:
    by_id = {item.record_id: item for item in records}
    lineage = _reachable({target_id}, by_id)
    remaining = set(by_id) - lineage
    protected = _reachable(remaining, by_id)
    if target_id in protected:
        raise MemoryContractError("deletion_conflict", "remaining records reference the deletion target")
    removed = lineage - protected
    retained = [item for item in records if item.record_id not in removed]
    validate_memory_graph(retained)
    return retained


def _read_valid(directory: PrivateDirectory) -> list[MemoryRecord]:
    raw = directory.read("records.jsonl")
    if raw is None:
        return []
    try:
        return _decode(raw)
    except MemoryContractError:
        quarantine(directory, "records.jsonl", raw, "semantic-or-syntax-corruption")
        raise


def _load_locked(directory_name: str, codex_home: Path) -> list[MemoryRecord]:
    with private_directory(codex_home, directory_name) as directory:
        with locked(directory, ".memory.lock"):
            try:
                return _read_valid(directory)
            except MemoryContractError:
                return []


def append_record(payload: JsonObject, codex_home: Path | None = None) -> MemoryRecord:
    record = parse_memory_record(payload)
    home = runtime_home(codex_home)
    try:
        with private_directory(home, "memory") as directory:
            with locked(directory, ".memory.lock"):
                records = _read_valid(directory)
                candidate = [*records, record]
                validate_memory_graph(candidate)
                directory.atomic_replace("records.jsonl", _encoded(candidate))
    except StorageError as exc:
        raise MemoryContractError(exc.code, exc.detail) from exc
    return record


def load_records(
    *,
    requesting_role: str,
    codex_home: Path | None = None,
    active_only: bool = True,
) -> list[MemoryRecord]:
    try:
        role = ensure_role(requesting_role)
    except PrivacyError as exc:
        raise MemoryContractError(exc.code, exc.detail) from exc
    try:
        records = _load_locked("memory", runtime_home(codex_home))
    except StorageError as exc:
        raise MemoryContractError(exc.code, exc.detail) from exc
    if active_only:
        superseded = {record_id for record in records for record_id in record.supersedes}
        records = [record for record in records if record.record_id not in superseded]
    return [record for record in records if role in record.visible_to_roles]


def delete_record(
    record_id: str,
    deletion_id: str,
    *,
    requesting_role: str,
    codex_home: Path | None = None,
) -> None:
    try:
        role = ensure_role(requesting_role)
    except PrivacyError as exc:
        raise MemoryContractError(exc.code, exc.detail) from exc
    home = runtime_home(codex_home)
    try:
        with private_directory(home, "memory") as directory:
            with locked(directory, ".memory.lock"):
                records = _read_valid(directory)
                target = next((item for item in records if item.record_id == record_id), None)
                if target is None or target.deletion_id != deletion_id or role not in target.visible_to_roles:
                    raise MemoryContractError("deletion_denied", "record, role, or deletion id did not match")
                retained = _retained_after_deletion(target.record_id, records)
                if retained:
                    directory.atomic_replace("records.jsonl", _encoded(retained))
                else:
                    directory.remove("records.jsonl")
    except StorageError as exc:
        raise MemoryContractError(exc.code, exc.detail) from exc
