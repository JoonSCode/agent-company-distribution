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

from agent_company_deps import DepsError, JsonValue
from agent_company_install_engine import execute_generation, uninstall, verify_prior
from agent_company_install_fs import anchored_parent
from agent_company_install_io import install_paths
from agent_company_install_lock import InstallLock, acquire_lock, release_lock
from agent_company_install_source import CoreSyncBlocked, snapshot_identity
from agent_company_install_state import load_index
from agent_company_install_managed_fs import ensure_managed_dir
from agent_company_install_transaction import recover, rollback
from agent_company_install_types import InstallError, InstallPaths
from agent_company_launchd_install import install_user_launchd, remove_user_launchd, start_user_launchd
from agent_company_skill_registry import SkillInstallError
from agent_company_role_contract import NativeAgentError
from agent_company_core_sync import (
    DEFERRED_EXIT_CODE,
    deferred_result,
)

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
    user: bool = False,
    automatic: bool = False,
) -> dict[str, JsonValue]:
    selected = parse_action(action)
    paths = install_paths()
    if dry_run:
        try:
            identity = snapshot_identity(require_core_sync=selected in {"install", "update"})
        except CoreSyncBlocked as exc:
            if automatic:
                return deferred_result(selected, exc.status)
            state = exc.status.get("state")
            reason = state if isinstance(state, str) else "incompatible"
            raise InstallError("core_sync_blocked", reason) from exc
        return {"status": "dry_run", "action": selected, "snapshot_id": identity.snapshot_id, "king_sejong": identity.dependency}
    prepare_runtime(paths)
    lock: InstallLock = acquire_lock(paths)
    start_user_job = False
    try:
        if selected != "recover" and paths.journal.exists():
            raise InstallError("recovery_required", "run recover before any other action")
        result: dict[str, JsonValue]
        try:
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
        except CoreSyncBlocked as exc:
            if not automatic:
                state = exc.status.get("state")
                reason = state if isinstance(state, str) else "incompatible"
                raise InstallError("core_sync_blocked", reason) from exc
            result = deferred_result(selected, exc.status)
        if user and result.get("status") != "deferred":
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
    finally:
        release_lock(paths, lock)
    if start_user_job:
        start_user_launchd()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "update", "recover", "rollback", "uninstall"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--user", action="store_true")
    parser.add_argument("--auto", action="store_true")
    args = parser.parse_args()
    try:
        result = run(
            args.action,
            dry_run=args.dry_run,
            user=args.user,
            automatic=args.auto,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        if result.get("status") == "deferred":
            return DEFERRED_EXIT_CODE
    except (DepsError, InstallError, NativeAgentError, SkillInstallError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
