#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# How to run:
#   python3 scripts/test_doctor_runtime.py --case drift-failed-update-and-recovery-required

from __future__ import annotations

import math
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, final, override


MAX_STALE_SECONDS = 31 * 24 * 60 * 60
LAUNCHD_LABEL = "local.agent-company.update"


class ProcessOutput(Protocol):
    @property
    def returncode(self) -> int: ...

    @property
    def stdout(self) -> str: ...

    @property
    def stderr(self) -> str: ...


class ProcessAdapter(Protocol):
    def run(self, argv: tuple[str, ...]) -> ProcessOutput: ...


class Clock(Protocol):
    def now_epoch(self) -> float: ...


@final
class LaunchdContractError(Exception):
    code: str
    detail: str

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)
        self.code = code
        self.detail = detail

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class LaunchdTarget:
    domain: str
    uid: int
    label: str

    def __post_init__(self) -> None:
        validate_target(self)

    @property
    def reference(self) -> str:
        return f"{self.domain}/{self.uid}/{self.label}"


def default_target() -> LaunchdTarget:
    return LaunchdTarget("gui", os.getuid(), LAUNCHD_LABEL)


def validate_target(target: LaunchdTarget) -> None:
    if (
        type(target) is not LaunchdTarget
        or target.domain != "gui"
        or type(target.uid) is not int
        or target.uid != os.getuid()
        or target.label != LAUNCHD_LABEL
    ):
        raise LaunchdContractError("invalid_target", "launchd target must match the current user job")


@dataclass(frozen=True, slots=True)
class LaunchdPaths:
    user_plist: Path
    stdout_log: Path
    stderr_log: Path

    def __post_init__(self) -> None:
        if any(not isinstance(path, Path) for path in (self.user_plist, self.stdout_log, self.stderr_log)):
            raise LaunchdContractError("invalid_paths", "launchd paths must be pathlib values")


@dataclass(frozen=True, slots=True)
class LaunchdConfig:
    paths: LaunchdPaths
    process: ProcessAdapter
    clock: Clock
    stale_seconds: int | float
    observe_live: bool
    target: LaunchdTarget = field(default_factory=default_target)

    def __post_init__(self) -> None:
        if type(self.paths) is not LaunchdPaths:
            raise LaunchdContractError("invalid_config", "paths must be an exact LaunchdPaths value")
        if not callable(getattr(self.process, "run", None)):
            raise LaunchdContractError("invalid_config", "process adapter must expose run")
        if not callable(getattr(self.clock, "now_epoch", None)):
            raise LaunchdContractError("invalid_config", "clock adapter must expose now_epoch")
        validate_target(self.target)
        threshold = self.stale_seconds
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, int | float)
            or not math.isfinite(threshold)
            or not 0 < threshold <= MAX_STALE_SECONDS
            or type(self.observe_live) is not bool
        ):
            raise LaunchdContractError("invalid_config", "stale threshold and observation flag are invalid")


@dataclass(frozen=True, slots=True)
class SystemProcess:
    def run(self, argv: tuple[str, ...]) -> CommandResult:
        try:
            completed = subprocess.run(argv, text=True, capture_output=True, check=False, timeout=5)
        except UnicodeError:
            return CommandResult(1, "", "launchd process output was not valid UTF-8")
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CommandResult(1, "", str(exc))
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


@dataclass(frozen=True, slots=True)
class SystemClock:
    def now_epoch(self) -> float:
        return time.time()


def validated_clock(config: LaunchdConfig) -> tuple[float, float]:
    if type(config) is not LaunchdConfig:
        raise LaunchdContractError("invalid_config", "config must be an exact LaunchdConfig value")
    validate_target(config.target)
    try:
        now = config.clock.now_epoch()
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise LaunchdContractError("invalid_clock", "clock observation failed") from exc
    if isinstance(now, bool) or not isinstance(now, int | float) or not math.isfinite(now):
        raise LaunchdContractError("invalid_clock", "clock must return a finite epoch number")
    return float(now), float(config.stale_seconds)
