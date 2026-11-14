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
import fcntl
import hashlib
import json
import stat
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
from agent_company_install_types import JsonValue
from agent_company_update_receipts import UpdateAttempt, UpdateReceiptError, UpdateResult
from agent_company_update_store import THREAD_LOCK, UpdateReceiptStore


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


MARKER_FORMAT: Final[str] = "company-update-marker/v1"
MARKER_LIMIT: Final[int] = 4096


def marker_line(run_id: str, output: ProcessOutput | None = None) -> bytes:
    record: dict[str, JsonValue] = {"format": MARKER_FORMAT, "event": "attempt", "run_id": run_id}
    if output is not None:
        record.update(event="result", exit_code=output.returncode)
        streams: dict[str, JsonValue] = {}
        for name, value in (("stdout", output.stdout), ("stderr", output.stderr)):
            normalized = value.encode("utf-8", errors="surrogatepass")
            streams[name] = {"bytes": len(normalized), "sha256": hashlib.sha256(normalized).hexdigest()}
        record["captured_process_output"] = {
            "scope": "returned_process_strings", "encoding": "utf-8/surrogatepass",
            "raw_retained": False, **streams,
        }
    return (json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_marker(store: UpdateReceiptStore, run_id: str, output: ProcessOutput | None = None) -> None:
    """Publish complete bounded lines privately, never infer identity from latest.

    Directory locking serializes cooperating processes; the store's thread lock
    covers threads too. Atomic replacement appends a complete result without a
    torn JSON line on write failure. Neither shared logs nor raw output are read.
    """
    from agent_company_update_receipts import RUN_ID

    descriptors: list[int] = []
    temporary: str | None = None
    try:
        if not isinstance(run_id, str) or RUN_ID.fullmatch(run_id) is None:
            raise ValueError("invalid marker identity")
        line = marker_line(run_id, output)
        if len(line) > MARKER_LIMIT:
            raise ValueError("marker limit")
        with THREAD_LOCK:
            descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(descriptor)
            parts = (*store.codex_home.absolute().parts[1:], "agent-company", "state", "update-markers")
            for index, part in enumerate(parts):
                if part in {".", ".."}:
                    raise ValueError("unsafe component")
                try:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                except FileNotFoundError:
                    # Existing receipt storage must already supply the parents.
                    if index != len(parts) - 1:
                        raise
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass  # Another run may have created the same directory.
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                descriptors.append(child)
                descriptor = child
                metadata = os.fstat(child)
                if metadata.st_uid not in {0, os.getuid()} or stat.S_IMODE(metadata.st_mode) & 0o022:
                    raise ValueError("unsafe directory")
                if index == len(parts) - 1 and (metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700):
                    raise ValueError("nonprivate marker directory")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            name = run_id + ".jsonl"
            expected = marker_line(run_id)
            if output is None:
                # Never overwrite an existing diagnostic, including an empty one.
                try:
                    os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError("marker already exists")
                payload = line
            else:
                reader = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
                try:
                    metadata = os.fstat(reader)
                    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                            or metadata.st_nlink != 1 or stat.S_IMODE(metadata.st_mode) != 0o600
                            or metadata.st_size > MARKER_LIMIT):
                        raise ValueError("unsafe marker")
                    previous = os.read(reader, MARKER_LIMIT + 1)
                    if previous != expected:
                        raise ValueError("marker is not a single matching attempt")
                finally:
                    os.close(reader)
                payload = previous + line
            if len(payload) > MARKER_LIMIT:
                raise ValueError("marker limit")
            temporary = "." + run_id + "." + uuid.uuid4().hex
            writer = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=descriptor)
            try:
                if os.write(writer, payload) != len(payload):
                    raise OSError("short marker write")
                os.fsync(writer)
            finally:
                os.close(writer)
            os.replace(temporary, name, src_dir_fd=descriptor, dst_dir_fd=descriptor)
            temporary = None
            os.fsync(descriptor)
    except (OSError, ValueError, OverflowError) as exc:
        raise UpdateReceiptError("update_marker_unavailable", "private update diagnostic could not be persisted") from exc
    finally:
        if temporary is not None and descriptors:
            try:
                os.unlink(temporary, dir_fd=descriptors[-1])
            except OSError:
                pass
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def run(argv: tuple[str, ...], *, config: UpdateRunnerConfig | None = None) -> int:
    selected = config or default_config()
    run_id = selected.run_ids.new()
    attempted_at = timestamp(selected.clock.now())
    selected.store.record_attempt(UpdateAttempt(run_id, attempted_at))
    write_marker(selected.store, run_id)
    output = selected.process.run((sys.executable, str(INSTALLER), "update", *argv))
    if type(output.returncode) is not int or not isinstance(output.stdout, str) or not isinstance(output.stderr, str):
        raise UpdateReceiptError("invalid_process_output", "update process output types are invalid")
    completed_at = timestamp(selected.clock.now())
    successful_at = completed_at if output.returncode == 0 else None
    selected.store.record_result(UpdateResult(run_id, completed_at, output.returncode, successful_at))
    write_marker(selected.store, run_id, output)
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
