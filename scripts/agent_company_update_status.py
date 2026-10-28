#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Run through scripts/update.sh --auto.
# 2. Each attempt and result is bound to one run id.
# 3. Installer arguments are passed as an argv array without a shell.
# ─────────────────

from __future__ import annotations

import subprocess
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Protocol

# Select Python's normal cache prefix before importing Company modules.
# Restrict this to the CLI process; callers importing a module are unchanged.
if __name__ == "__main__":
    import os as _os
    import sys as _sys
    _sys.pycache_prefix = _os.path.join(_os.path.abspath(_os.path.expanduser("~")), ".cache", "agent-company", "python")

from agent_company_install_io import install_paths
from agent_company_update_receipts import UpdateAttempt, UpdateReceiptError, UpdateResult
from agent_company_update_store import UpdateReceiptStore


INSTALLER: Final[Path] = Path(__file__).with_name("agent_company_installer.py")


class ProcessOutput(Protocol):
    @property
    def returncode(self) -> int: ...

    @property
    def stdout(self) -> str: ...

    @property
    def stderr(self) -> str: ...


class UpdateProcess(Protocol):
    def run(self, argv: tuple[str, ...]) -> ProcessOutput: ...


class UpdateClock(Protocol):
    def now(self) -> datetime: ...


class RunIds(Protocol):
    def new(self) -> str: ...


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class SystemProcess:
    def run(self, argv: tuple[str, ...]) -> CommandResult:
        try:
            env = dict(os.environ, PYTHONPYCACHEPREFIX=str(Path.home() / ".cache/agent-company/python"))
            completed = subprocess.run(argv, env=env, text=True, capture_output=True, check=False)
        except OSError as exc:
            return CommandResult(127, "", f"update process failed: {exc}")
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


@dataclass(frozen=True, slots=True)
class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class SystemRunIds:
    def new(self) -> str:
        return uuid.uuid4().hex


@dataclass(frozen=True, slots=True)
class UpdateRunnerConfig:
    store: UpdateReceiptStore
    process: UpdateProcess
    clock: UpdateClock
    run_ids: RunIds


def timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise UpdateReceiptError("invalid_clock", "update clock must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def default_config() -> UpdateRunnerConfig:
    return UpdateRunnerConfig(UpdateReceiptStore(install_paths().codex_home), SystemProcess(), SystemClock(), SystemRunIds())


def run(argv: tuple[str, ...], *, config: UpdateRunnerConfig | None = None) -> int:
    selected = config or default_config()
    run_id = selected.run_ids.new()
    attempted_at = timestamp(selected.clock.now())
    selected.store.record_attempt(UpdateAttempt(run_id, attempted_at))
    output = selected.process.run((sys.executable, str(INSTALLER), "update", *argv))
    if type(output.returncode) is not int or not isinstance(output.stdout, str) or not isinstance(output.stderr, str):
        raise UpdateReceiptError("invalid_process_output", "update process output types are invalid")
    completed_at = timestamp(selected.clock.now())
    successful_at = completed_at if output.returncode == 0 else None
    selected.store.record_result(UpdateResult(run_id, completed_at, output.returncode, successful_at))
    if output.stdout:
        print(output.stdout, end="")
    if output.stderr:
        print(output.stderr, end="", file=sys.stderr)
    return output.returncode


def main(argv: tuple[str, ...]) -> int:
    try:
        return run(argv)
    except UpdateReceiptError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(tuple(sys.argv[1:])))
