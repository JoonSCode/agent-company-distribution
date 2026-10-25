#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/agent_company_role_authority.py
# 3. Or run with system Python when stdlib-only execution is preferred:
#      python3 scripts/agent_company_role_authority.py
# ─────────────────

from __future__ import annotations

from pathlib import Path
from typing import Final, assert_never

from agent_company_role_schema import JsonValue, ProfileIssue, issue


FORBIDDEN_AUTHORITY_TERMS: Final[tuple[str, ...]] = (
    "override user authority",
    "self-approve final verification",
    "final verification authority",
    "gate approval authority",
    "approve uigwe gates",
    "approves uigwe gates",
    "replaces king sejong",
    "override king sejong",
    "overrides king sejong",
)
NEGATED_CLAIM_PREFIXES: Final[tuple[str, ...]] = (
    "not ",
    "never ",
    "does not ",
    "do not ",
    "must not ",
    "may not ",
    "cannot ",
    "can't ",
    "no ",
    "without ",
    "does not have ",
    "do not have ",
    "must not have ",
    "may not have ",
    "cannot have ",
    "can't have ",
    "does not claim ",
    "do not claim ",
    "must not claim ",
    "may not claim ",
    "cannot claim ",
    "can't claim ",
)


def collect_authority_claims(path: Path, field: str, value: JsonValue) -> list[ProfileIssue]:
    errors: list[ProfileIssue] = []
    match value:
        case str():
            text = value.lower()
            for term in FORBIDDEN_AUTHORITY_TERMS:
                start = text.find(term)
                while start >= 0:
                    prefix = text[:start]
                    denied = field == "does_not_own" or field.startswith("$.does_not_own")
                    negated = any(prefix.endswith(marker) for marker in NEGATED_CLAIM_PREFIXES)
                    if not denied and not negated:
                        errors.append(
                            issue(path, field, "forbidden_authority_claim", f"profile claims forbidden authority: {term}")
                        )
                    start = text.find(term, start + 1)
        case list():
            for index, item in enumerate(value):
                errors.extend(collect_authority_claims(path, f"{field}[{index}]", item))
        case dict():
            for key, item in value.items():
                errors.extend(collect_authority_claims(path, f"{field}.{key}", item))
        case int() | float() | bool() | None:
            return errors
        case unreachable:
            assert_never(unreachable)
    return errors
