#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations
# pyright: reportImplicitRelativeImport=false

import os
import plistlib
import stat
import subprocess
from pathlib import Path
from typing import Final

from agent_company_install_io import atomic_write, install_paths
from agent_company_install_types import InstallError, JsonValue
from agent_company_launchd_contract import LAUNCHD_LABEL
from agent_company_launchd_output import LaunchdOutputError, parse_launchctl


ROOT: Final[Path] = Path(__file__).resolve().parents[1]
TEMPLATE: Final[Path] = ROOT / "launchd" / f"{LAUNCHD_LABEL}.plist"
LAUNCHCTL: Final[Path] = Path("/bin/launchctl")
UPDATE_LOGS: Final[tuple[Path, Path]] = (
    Path("/private/tmp/agent-company-update.out.log"),
    Path("/private/tmp/agent-company-update.err.log"),
)


def user_plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def target() -> str:
    return f"gui/{os.getuid()}/{LAUNCHD_LABEL}"


def rendered_plist(*, updater_root: Path | None = None) -> bytes:
    try:
        parsed = plistlib.loads(TEMPLATE.read_bytes())
    except (OSError, plistlib.InvalidFileException) as exc:
        raise InstallError("launchd_template_missing", str(TEMPLATE)) from exc
    if not isinstance(parsed, dict):
        raise InstallError("launchd_template_invalid", "plist root must be a dictionary")
    arguments = parsed.get("ProgramArguments")
    environment = parsed.get("EnvironmentVariables")
    expected_keys = {
        "Label", "ProgramArguments", "EnvironmentVariables", "StartCalendarInterval",
        "StandardOutPath", "StandardErrorPath",
    }
    if (
        set(parsed) != expected_keys
        or parsed.get("Label") != LAUNCHD_LABEL
        or arguments != ["/bin/bash", "scripts/update.sh", "--auto"]
        or environment != {
            "CODEX_HOME": "~/.codex",
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        }
        or parsed.get("StartCalendarInterval") != {"Hour": 9, "Minute": 0}
        or parsed.get("StandardOutPath") != str(UPDATE_LOGS[0])
        or parsed.get("StandardErrorPath") != str(UPDATE_LOGS[1])
    ):
        raise InstallError("launchd_template_invalid", "launchd template differs from the authenticated contract")
    assert isinstance(arguments, list)
    assert isinstance(environment, dict)
    arguments[1] = str((ROOT if updater_root is None else updater_root) / "scripts" / "update.sh")
    environment["CODEX_HOME"] = str(install_paths().codex_home)
    logs = selected_update_logs()
    parsed["StandardOutPath"], parsed["StandardErrorPath"] = map(str, logs)
    if sejong_home := os.environ.get("SEJONG_HOME"):
        environment["SEJONG_HOME"] = str(Path(sejong_home).expanduser().resolve())
    return plistlib.dumps(parsed, fmt=plistlib.FMT_XML, sort_keys=False)


def selected_update_logs() -> tuple[Path, Path]:
    """Keep production log paths; isolate logs with the existing test launcher."""
    selected = os.environ.get("AGENT_COMPANY_TEST_UPDATE_LOG_DIR")
    if selected and os.environ.get("AGENT_COMPANY_TEST_LAUNCHCTL"):
        root = Path(selected)
        if not root.is_absolute() or ".." in root.parts:
            raise InstallError("unsafe_path", "test update log directory must be absolute")
        return root / UPDATE_LOGS[0].name, root / UPDATE_LOGS[1].name
    return UPDATE_LOGS


def launchctl_executable() -> Path:
    test_override = os.environ.get("AGENT_COMPANY_TEST_LAUNCHCTL")
    if test_override is None:
        return LAUNCHCTL
    candidate = Path(test_override)
    if not candidate.is_absolute() or not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise InstallError("launchctl_missing", "test launchctl must be an executable absolute path")
    return candidate


def launchctl(arguments: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    executable = launchctl_executable()
    try:
        return subprocess.run((executable, *arguments), text=True, capture_output=True, check=False)
    except OSError as exc:
        raise InstallError("launchctl_failed", str(exc)) from exc


def prepare_update_logs(logs: tuple[Path, Path] = UPDATE_LOGS) -> None:
    for log in logs:
        try:
            directory_fd = os.open(
                log.parent,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
        except OSError as exc:
            raise InstallError("unsafe_path", f"update log parent is unsafe: {log.parent}") from exc
        try:
            try:
                log_fd = os.open(
                    log.name,
                    os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                    0o600,
                    dir_fd=directory_fd,
                )
            except OSError as exc:
                raise InstallError("unsafe_path", f"update log is unsafe: {log}") from exc
            try:
                metadata = os.fstat(log_fd)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != os.getuid()
                    or metadata.st_nlink != 1
                ):
                    raise InstallError("unsafe_path", f"update log is unsafe: {log}")
                os.ftruncate(log_fd, 0)
                os.fchmod(log_fd, 0o600)
            finally:
                os.close(log_fd)
        finally:
            os.close(directory_fd)


def install_user_launchd() -> None:
    plist = user_plist()
    atomic_write(plist, rendered_plist(), 0o600)
    prepare_update_logs(selected_update_logs())
    _ = launchctl(("bootout", target()))
    bootstrap = launchctl(("bootstrap", target().rsplit("/", 1)[0], str(plist)))
    if bootstrap.returncode != 0:
        raise InstallError("launchd_bootstrap_failed", bootstrap.stderr.strip() or bootstrap.stdout.strip())


def start_user_launchd() -> None:
    started = launchctl(("kickstart", "-k", target()))
    if started.returncode != 0:
        raise InstallError("launchd_kickstart_failed", started.stderr.strip() or started.stdout.strip())


def remove_user_launchd() -> dict[str, JsonValue]:
    """The shared user-domain label alone never establishes install ownership."""
    plist = user_plist()
    try:
        metadata = plist.lstat()
    except FileNotFoundError:
        return {"status": "preserved", "reason": "ownership_plist_missing"}
    except OSError:
        return {"status": "preserved", "reason": "ownership_plist_unreadable"}
    if (
        not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1 or stat.S_IMODE(metadata.st_mode) not in {0o600, 0o644}
    ):
        return {"status": "preserved", "reason": "ownership_plist_unsafe"}
    try:
        parsed = plistlib.loads(plist.read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException):
        return {"status": "preserved", "reason": "ownership_plist_invalid"}
    if not isinstance(parsed, dict) or parsed.get("Label") != LAUNCHD_LABEL:
        return {"status": "preserved", "reason": "ownership_plist_invalid"}
    arguments = parsed.get("ProgramArguments")
    environment = parsed.get("EnvironmentVariables")
    if (
        not isinstance(arguments, list) or len(arguments) != 3
        or arguments[0] != "/bin/bash" or arguments[2] != "--auto"
        or not isinstance(arguments[1], str)
        or not isinstance(environment, dict)
        or environment.get("CODEX_HOME") != str(install_paths().codex_home)
    ):
        return {"status": "preserved", "reason": "ownership_install_mismatch"}
    updater = Path(arguments[1])
    if not updater.is_absolute() or ".." in updater.parts or updater.parts[-2:] != ("scripts", "update.sh"):
        return {"status": "preserved", "reason": "ownership_updater_invalid"}

    # A stale local plist must not authorize stopping another loaded install.
    # Compare the root fields observed in launchctl print, not inherited/nested
    # environments. An older source path/hash is allowed to update or recover.
    observed = launchctl(("print", target()))
    absent = observed.returncode == 113 and "Could not find service" in (observed.stdout + observed.stderr)
    if not absent:
        if observed.returncode != 0:
            return {"status": "preserved", "reason": "loaded_ownership_unconfirmed"}
        try:
            valid = parse_launchctl(observed.stdout, observed.stderr).state != "invalid"
        except LaunchdOutputError:
            valid = False
        if not valid:
            return {"status": "preserved", "reason": "loaded_ownership_unconfirmed"}
        paths: list[str] = []
        programs: list[str] = []
        argv_blocks: list[list[str]] = []
        home_blocks: list[list[str]] = []
        depth, section = 0, ""
        for line in observed.stdout.splitlines():
            value = line.strip()
            if depth == 1:
                if value.startswith("path = "):
                    paths.append(value.removeprefix("path = "))
                elif value.startswith("program = "):
                    programs.append(value.removeprefix("program = "))
                elif value == "arguments = {":
                    argv_blocks.append([])
                    section = "arguments"
                elif value == "environment = {":
                    home_blocks.append([])
                    section = "environment"
            elif depth == 2 and value != "}":
                if section == "arguments":
                    argv_blocks[-1].append(value)
                elif section == "environment" and value.startswith("CODEX_HOME => "):
                    home_blocks[-1].append(value.removeprefix("CODEX_HOME => "))
            depth += line.count("{") - line.count("}")
            if depth <= 1:
                section = ""
        if (
            paths != [str(plist)]
            or programs != ["/bin/bash"] or home_blocks != [[environment["CODEX_HOME"]]]
            or argv_blocks != [arguments]
        ):
            return {"status": "preserved", "reason": "loaded_ownership_unconfirmed"}
        stopped = launchctl(("bootout", target()))
        if stopped.returncode != 0:
            raise InstallError("launchd_remove_failed", stopped.stderr.strip() or stopped.stdout.strip() or "owned updater bootout failed")
    try:
        plist.unlink()
    except OSError as exc:
        raise InstallError("launchd_remove_failed", str(exc)) from exc
    return {"status": "removed", "reason": "owned_plist_only" if absent else "owned_job_and_plist"}
