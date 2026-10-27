#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# uv run --script scripts/agent_company_bootstrap.py install --user --dry-run
# uv run --script scripts/agent_company_bootstrap.py install --user
# uv run --script scripts/agent_company_bootstrap.py verify
# ──────────────────

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, Literal

from agent_company_config import ConfigError
from agent_company_bootstrap_sources import (
    BootstrapError, CommandRequest, SourceSpec, checked, managed_container,
    lexical_home, materialize_source, object_value, source_identity, source_target, validate_materialized,
)

type Action = Literal["install", "verify"]
type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
ROOT: Final[Path] = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class BootstrapConfig:
    action: Action
    codex_home: Path
    user: bool | None = None
    dry_run: bool = False
    files_only: bool = False
    disable_updater: bool = False


def install_environment(config: BootstrapConfig) -> dict[str, str]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(config.codex_home)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def verify_company(config: BootstrapConfig, company: Path, env: dict[str, str]) -> None:
    output = checked(CommandRequest(
        (sys.executable, str(company / "scripts" / "sync-status.py"), "--json", "--device-home", str(config.codex_home)),
        company, env, "company_verify_failed",
    ))
    try:
        status = json.loads(output)
    except json.JSONDecodeError as exc:
        raise BootstrapError("company_verify_failed", "Company sync status was not JSON") from exc
    if not isinstance(status, dict) or status.get("material_failure") is not False:
        raise BootstrapError("company_verify_failed", "Company integrity/runtime verification failed")


def selected_sources(config: BootstrapConfig, source_root: Path) -> tuple[SourceSpec, dict[str, Path]]:
    spec = source_identity(source_root)
    return spec, {"agent_company": source_target(config.codex_home, spec)}


def bootstrap(config: BootstrapConfig, *, source_root: Path = ROOT) -> dict[str, JsonValue]:
    config = replace(config, codex_home=lexical_home(config.codex_home))
    if config.user is None:
        from agent_company_config import resolve
        config = replace(config, user=resolve(home=config.codex_home)["values"]["updater"])
    spec, targets = selected_sources(config, source_root)
    target = targets["agent_company"]
    installation: dict[str, JsonValue] = {}
    if config.dry_run:
        container = managed_container(config.codex_home, create=False)
        if container.exists() and (target.exists() or target.is_symlink()):
            validate_materialized(target, spec)
        return {"status": "dry_run", "sources": {"agent_company": str(target)}, "runtime_contract": "orca-company-standalone/v1"}
    if config.action == "verify":
        _ = managed_container(config.codex_home, create=False)
        if not target.exists():
            raise BootstrapError("source_missing", str(target))
        validate_materialized(target, spec)
        action = "verify"
    else:
        target = materialize_source(config.codex_home, spec)
        action = "update" if (config.codex_home / "agent-company/active.json").is_file() else "install"
        env = install_environment(config)
        installer = target / "scripts/agent_company_installer.py"
        checked(CommandRequest((sys.executable, str(installer), action, "--dry-run"), target, env, "company_preflight_failed"))
        output = checked(CommandRequest((sys.executable, str(installer), action, *(["--user"] if config.user else []), *(["--disable-updater"] if config.disable_updater else [])), target, env, "company_install_failed"))
        try:
            installation = object_value(json.loads(output), "installer result")
        except json.JSONDecodeError as exc:
            raise BootstrapError("company_install_failed", "installer result was not JSON") from exc
    if config.files_only:
        # Reuse installer dry-run to verify the activated generation and hashes.
        checked(CommandRequest((sys.executable, str(target / "scripts/agent_company_installer.py"), "update", "--dry-run"), target, install_environment(config), "company_integrity_failed"))
    else:
        verify_company(config, target, install_environment(config))
    result: dict[str, JsonValue] = {"status": "verified" if config.action == "verify" else "installed", "company_action": action, "sources": {"agent_company": str(target)}, "runtime_contract": "orca-company-standalone/v1", "verification": "package_files_only; native runtime/provider unverified" if config.files_only else "company_sync_runtime"}
    if "updater_removal" in installation:
        result["updater_removal"] = installation["updater_removal"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Install standalone Orca Company from an exact Company source")
    parser.add_argument("action", nargs="?", choices=("install", "verify"), default="install")
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))))
    parser.add_argument("--user", action="store_true", default=None)
    parser.add_argument("--no-user", action="store_false", dest="user", help="Skip the optional user updater")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--disable-updater", action="store_true")
    parser.add_argument("--files-only", action="store_true", help="Verify package integrity without Codex runtime/provider probes")
    args = parser.parse_args()
    try:
        result = bootstrap(BootstrapConfig(args.action, lexical_home(args.codex_home), args.user, args.dry_run, args.files_only, args.disable_updater))
    except (BootstrapError, ConfigError) as exc:
        print(json.dumps({"status": "blocked", "error": getattr(exc, "code", "configuration_invalid"), "detail": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
