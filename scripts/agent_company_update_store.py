#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# How to run:
#   python3 scripts/test_doctor_runtime.py --case fresh-v02

from __future__ import annotations

import fcntl
import os
import threading
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from agent_company_install_fs import anchored_parent
from agent_company_install_io import read_json, write_json
from agent_company_install_types import InstallError, JsonValue
from agent_company_update_receipts import (
    FORMAT,
    UpdateAttempt,
    UpdateReceiptError,
    UpdateReceiptState,
    UpdateResult,
    UpdateRun,
    parse_update_status,
    parsed_time,
    run_json,
    validate_run,
)


THREAD_LOCK: Final = threading.RLock()


@dataclass(frozen=True, slots=True)
class UpdateReceiptStore:
    codex_home: Path

    @property
    def status_path(self) -> Path:
        return self.codex_home / "agent-company" / "state" / "status.json"

    @contextmanager
    def locked(self) -> Generator[None, None, None]:
        relative = "agent-company/state/update-status.lock"
        with THREAD_LOCK:
            with anchored_parent(self.codex_home, relative, create=True) as (parent_fd, name):
                descriptor = os.open(name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
                with os.fdopen(descriptor, "r+") as handle:
                    os.fchmod(handle.fileno(), 0o600)
                    fcntl.flock(handle, fcntl.LOCK_EX)
                    try:
                        yield
                    finally:
                        fcntl.flock(handle, fcntl.LOCK_UN)

    def _payload(self) -> dict[str, JsonValue]:
        try:
            return read_json(self.status_path) if self.status_path.exists() else {}
        except InstallError as exc:
            raise UpdateReceiptError("unsafe_status", "update status is unreadable or unsafe") from exc

    def read_state(self) -> UpdateReceiptState:
        with self.locked():
            return parse_update_status(self._payload())

    def record_attempt(self, attempt: UpdateAttempt) -> None:
        pending = validate_run(UpdateRun(attempt.run_id, attempt.attempted_at, None, None, None))
        with self.locked():
            payload = self._payload()
            for field in ("last_attempted_update", "last_successful_update", "last_update_exit"):
                payload.pop(field, None)
            state = parse_update_status(payload)
            if pending.run_id in {run.run_id for run in state.runs}:
                raise UpdateReceiptError("duplicate_run", "run_id already exists")
            if state.runs and parsed_time(pending.attempted_at, "attempted_at") < parsed_time(state.runs[-1].attempted_at, "attempted_at"):
                raise UpdateReceiptError("invalid_order", "new update attempt predates the latest stored attempt")
            payload["schema_version"] = FORMAT
            payload["runs"] = [*(run_json(run) for run in state.runs), run_json(pending)]
            write_json(self.status_path, payload)

    def record_result(self, result: UpdateResult) -> None:
        with self.locked():
            payload = self._payload()
            state = parse_update_status(payload)
            runs: list[UpdateRun] = []
            matched = False
            for run in state.runs:
                if run.run_id == result.run_id:
                    if run.completed_at is not None:
                        raise UpdateReceiptError("duplicate_result", "run already has a result")
                    run = validate_run(
                        UpdateRun(run.run_id, run.attempted_at, result.completed_at, result.exit_code, result.successful_at)
                    )
                    matched = True
                runs.append(run)
            if not matched:
                raise UpdateReceiptError("unknown_run", "result run_id has no matching attempt")
            payload["runs"] = [run_json(run) for run in runs]
            write_json(self.status_path, payload)
