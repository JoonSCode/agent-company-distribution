#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from agent_company_deps import JsonValue


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    codex_home: Path
    root: Path
    state: Path
    snapshots: Path
    rollback: Path


def runtime_paths(codex_home: Path | None = None) -> RuntimePaths:
    base = codex_home or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    root = base / "agent-company"
    return RuntimePaths(base, root, root / "state", root / "snapshots", root / "rollback")


def text_field(values: dict[str, JsonValue], field: str) -> str:
    value = values.get(field)
    return value if isinstance(value, str) else ""


def int_field(values: dict[str, JsonValue], field: str) -> int | None:
    value = values.get(field)
    return value if type(value) is int else None


def map_field(values: dict[str, JsonValue], field: str) -> dict[str, JsonValue]:
    value = values.get(field)
    return value if isinstance(value, dict) else {}


def list_field(values: dict[str, JsonValue], field: str) -> list[JsonValue]:
    value = values.get(field)
    return value if isinstance(value, list) else []


def issue(code: str, message: str, path: Path | None = None) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {"code": code, "message": message}
    if path is not None:
        payload["path"] = str(path)
    return {"issue": payload}


def status_from_issues(issues: list[JsonValue]) -> str:
    return "ok" if not issues else "fail"
