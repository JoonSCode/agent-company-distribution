#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/agent_company_agents.py --profiles-dir agents --output-dir /tmp/agent-company-agents
# 3. Or run with system Python when stdlib-only execution is preferred:
#      python3 scripts/agent_company_agents.py --profiles-dir agents --output-dir /tmp/agent-company-agents
# ─────────────────

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

from agent_company_agent_output import (
    CompiledAgent,
    write_compiled_agents,
)
from agent_company_expertise_catalog import ExpertiseCatalog, load_expertise_catalog
from agent_company_expertise_routing import load_routing_policy
from agent_company_role_contract import NativeAgentError, RoleProfile, load_profile

EXPECTED_ROLES: Final[tuple[str, ...]] = ("design", "development", "founder", "marketing", "planning", "qa-release")
WRITABLE_ROLES: Final[frozenset[str]] = frozenset({"development", "qa-release"})


def developer_instructions(
    profile: RoleProfile,
    catalog: ExpertiseCatalog | None = None,
) -> str:
    selected_catalog = catalog or load_expertise_catalog()
    expertise = selected_catalog.roles[profile.role]
    routing = load_routing_policy(selected_catalog.root, selected_catalog)
    lines = [
        f"Role: {profile.display_name}",
        f"Mission: {profile.mission}",
        f"Authority boundary: {profile.authority_boundary}",
        "Owns:",
        *(f"- {item}" for item in profile.owns),
        "Does not own:",
        *(f"- {item}" for item in profile.does_not_own),
        "Skills and methods:",
        *(f"- {item}" for item in profile.skills),
        "Expertise orchestration:",
        f"- Role OS: {expertise.role_os_skill}",
        f"- Role kernel: {expertise.role_kernel_id}",
        "- Expertise registry: policies/expertise-registry.json",
        f"- Expertise registry SHA-256: {selected_catalog.registry_sha256}",
        "- Reference manifest: policies/reference-manifest.json",
        f"- Reference manifest SHA-256: {selected_catalog.manifest_sha256}",
        "- Routing policy: policies/expertise-routing.json",
        f"- Routing policy SHA-256: {routing.sha256}",
        f"- Default specialist limit: {selected_catalog.default_specialist_limit}",
        "- Execute with the parent-selected Role Kernel and exactly one Task Pack; never load an Evaluation Set.",
        "- Load only parent-approved, freshness-valid Current Source Sets and Job Evidence.",
        "- Reuse only hash-valid cache objects and record every used or unused read in the reference ledger.",
        "- Persist role identity through a logical serial checkpoint; do not create a persistent or background worker.",
        f"- Independent verifier: {expertise.default_verifier}",
        "- A verified Knowledge Usage Receipt is required before current work can cross a handoff.",
        "Memory references:",
        *(f"- {item}" for item in profile.memory_refs),
        "Bounded tools:",
        *(f"- {item}" for item in profile.tools),
        "Approval rules:",
        *(f"- {item}" for item in profile.approval_rules),
        "Bounded handoff:",
        f"- Format: {profile.handoff_shape.format}",
        f"- Policy: {profile.handoff_shape.policy_ref}",
        "- Required fields:",
        *(f"  - {item}" for item in profile.handoff_shape.required_fields),
    ]
    if profile.role == "founder":
        lines.extend(
            [
                "Founder boundary: Provide portfolio-strategy evidence and decision framing to the CEO.",
                "Never impersonate the CEO or claim CEO decision authority.",
            ]
        )
    return "\n".join(lines) + "\n"


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_agent(profile: RoleProfile, catalog: ExpertiseCatalog | None = None) -> bytes:
    native = profile.native_agent
    lines = [
        f"name = {toml_string(native.name)}",
        f"description = {toml_string(native.description)}",
        f"sandbox_mode = {toml_string(native.sandbox_mode)}",
    ]
    if native.model is not None:
        lines.append(f"model = {toml_string(native.model)}")
    if native.reasoning_effort is not None:
        lines.append(f"model_reasoning_effort = {toml_string(native.reasoning_effort)}")
    if native.nicknames is not None:
        nicknames = ", ".join(toml_string(item) for item in native.nicknames)
        lines.append(f"nickname_candidates = [{nicknames}]")
    lines.append(f"developer_instructions = {toml_string(developer_instructions(profile, catalog))}")
    return ("\n".join(lines) + "\n").encode()


def compile_agents(profiles_dir: Path, output_dir: Path) -> Path:
    profiles = tuple(load_profile(path) for path in sorted(profiles_dir.glob("*.json")))
    catalog = load_expertise_catalog()
    targets = tuple(f"{profile.native_agent.name}.toml" for profile in profiles)
    if len(set(targets)) != len(targets):
        raise NativeAgentError("duplicate_output_path", "multiple profiles compile to the same output path")
    roles = tuple(sorted(profile.role for profile in profiles))
    if roles != EXPECTED_ROLES:
        raise NativeAgentError("unexpected_role_set", f"expected exact roles {EXPECTED_ROLES}, got {roles}")
    compiled: list[CompiledAgent] = []
    for profile, target in zip(profiles, targets, strict=True):
        expected_name = f"agent-company-{profile.role}"
        if profile.native_agent.name != expected_name:
            raise NativeAgentError("agent_name_mismatch", f"{profile.role} must compile as {expected_name}")
        expected_sandbox = "workspace-write" if profile.role in WRITABLE_ROLES else "read-only"
        if profile.native_agent.sandbox_mode != expected_sandbox:
            raise NativeAgentError("sandbox_mismatch", f"{profile.role} must use {expected_sandbox}")
        compiled.append(CompiledAgent(profile.source.name, target, render_agent(profile, catalog)))
    return write_compiled_agents(tuple(compiled), output_dir)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        index = compile_agents(args.profiles_dir, args.output_dir)
    except NativeAgentError as exc:
        print(json.dumps({"status": "fail", "code": exc.code, "detail": exc.detail}), file=sys.stderr)
        return 1
    except OSError as exc:
        print(json.dumps({"status": "fail", "code": "io_error", "detail": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "ok", "agent_count": len(EXPECTED_ROLES), "index": str(index)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
