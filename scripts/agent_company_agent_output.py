#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/agent_company_agent_output.py
# 3. Or run with system Python when stdlib-only execution is preferred:
#      python3 scripts/agent_company_agent_output.py
# ─────────────────

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from agent_company_role_contract import NativeAgentError
from agent_company_role_schema import JsonValue, as_json_object


INDEX_NAME: Final[str] = "agent-company-agents.index.json"
INDEX_VERSION: Final[str] = "agent-company.native-agent-index/v0.2"
INDEX_FIELDS: Final[frozenset[str]] = frozenset({"schema_version", "managed_files", "agents"})
ENTRY_FIELDS: Final[frozenset[str]] = frozenset({"name", "file", "sha256", "source"})
SAFE_HASH: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
SAFE_FILE: Final[re.Pattern[str]] = re.compile(r"^agent-company-[a-z0-9]+(?:-[a-z0-9]+)*\.toml$")


@dataclass(frozen=True, slots=True)
class CompiledAgent:
    source: str
    filename: str
    content: bytes


@dataclass(frozen=True, slots=True)
class ManagedAgent:
    name: str
    filename: str
    sha256: str
    source: str


@dataclass(frozen=True, slots=True)
class ManagedIndex:
    agents: tuple[ManagedAgent, ...]

    @property
    def filenames(self) -> tuple[str, ...]:
        return tuple(agent.filename for agent in self.agents)


def ownership_conflict(detail: str) -> NativeAgentError:
    return NativeAgentError("output_ownership_conflict", detail)


def index_text(values: dict[str, JsonValue], field: str) -> str:
    value = values.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ownership_conflict(f"managed index {field} must be non-empty text")
    return value


def is_text(value: JsonValue) -> bool:
    return isinstance(value, str)


def parse_managed_index(path: Path) -> ManagedIndex:
    if path.is_symlink() or not path.is_file():
        raise ownership_conflict("managed index must be a regular file")
    try:
        parsed: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ownership_conflict(f"managed index is unreadable or malformed: {exc}") from exc
    payload = as_json_object(parsed)
    if payload is None or set(payload) != INDEX_FIELDS or payload.get("schema_version") != INDEX_VERSION:
        raise ownership_conflict("managed index has an unsupported shape or version")
    managed_files = payload.get("managed_files")
    raw_agents = payload.get("agents")
    if not isinstance(managed_files, list) or not isinstance(raw_agents, list):
        raise ownership_conflict("managed index file and agent collections must be lists")
    agents: list[ManagedAgent] = []
    for raw_agent in raw_agents:
        agent = as_json_object(raw_agent)
        if agent is None or set(agent) != ENTRY_FIELDS:
            raise ownership_conflict("managed index agent entry has an unsupported shape")
        name = index_text(agent, "name")
        filename = index_text(agent, "file")
        sha256 = index_text(agent, "sha256")
        source = index_text(agent, "source")
        if SAFE_FILE.fullmatch(filename) is None or name != filename.removesuffix(".toml"):
            raise ownership_conflict("managed index contains an unsafe agent filename")
        if SAFE_HASH.fullmatch(sha256) is None or Path(source).name != source or not source.endswith(".json"):
            raise ownership_conflict("managed index contains unsafe hash or source metadata")
        agents.append(ManagedAgent(name, filename, sha256, source))
    filenames = tuple(agent.filename for agent in agents)
    if len(set(filenames)) != len(filenames):
        raise ownership_conflict("managed index contains duplicate agent filenames")
    if not all(is_text(item) for item in managed_files) or tuple(managed_files) != filenames:
        raise ownership_conflict("managed_files does not match indexed agents")
    return ManagedIndex(tuple(agents))


def validate_output_ownership(output_dir: Path) -> ManagedIndex:
    if not output_dir.exists():
        return ManagedIndex(())
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise ownership_conflict("output path must be a regular directory")
    paths = tuple(output_dir.iterdir())
    if not paths:
        return ManagedIndex(())
    index_path = output_dir / INDEX_NAME
    if not index_path.exists():
        raise ownership_conflict("non-empty output directory has no managed index")
    index = parse_managed_index(index_path)
    existing = {path.name: path for path in paths if path.name != INDEX_NAME}
    if set(existing) != set(index.filenames):
        raise ownership_conflict("managed index does not own every existing output entry")
    for agent in index.agents:
        path = existing[agent.filename]
        if path.is_symlink() or not path.is_file():
            raise ownership_conflict(f"managed output is not a regular file: {agent.filename}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != agent.sha256:
            raise ownership_conflict(f"managed output hash changed: {agent.filename}")
    return index


def write_compiled_agents(compiled: tuple[CompiledAgent, ...], output_dir: Path) -> Path:
    prior = validate_output_ownership(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = {item.filename for item in compiled}
    for item in compiled:
        (output_dir / item.filename).write_bytes(item.content)
    for filename in set(prior.filenames) - expected:
        (output_dir / filename).unlink()
    index = {
        "schema_version": INDEX_VERSION,
        "managed_files": [item.filename for item in compiled],
        "agents": [
            {
                "name": item.filename.removesuffix(".toml"),
                "file": item.filename,
                "sha256": hashlib.sha256(item.content).hexdigest(),
                "source": item.source,
            }
            for item in compiled
        ],
    }
    index_path = output_dir / INDEX_NAME
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return index_path
