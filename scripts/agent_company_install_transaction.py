#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import os
import re
import stat
import uuid
from typing import Final

from agent_company_install_fs import anchored_parent, entry_stat, remove_at
from agent_company_install_faults import before_phase, midpoint
from agent_company_install_io import restore_entries, write_json
from agent_company_install_journal import begin, capture, load_journal, phase, transaction_dir, verified_entries
from agent_company_install_managed_fs import copy_managed, ensure_managed_dir, hash_managed, managed_exists, remove_managed, rename_managed
from agent_company_install_state import load_index, parse_entries
from agent_company_install_types import BackupEntry, InstallError, InstallPaths, JsonValue, TransactionSpec


COMPLETED_RECOVERY: Final[re.Pattern[str]] = re.compile(r"^recovery-[0-9a-f]{32}$")


def restore_transaction(paths: InstallPaths, transaction_id: str) -> None:
    directory, entries = verified_entries(paths, transaction_id)
    transaction = transaction_dir(paths, transaction_id)
    if directory != transaction:
        copy_managed(
            paths,
            "agent-company/rollback/current",
            f"agent-company/state/transactions/{transaction_id}",
        )
        directory = transaction
    if entries:
        restore_entries(paths, directory, entries)
    restore_rollback_swap(paths, transaction_id)
    cleanup_success(paths, transaction_id)


def recover(paths: InstallPaths) -> dict[str, JsonValue]:
    if not managed_exists(paths, "agent-company/state/install-transaction.json"):
        sweep_completed_recovery(paths)
        return {"status": "ok", "action": "recover", "recovered": False}
    _, spec = load_journal(paths)
    restore_transaction(paths, spec.transaction_id)
    return {"status": "ok", "action": "recover", "recovered": True, "transaction_id": spec.transaction_id}


def preserve_rollback(paths: InstallPaths, transaction_id: str) -> None:
    ensure_managed_dir(paths, "agent-company/rollback")
    current, next_generation = "agent-company/rollback/current", f"agent-company/rollback/next-{transaction_id}"
    previous = f"agent-company/rollback/previous-{transaction_id}"
    retained = f"agent-company/rollback/recovery-{transaction_id}"
    for relative in (next_generation, previous, retained):
        if managed_exists(paths, relative):
            remove_managed(paths, relative)
    copy_managed(paths, f"agent-company/state/transactions/{transaction_id}", next_generation)
    if managed_exists(paths, current):
        rename_managed(paths, current, previous)
    else:
        ensure_managed_dir(paths, previous)
        write_json(paths.codex_home / previous / ".absent.json", {"absent": True})
    rename_managed(paths, next_generation, current)
    midpoint("cleanup_rollback")
    rename_managed(paths, previous, retained)
    midpoint("preserve_rollback_after_prior_delete")


def restore_rollback_swap(paths: InstallPaths, transaction_id: str) -> None:
    current, next_generation = "agent-company/rollback/current", f"agent-company/rollback/next-{transaction_id}"
    previous = f"agent-company/rollback/previous-{transaction_id}"
    retained = f"agent-company/rollback/recovery-{transaction_id}"
    source = previous if managed_exists(paths, previous) else retained
    if managed_exists(paths, source):
        absent = managed_exists(paths, f"{source}/.absent.json")
        if managed_exists(paths, current):
            remove_managed(paths, current)
        if absent:
            remove_managed(paths, source)
        else:
            rename_managed(paths, source, current)
    for relative in (previous, retained):
        if managed_exists(paths, relative):
            remove_managed(paths, relative)
    if managed_exists(paths, next_generation):
        remove_managed(paths, next_generation)


def sweep_completed_recovery(paths: InstallPaths) -> None:
    with anchored_parent(paths.codex_home, "agent-company/rollback/.sweep", create=False) as (rollback_fd, _):
        for name in os.listdir(rollback_fd):
            if COMPLETED_RECOVERY.fullmatch(name) is None:
                continue
            metadata = entry_stat(rollback_fd, name)
            if metadata is None:
                continue
            if not stat.S_ISDIR(metadata.st_mode):
                raise InstallError("corrupt_recovery", f"completed recovery payload is not a directory: {name}")
            remove_at(rollback_fd, name)


def cleanup_success(paths: InstallPaths, transaction_id: str) -> None:
    transaction = f"agent-company/state/transactions/{transaction_id}"
    if managed_exists(paths, transaction):
        remove_managed(paths, transaction)
        midpoint("cleanup_after_payload_delete_before_journal")
    before_commit = (
        f"agent-company/staging/{transaction_id}",
        f"agent-company/rollback/next-{transaction_id}",
        f"agent-company/rollback/previous-{transaction_id}",
    )
    for relative in before_commit:
        if managed_exists(paths, relative):
            remove_managed(paths, relative)
    journal = "agent-company/state/install-transaction.json"
    if managed_exists(paths, journal):
        remove_managed(paths, journal)
    midpoint("cleanup_after_journal_delete_before_recovery_sweep")
    sweep_completed_recovery(paths)


def preflight_rollback(paths: InstallPaths, desired: tuple[BackupEntry, ...]) -> None:
    index = load_index(paths)
    for entry in desired:
        parts = entry.relative.split("/")
        if not managed_exists(paths, entry.relative):
            continue
        if parts[0] not in {"agents", "skills"}:
            continue
        if index is None:
            raise InstallError(
                "agent_conflict" if parts[0] == "agents" else "skill_conflict",
                f"rollback target is user-owned: {entry.relative}",
            )
        hashes = index.agents if parts[0] == "agents" else index.skills
        expected = hashes.get(parts[1])
        if expected is None:
            raise InstallError("agent_conflict" if parts[0] == "agents" else "skill_conflict", f"rollback target is user-owned: {entry.relative}")
        kind = "file" if parts[0] == "agents" else "dir"
        if hash_managed(paths, entry.relative, kind) != expected:
            raise InstallError("managed_drift", f"rollback target changed: {entry.relative}")


def rollback(paths: InstallPaths) -> dict[str, JsonValue]:
    if managed_exists(paths, "agent-company/state/install-transaction.json"):
        raise InstallError("recovery_required", "run recover before rollback")
    source, backup = paths.rollback / "current", paths.rollback / "current" / "backup.json"
    try:
        desired = parse_entries(backup)
    except InstallError as exc:
        if exc.code == "missing_target":
            raise InstallError("rollback_unavailable", "no prior generation") from exc
        raise
    preflight_rollback(paths, desired)
    transaction_id = uuid.uuid4().hex
    begin(paths, TransactionSpec(transaction_id, "rollback", "rollback"))
    try:
        groups = (
            ("preflight_all", None), ("stage_all", None),
            ("backup_managed", lambda: capture(paths, transaction_id, tuple(entry.relative for entry in desired))),
            ("apply_snapshot", lambda: restore_entries(paths, source, tuple(entry for entry in desired if entry.relative.startswith("agent-company/snapshots/")))),
            ("apply_skills", lambda: restore_entries(paths, source, tuple(entry for entry in desired if entry.relative.startswith("skills/")))),
            ("apply_agents", lambda: restore_entries(paths, source, tuple(entry for entry in desired if entry.relative.startswith("agents/")))),
            ("write_indexes", lambda: restore_entries(paths, source, tuple(entry for entry in desired if entry.relative == "agent-company/managed-index.json"))),
        )
        for name, operation in groups:
            before_phase(name)
            if operation is not None:
                operation()
            if name.startswith("apply_") or name == "write_indexes":
                midpoint("write_index" if name == "write_indexes" else name)
            phase(paths, name)
        before_phase("commit_active_hashes")
        restore_entries(
            paths,
            source,
            tuple(entry for entry in desired if entry.relative == "agent-company/installed-hashes.json"),
        )
        midpoint("ledger_hashes")
        restore_entries(
            paths,
            source,
            tuple(entry for entry in desired if entry.relative == "agent-company/active.json"),
        )
        midpoint("ledger_active")
        phase(paths, "commit_active_hashes")
        before_phase("cleanup")
        phase(paths, "cleanup")
        preserve_rollback(paths, transaction_id)
        cleanup_success(paths, transaction_id)
    except (InstallError, OSError, ValueError):
        restore_transaction(paths, transaction_id)
        raise
    return {"status": "ok", "action": "rollback", "transaction_id": transaction_id}
