#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# uv run scripts/agent_company_installer.py install --user
# uv run scripts/agent_company_installer.py recover --user
# ──────────────────

from __future__ import annotations
# pyright: reportAny=false, reportImplicitRelativeImport=false
# pyright: reportUnnecessaryComparison=false, reportUnusedCallResult=false

import argparse
import json
import sys
from typing import Literal, TypeIs, assert_never

from agent_company_config import ConfigError, resolve
from agent_company_deps import DepsError, JsonValue
from agent_company_install_engine import execute_generation, uninstall, verify_prior
from agent_company_install_fs import anchored_parent
from agent_company_install_io import install_paths, read_json
from agent_company_install_lock import InstallLock, acquire_lock, release_lock
from agent_company_install_source import RUNTIME_CONTRACT, snapshot_identity
from agent_company_install_state import load_index
from agent_company_install_managed_fs import ensure_managed_dir
from agent_company_install_transaction import recover, rollback
from agent_company_install_types import InstallError, InstallPaths
from agent_company_launchd_install import install_user_launchd, remove_user_launchd, start_user_launchd
from agent_company_skill_registry import SkillInstallError
from agent_company_role_contract import NativeAgentError

type Action = Literal["install", "update", "recover", "rollback", "uninstall"]
VALID_ACTIONS = frozenset({"install", "update", "recover", "rollback", "uninstall"})


def is_action(value: str) -> TypeIs[Action]:
    return value in VALID_ACTIONS


def parse_action(value: str) -> Action:
    if not is_action(value):
        raise InstallError("unsupported_action", value)
    return value


def prepare_runtime(paths: InstallPaths) -> None:
    for relative in (
        "agent-company",
        "agent-company/state",
        "agent-company/state/transactions",
        "agent-company/rollback",
        "agent-company/staging",
    ):
        ensure_managed_dir(paths, relative)
    for relative in ("agents/.agent-company-probe", "skills/.agent-company-probe"):
        try:
            with anchored_parent(paths.codex_home, relative, create=False):
                pass
        except InstallError as exc:
            if exc.code != "missing_target":
                raise


def run(
    action: str,
    *,
    dry_run: bool,
    user: bool | None = None,
    automatic: bool = False,
    disable_updater: bool = False,
) -> dict[str, JsonValue]:
    selected = parse_action(action)
    if user and disable_updater:
        raise InstallError("updater_conflict", "cannot enable and disable updater together")
    paths = install_paths()
    configuration = resolve(home=paths.codex_home) if selected in {"install", "update"} else None
    if user is None:
        user = bool(configuration and configuration['values']['updater'] and not automatic and not disable_updater)
    if dry_run:
        if selected in {"install", "update"}:
            verify_prior(paths, load_index(paths))
            identity = snapshot_identity()
            return {"status": "dry_run", "action": selected, "snapshot_id": identity.snapshot_id, "runtime_contract": RUNTIME_CONTRACT, "configuration": configuration}
        if selected != "recover":
            verify_prior(paths, load_index(paths))
        return {"status": "dry_run", "action": selected, "controller_runtime_contract": RUNTIME_CONTRACT}
    prepare_runtime(paths)
    lock: InstallLock = acquire_lock(paths)
    start_user_job = False
    try:
        if selected != "recover" and paths.journal.exists():
            raise InstallError("recovery_required", "run recover before any other action")
        result: dict[str, JsonValue]
        match selected:
            case "recover":
                result = recover(paths)
            case "rollback":
                verify_prior(paths, load_index(paths))
                result = rollback(paths)
            case "uninstall":
                result = uninstall(paths)
            case "install" | "update":
                result = execute_generation(paths, selected)
            case _ as unreachable:
                assert_never(unreachable)
        if selected in {"recover", "rollback"}:
            active_path = paths.root / "active.json"
            if active_path.exists():
                active = read_json(active_path)
                from agent_company_install_fs import safe_relative
                snapshot = safe_relative(str(active.get("snapshot_id", "")))
                if len(snapshot.parts) != 1:
                    raise InstallError("stale_state", "unsafe restored snapshot identity")
                restored = read_json(paths.snapshots / snapshot / "manifest.json")
                contract = restored.get("runtime_contract")
                result.update(controller_runtime_contract=RUNTIME_CONTRACT,
                              restored_runtime_contract=contract,
                              runtime_certification="standalone" if contract == RUNTIME_CONTRACT else "historical_legacy")
        if user:
            match selected:
                case "install" | "update" | "recover":
                    install_user_launchd()
                    start_user_job = True
                case "uninstall":
                    remove_user_launchd()
                case "rollback":
                    pass
                case unreachable:
                    assert_never(unreachable)
        if disable_updater and selected in {"install", "update", "recover"}:
            remove_user_launchd()
    finally:
        release_lock(paths, lock)
    if start_user_job:
        start_user_launchd()
    if configuration is not None:
        result["configuration"] = configuration
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "update", "recover", "rollback", "uninstall"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--user", action="store_true", default=None)
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--disable-updater", action="store_true", help="Explicitly unregister only the owned optional updater")
    args = parser.parse_args()
    try:
        result = run(
            args.action,
            dry_run=args.dry_run,
            user=args.user,
            automatic=args.auto,
            disable_updater=args.disable_updater,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
    except (ConfigError, DepsError, InstallError, NativeAgentError, SkillInstallError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
