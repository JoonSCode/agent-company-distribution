#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

from pathlib import Path

from agent_company_agent_output import INDEX_NAME, parse_managed_index
from agent_company_install_fs import ensure_regular_tree, sha256_file
from agent_company_install_types import InstallError, InstallTarget, ManagedIndex


def desired_agents(compiled: Path) -> tuple[InstallTarget, ...]:
    index = parse_managed_index(compiled / INDEX_NAME)
    return tuple(
        InstallTarget(f"agents/{agent.filename}", compiled / agent.filename, agent.sha256, "file")
        for agent in index.agents
    )


def plan_agents(
    codex_home: Path,
    desired: tuple[InstallTarget, ...],
    prior: ManagedIndex | None,
) -> tuple[tuple[InstallTarget, ...], tuple[InstallTarget, ...]]:
    agents_root = codex_home / "agents"
    if agents_root.exists():
        ensure_regular_tree(agents_root)
    prior_hashes = {} if prior is None else prior.agents
    desired_names = {Path(target.relative).name for target in desired}
    for target in desired:
        path = codex_home / target.relative
        if not path.exists():
            continue
        name = path.name
        expected = prior_hashes.get(name)
        if expected is None or sha256_file(path) != expected:
            raise InstallError("agent_conflict", f"{name} exists without matching managed ownership")
    stale: list[InstallTarget] = []
    for name, expected in sorted(prior_hashes.items()):
        if name in desired_names:
            continue
        path = agents_root / name
        if not path.exists():
            raise InstallError("managed_drift", f"managed agent disappeared: {name}")
        if sha256_file(path) != expected:
            raise InstallError("managed_drift", f"managed agent changed: {name}")
        stale.append(InstallTarget(f"agents/{name}", None, expected, "file"))
    return desired, tuple(stale)
