#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/agent_company_sync_guard.py
# 3. Or run with system Python when stdlib-only execution is preferred:
#      python3 scripts/agent_company_sync_guard.py
# ──────────────────

from __future__ import annotations

from pathlib import Path
from typing import Final

from agent_company_deps import JsonValue


DISALLOWED_NAMES: Final[tuple[str, ...]] = ("auth.json", ".env", "credentials", "session_index")
DISALLOWED_SUFFIXES: Final[tuple[str, ...]] = (".sqlite", ".sqlite3")


def issue(code: str, message: str, path: Path) -> dict[str, JsonValue]:
    return {"issue": {"code": code, "message": message, "path": str(path)}}


def disallowed_sync_files(repo_root: Path, install_root: Path) -> list[JsonValue]:
    findings: list[JsonValue] = []
    for root in (repo_root, install_root):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if ".git" in path.parts:
                continue
            name = path.name.lower()
            if path.is_file() and (name in DISALLOWED_NAMES or name.endswith(DISALLOWED_SUFFIXES)):
                findings.append(issue("disallowed_sync_file", "raw Codex state or secret-shaped file is disallowed", path))
    return findings
