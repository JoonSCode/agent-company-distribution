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
from agent_company_install_types import InstallError
from agent_company_deps import DepsError, resolve_dependency
from agent_company_launchd_contract import LAUNCHD_LABEL


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


def rendered_plist() -> bytes:
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
    arguments[1] = str(ROOT / "scripts" / "update.sh")
    environment["CODEX_HOME"] = str(install_paths().codex_home)
    try:
        dependency = resolve_dependency()
    except DepsError as exc:
        raise InstallError("dependency_resolution_failed", exc.detail) from exc
    if dependency.selected_source != "local_develop_checkout" or not dependency.git_root:
        raise InstallError("dependency_resolution_failed", "user updater requires a persistent local Core source")
    environment["AGENT_COMPANY_DEP_MODE"] = "local"
    environment["AGENT_COMPANY_KING_SEJONG_LOCAL_PATH"] = dependency.git_root
    if sejong_home := os.environ.get("SEJONG_HOME"):
        environment["SEJONG_HOME"] = str(Path(sejong_home).expanduser().resolve())
    return plistlib.dumps(parsed, fmt=plistlib.FMT_XML, sort_keys=False)


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
    prepare_update_logs()
    _ = launchctl(("bootout", target()))
    bootstrap = launchctl(("bootstrap", target().rsplit("/", 1)[0], str(plist)))
    if bootstrap.returncode != 0:
        raise InstallError("launchd_bootstrap_failed", bootstrap.stderr.strip() or bootstrap.stdout.strip())


def start_user_launchd() -> None:
    started = launchctl(("kickstart", "-k", target()))
    if started.returncode != 0:
        raise InstallError("launchd_kickstart_failed", started.stderr.strip() or started.stdout.strip())


def remove_user_launchd() -> None:
    _ = launchctl(("bootout", target()))
    try:
        user_plist().unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise InstallError("launchd_remove_failed", str(exc)) from exc
