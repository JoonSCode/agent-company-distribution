#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# How to run:
#   python3 scripts/test_doctor_runtime.py --case fresh-v02

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, final, override

from agent_company_launchd_contract import LaunchdTarget, default_target, validate_target
from agent_company_privacy import PrivacyError, reject_sensitive


KNOWN_STATES: Final[frozenset[str]] = frozenset(
    {"running", "waiting", "not running", "exited", "unknown"}
)
STATE_LINE: Final[re.Pattern[str]] = re.compile(
    r'^\s*"?state"?\s*=\s*(.+?)\s*$',
    re.IGNORECASE,
)
EXIT_LINE: Final[re.Pattern[str]] = re.compile(
    r'^\s*(?:"?last\s+exit\s+(?:code|status)"?|"?LastExitStatus"?)\s*=\s*(-?\d+)\s*;?\s*$',
    re.IGNORECASE,
)
MAX_OUTPUT_BYTES: Final[int] = 65_536
MAX_LINES: Final[int] = 512
MAX_LINE_LENGTH: Final[int] = 4_096
MAX_DEPTH: Final[int] = 16


@final
class LaunchdOutputError(Exception):
    code: str

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

    @override
    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class ParsedLaunchctl:
    state: str
    last_exit: int | None
    safe_stderr: str
    privacy_sanitized: bool


def is_sensitive(value: str) -> bool:
    try:
        reject_sensitive(value)
    except PrivacyError:
        return True
    return False


def state_value(raw: str) -> str:
    value = raw.strip().removesuffix(";").strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    normalized = " ".join(value.lower().split())
    return normalized if normalized in KNOWN_STATES else "invalid"


def indentation(line: str) -> int:
    prefix = line[: len(line) - len(line.lstrip())]
    return sum(4 if character == "\t" else 1 for character in prefix)


def stderr_projection(stderr: str) -> tuple[str, bool]:
    if not text_is_bounded(stderr):
        return "launchd observation sanitized", True
    if is_sensitive(stderr):
        return "launchd observation sanitized", True
    return stderr, False


def invalid_result(stderr: str, *, sanitized: bool) -> ParsedLaunchctl:
    safe_stderr, stderr_sanitized = stderr_projection(stderr)
    return ParsedLaunchctl("invalid", None, safe_stderr, sanitized or stderr_sanitized)


def text_is_bounded(value: str) -> bool:
    lines = value.splitlines()
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise LaunchdOutputError("invalid_unicode") from exc
    return (
        size <= MAX_OUTPUT_BYTES
        and len(lines) <= MAX_LINES
        and all(len(line) <= MAX_LINE_LENGTH for line in lines)
    )


def parse_launchctl(
    stdout: str,
    stderr: str,
    target: LaunchdTarget | None = None,
) -> ParsedLaunchctl:
    selected_target = target if target is not None else default_target()
    validate_target(selected_target)
    expected_header = f"{selected_target.reference} = {{"
    lines = stdout.splitlines()
    if not text_is_bounded(stdout):
        return invalid_result(stderr, sanitized=False)
    states: list[str] = []
    exits: list[int] = []
    sanitized = False
    root_seen = False
    root_closed = False
    root_indent = 0
    authority_indent: int | None = None
    depth = 0
    invalid = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not root_seen:
            if index != 0 or invalid or line != expected_header:
                invalid = True
            else:
                root_seen = True
                root_indent = 0
                depth = 1
            sanitized = sanitized or is_sensitive(line)
            continue
        if root_closed:
            invalid = invalid or bool(stripped)
            sanitized = sanitized or (bool(stripped) and is_sensitive(line))
            continue
        state_match = STATE_LINE.fullmatch(line)
        exit_match = EXIT_LINE.fullmatch(line)
        if depth == 1 and (state_match is not None or exit_match is not None):
            line_indent = indentation(line)
            if line_indent <= root_indent or (
                authority_indent is not None and line_indent != authority_indent
            ):
                invalid = True
            authority_indent = line_indent if authority_indent is None else authority_indent
            if state_match is not None:
                parsed = state_value(state_match.group(1))
                states.append(parsed)
                sanitized = sanitized or (parsed == "invalid" and is_sensitive(line))
            elif exit_match is not None:
                exits.append(int(exit_match.group(1)))
        elif stripped and is_sensitive(line):
            sanitized = True
        next_depth = depth + line.count("{") - line.count("}")
        if next_depth < 0 or next_depth > MAX_DEPTH:
            invalid = True
        if next_depth == 0:
            if stripped != "}" or indentation(line) != root_indent:
                invalid = True
            root_closed = True
        depth = next_depth
    if not root_seen:
        if stdout.strip():
            return invalid_result(stderr, sanitized=sanitized)
        safe_stderr, stderr_sanitized = stderr_projection(stderr)
        return ParsedLaunchctl("unknown", None, safe_stderr, sanitized or stderr_sanitized)
    if not root_closed or depth != 0 or len(states) > 1 or len(exits) > 1:
        invalid = True
    if invalid:
        return invalid_result(stderr, sanitized=sanitized)
    safe_stderr, stderr_sanitized = stderr_projection(stderr)
    state = states[0] if states else "unknown"
    last_exit = exits[0] if exits else None
    return ParsedLaunchctl(state, last_exit, safe_stderr, sanitized or stderr_sanitized)
