#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import os
from pathlib import Path

from agent_company_install_types import InstallError


def inject(env_name: str, value: str, exit_code: int) -> None:
    if os.environ.get(env_name) == value:
        os._exit(exit_code)


def before_phase(name: str) -> None:
    inject("AGENT_COMPANY_KILL_BEFORE_PHASE", name, 97)
    if os.environ.get("AGENT_COMPANY_FAIL_BEFORE_PHASE") == name:
        raise InstallError("injected_failure", f"failure before {name}")


def after_phase(name: str) -> None:
    inject("AGENT_COMPANY_KILL_AFTER_PHASE", name, 97)
    if os.environ.get("AGENT_COMPANY_FAIL_AFTER_PHASE") == name:
        raise InstallError("injected_failure", f"failure after {name}")


def midpoint(name: str) -> None:
    inject("AGENT_COMPANY_KILL_MID_STEP", name, 96)
    if os.environ.get("AGENT_COMPANY_FAIL_MID_STEP") == name:
        raise InstallError("injected_failure", f"failure during {name}")


def corrupt_staged_target(staging_root: Path) -> None:
    mode = os.environ.get("AGENT_COMPANY_CORRUPT_STAGED_TARGET", "")
    if not mode and os.environ.get("AGENT_COMPANY_CORRUPT_STAGED_AGENT") == "1":
        mode = "agent"
    if not mode:
        return
    _corrupt_staged_target(staging_root, mode)


def _corrupt_staged_target(staging_root: Path, mode: str) -> None:
    if mode == "extra-agent":
        (staging_root / "compiled-agents" / "agent-company-rogue.toml").write_text(
            'name = "rogue"\n', encoding="utf-8",
        )
        return
    skill_files = sorted((staging_root / "compiled-skills").glob("*/SKILL.md"))
    targets = {
        "snapshot": staging_root / "snapshot" / "repo" / "README.md",
        "skill": skill_files[0] if skill_files else staging_root / "missing-skill",
        "agent": staging_root / "compiled-agents" / "agent-company-design.toml",
        "agent-index": staging_root / "compiled-agents" / "agent-company-agents.index.json",
    }
    target = targets.get(mode)
    if target is None:
        raise InstallError("malformed_input", f"unsupported staged corruption mode: {mode}")
    target.write_bytes(target.read_bytes() + b"\ncorrupt\n")


def race_staged_target(staging_root: Path, expected_mode: str) -> None:
    if os.environ.get("AGENT_COMPANY_RACE_STAGED_TARGET") != expected_mode:
        return
    _corrupt_staged_target(staging_root, expected_mode)


__all__ = [
    "after_phase", "before_phase", "corrupt_staged_target", "midpoint",
    "race_staged_target",
]
