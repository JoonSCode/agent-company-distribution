#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Final

from agent_company_install_faults import after_phase
from agent_company_install_fs import sha256_file
from agent_company_install_io import backup_targets, read_json, write_json
from agent_company_install_managed_fs import ensure_managed_dir, managed_exists
from agent_company_install_state import allowed_backup_target, entries_json, parse_entries
from agent_company_install_types import BackupEntry, InstallError, InstallPaths, JsonValue, TransactionSpec


PHASES: Final[tuple[str, ...]] = ("preflight_all", "stage_all", "backup_managed", "apply_snapshot", "apply_skills", "apply_agents", "write_indexes", "commit_active_hashes", "cleanup")
SAFE_TRANSACTION: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{32}$")
SAFE_SNAPSHOT: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SAFE_HASH: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
ACTIONS: Final[frozenset[str]] = frozenset({"install", "update", "rollback", "uninstall"})
FIELDS: Final[frozenset[str]] = frozenset({"schema_version", "transaction_id", "action", "snapshot_id", "phase", "status", "backup_sha256", "targets", "targets_sha256"})


def target_digest(targets: list[str]) -> str:
    return hashlib.sha256(json.dumps(targets, separators=(",", ":")).encode()).hexdigest()


def transaction_dir(paths: InstallPaths, transaction_id: str) -> Path:
    if SAFE_TRANSACTION.fullmatch(transaction_id) is None:
        raise InstallError("corrupt_recovery", "transaction id is unsafe")
    return paths.transactions / transaction_id


def begin(paths: InstallPaths, spec: TransactionSpec) -> None:
    if managed_exists(paths, "agent-company/state/install-transaction.json"):
        raise InstallError("recovery_required", "run recover before any install operation")
    ensure_managed_dir(paths, f"agent-company/state/transactions/{spec.transaction_id}")
    write_json(paths.journal, {"schema_version": "agent-company.install-transaction/v0.2", "transaction_id": spec.transaction_id, "action": spec.action, "snapshot_id": spec.snapshot_id, "phase": "created", "status": "recovery_required", "backup_sha256": "", "targets": [], "targets_sha256": target_digest([])})


def load_journal(paths: InstallPaths) -> tuple[dict[str, JsonValue], TransactionSpec]:
    payload = read_json(paths.journal, "corrupt_recovery")
    if set(payload) != FIELDS or payload.get("schema_version") != "agent-company.install-transaction/v0.2" or payload.get("status") != "recovery_required":
        raise InstallError("corrupt_recovery", "journal shape, version, or status is invalid")
    transaction_id, action, snapshot_id = payload.get("transaction_id"), payload.get("action"), payload.get("snapshot_id")
    phase_name, backup_digest = payload.get("phase"), payload.get("backup_sha256")
    targets, targets_hash = payload.get("targets"), payload.get("targets_sha256")
    if not isinstance(transaction_id, str) or SAFE_TRANSACTION.fullmatch(transaction_id) is None:
        raise InstallError("corrupt_recovery", "journal id is unsafe")
    if not isinstance(action, str) or action not in ACTIONS or not isinstance(snapshot_id, str) or SAFE_SNAPSHOT.fullmatch(snapshot_id) is None:
        raise InstallError("corrupt_recovery", "journal action or generation is invalid")
    if not isinstance(phase_name, str) or phase_name not in {"created", *PHASES} or not isinstance(backup_digest, str):
        raise InstallError("corrupt_recovery", "journal phase or digest is invalid")
    if not isinstance(targets, list) or not all(isinstance(target, str) and allowed_backup_target(target) for target in targets):
        raise InstallError("corrupt_recovery", "journal targets are invalid")
    if len(set(targets)) != len(targets) or not isinstance(targets_hash, str) or target_digest(targets) != targets_hash:
        raise InstallError("corrupt_recovery", "journal target digest is invalid")
    if phase_name in PHASES[2:] and (not targets or SAFE_HASH.fullmatch(backup_digest) is None):
        raise InstallError("corrupt_recovery", "completed backup is not bound")
    if backup_digest and SAFE_HASH.fullmatch(backup_digest) is None:
        raise InstallError("corrupt_recovery", "backup digest is malformed")
    transaction_relative = f"agent-company/state/transactions/{transaction_id}"
    if not managed_exists(paths, transaction_relative):
        if phase_name != "cleanup" or not managed_exists(paths, "agent-company/rollback/current"):
            raise InstallError("corrupt_recovery", "transaction payload and committed rollback are missing")
    return payload, TransactionSpec(transaction_id, action, snapshot_id)


def phase(paths: InstallPaths, name: str) -> None:
    if name not in PHASES:
        raise InstallError("invalid_phase", name)
    payload, _ = load_journal(paths)
    payload["phase"] = name
    write_json(paths.journal, payload)
    after_phase(name)


def capture(paths: InstallPaths, transaction_id: str, relatives: tuple[str, ...]) -> tuple[BackupEntry, ...]:
    directory, journal_spec = transaction_dir(paths, transaction_id), load_journal(paths)
    journal, spec = journal_spec
    targets = list(dict.fromkeys(relatives))
    if spec.transaction_id != transaction_id or not targets or not all(allowed_backup_target(target) for target in targets):
        raise InstallError("unsafe_path", "capture transaction or targets are invalid")
    journal["targets"], journal["targets_sha256"] = targets, target_digest(targets)
    write_json(paths.journal, journal)
    entries = backup_targets(paths, directory, tuple(targets))
    backup = directory / "backup.json"
    write_json(backup, {"schema_version": "agent-company.install-backup/v0.2", "transaction_id": transaction_id, "action": spec.action, "snapshot_id": spec.snapshot_id, "entries": entries_json(entries)})
    journal, _ = load_journal(paths)
    journal["backup_sha256"] = sha256_file(backup)
    write_json(paths.journal, journal)
    return entries


def verified_entries(paths: InstallPaths, transaction_id: str) -> tuple[Path, tuple[BackupEntry, ...]]:
    journal, spec = load_journal(paths)
    digest = journal.get("backup_sha256")
    if spec.transaction_id != transaction_id:
        raise InstallError("corrupt_recovery", "transaction id mismatch")
    transaction_relative = f"agent-company/state/transactions/{transaction_id}"
    if managed_exists(paths, transaction_relative):
        directory = transaction_dir(paths, transaction_id)
        backup_relative = f"{transaction_relative}/backup.json"
    else:
        directory = paths.rollback / "current"
        backup_relative = "agent-company/rollback/current/backup.json"
    backup = directory / "backup.json"
    if not managed_exists(paths, backup_relative):
        if digest:
            raise InstallError("corrupt_recovery", "bound backup is missing")
        return directory, ()
    if not isinstance(digest, str) or sha256_file(backup) != digest:
        raise InstallError("corrupt_recovery", "backup manifest digest mismatch")
    entries = parse_entries(backup, spec)
    if [entry.relative for entry in entries] != journal.get("targets"):
        raise InstallError("corrupt_recovery", "backup entries disagree with targets")
    return directory, entries
