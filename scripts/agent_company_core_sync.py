#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations
# pyright: reportAny=false, reportImplicitRelativeImport=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnnecessaryIsInstance=false
# pyright: reportUnusedCallResult=false

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from agent_company_deps import (
    DepsError,
    DependencyRecord,
    JsonValue,
    SAFE_GIT_CONFIG,
    dependency_mode,
    git_environment,
    load_config,
    lock_json,
    resolve_local,
    run_git,
)
from agent_company_install_fs import safe_relative, sha256_file
from agent_company_install_io import install_paths, read_json
from agent_company_install_managed_fs import hash_managed, read_path_bytes
from agent_company_install_state import load_index
from agent_company_install_types import InstallError, InstallPaths
from check_core_contract import ContractBlocker, check_contract


FORMAT: Final[str] = "agent-company.core-sync-status/v0.1"
DEFERRED_FORMAT: Final[str] = "agent-company.core-sync-deferred/v0.1"
DEFERRED_EXIT_CODE: Final[int] = 75
CORE_IDENTITY_RELATIVE_PATH: Final[Path] = Path("state/core-install-identity.json")
CORE_HELPER_RELATIVE_PATH: Final[Path] = Path("docs/sejong/scripts/core_install_identity.py")
CORE_SCHEMA_RELATIVE_PATH: Final[Path] = Path("docs/sejong/core-install-identity.schema.json")
ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SHA256_LENGTH: Final[int] = 64
CORE_HELPER_TIMEOUT_SECONDS: Final[int] = 30


def _sha256(path: Path) -> str | None:
    if not _regular_file(path):
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _regular_file(path: Path) -> bool:
    try:
        return path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1
    except OSError:
        return False


def _timestamp(value: str | None) -> str:
    if value is not None:
        return value
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _codex_home(env: Mapping[str, str]) -> Path:
    return Path(env.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser().resolve()


def _sejong_home(env: Mapping[str, str], codex_home: Path) -> Path:
    configured = env.get("SEJONG_HOME")
    return Path(configured).expanduser().resolve() if configured else codex_home / "sejong"


def _nullable_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _valid_sha256(value: str | None) -> bool:
    return value is not None and len(value) == SHA256_LENGTH and all(char in "0123456789abcdef" for char in value)


def _dependency_fields(payload: object) -> tuple[str, str, str]:
    if not isinstance(payload, dict):
        raise ValueError("dependency_not_object")
    dependencies = payload.get("resolved_dependencies")
    if not isinstance(dependencies, dict):
        raise ValueError("resolved_dependencies_not_object")
    king = dependencies.get("king_sejong")
    if not isinstance(king, dict):
        raise ValueError("king_sejong_not_object")
    commit = _nullable_text(king.get("commit"))
    checkout = king.get("local_develop_checkout")
    if not isinstance(checkout, dict):
        raise ValueError("local_develop_checkout_not_object")
    commit = _nullable_text(checkout.get("commit")) or commit
    content_sha256 = _nullable_text(checkout.get("content_sha256"))
    fallback = king.get("github_ref_fallback")
    if not isinstance(fallback, dict):
        raise ValueError("github_ref_fallback_not_object")
    origin = _nullable_text(fallback.get("url"))
    if commit is None or len(commit) not in {40, 64} or any(char not in "0123456789abcdef" for char in commit):
        raise ValueError("commit_invalid")
    if not _valid_sha256(content_sha256) or origin is None:
        raise ValueError("content_sha256_invalid")
    assert content_sha256 is not None
    return commit, content_sha256, origin


def _inspect_lock(path: Path) -> dict[str, JsonValue]:
    layer: dict[str, JsonValue] = {
        "status": "missing",
        "ref": str(path),
        "commit": None,
        "content_sha256": None,
        "origin": None,
        "errors": [],
    }
    if not path.exists() and not path.is_symlink():
        layer["errors"] = ["lock_missing"]
        return layer
    if not _regular_file(path):
        layer["status"] = "malformed"
        layer["errors"] = ["lock_unsafe"]
        return layer
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        commit, content_sha256, origin = _dependency_fields(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        layer["status"] = "malformed"
        layer["errors"] = [f"lock_invalid:{type(exc).__name__}"]
        return layer
    layer.update(status="available", commit=commit, content_sha256=content_sha256, origin=origin)
    return layer


def _candidate_binding(
    record: DependencyRecord,
    tracked: dict[str, JsonValue],
) -> tuple[str, list[str]]:
    if tracked.get("status") != "available":
        return "not_run", ["tracked_baseline_unavailable"]
    if record.worktree_status != "clean" or not record.git_root:
        return "blocked", ["candidate_not_clean_and_inspectable"]
    expected_commit = tracked.get("commit")
    expected_content = tracked.get("content_sha256")
    expected_origin = tracked.get("origin")
    if record.commit != expected_commit:
        return "blocked", ["candidate_commit_mismatch"]
    if record.content_sha256 != expected_content:
        return "blocked", ["candidate_content_mismatch"]
    actual_origin = run_git(["remote", "get-url", "origin"], cwd=Path(record.git_root))
    if not actual_origin.ok:
        return "blocked", ["candidate_origin_unavailable"]
    if actual_origin.stdout != expected_origin:
        return "blocked", ["candidate_origin_mismatch"]
    return "verified", []


def _candidate_contract(record: DependencyRecord) -> tuple[str, list[str]]:
    if record.worktree_status != "clean" or not record.git_root:
        return "not_run", ["candidate_not_clean_and_inspectable"]
    try:
        with tempfile.TemporaryDirectory(prefix="agent-company-core-contract-") as temporary:
            lock_path = Path(temporary) / "candidate.lock.json"
            lock_path.write_text(json.dumps(lock_json(record), sort_keys=True) + "\n", encoding="utf-8")
            _ = check_contract(lock_path)
    except ContractBlocker as exc:
        return "blocked", [f"core_contract:{exc.code}"]
    except OSError as exc:
        return "blocked", [f"core_contract_io:{type(exc).__name__}"]
    return "ok", []


def _inspect_source(
    env: Mapping[str, str],
    tracked: dict[str, JsonValue],
) -> tuple[dict[str, JsonValue], DependencyRecord | None]:
    layer: dict[str, JsonValue] = {
        "status": "missing",
        "selected_source": None,
        "ref": None,
        "commit": None,
        "content_sha256": None,
        "helper_sha256": None,
        "schema_sha256": None,
        "baseline_binding": "not_run",
        "contract_probe": "not_run",
        "errors": [],
    }
    try:
        mode = dependency_mode(env.get("AGENT_COMPANY_DEP_MODE", "auto"))
        config = load_config(env)
    except DepsError as exc:
        layer["status"] = "uninspectable"
        layer["errors"] = [f"dependency_config:{exc.code}"]
        return layer, None
    if mode == "github":
        layer.update(
            status="uninspectable",
            selected_source="github_ref_fallback",
            ref=f"{config.github_url}#{config.github_ref}",
            errors=["remote_candidate_not_materialized"],
        )
        return layer, None
    try:
        record = resolve_local(config)
    except DepsError as exc:
        layer["status"] = "uninspectable"
        layer["errors"] = [f"dependency_resolution:{exc.code}"]
        return layer, None
    if record is None:
        layer.update(
            status="missing",
            selected_source="local_develop_checkout",
            ref=str(config.local_path),
            errors=["local_source_missing"],
        )
        return layer, None
    source_root = Path(record.git_root).resolve()
    helper = source_root / CORE_HELPER_RELATIVE_PATH
    schema = source_root / CORE_SCHEMA_RELATIVE_PATH
    binding, binding_errors = _candidate_binding(record, tracked)
    probe, probe_errors = _candidate_contract(record) if binding == "verified" else ("not_run", [])
    errors = [*binding_errors, *probe_errors]
    if not _regular_file(helper):
        errors.append("core_identity_helper_missing")
    if not _regular_file(schema):
        errors.append("core_identity_schema_missing")
    status = "clean" if record.worktree_status == "clean" else "dirty"
    error_values: list[JsonValue] = [item for item in sorted(set(errors))]
    layer.update(
        status=status,
        selected_source=record.selected_source,
        ref=str(source_root),
        commit=record.commit,
        content_sha256=record.content_sha256,
        helper_sha256=_sha256(helper),
        schema_sha256=_sha256(schema),
        baseline_binding=binding,
        contract_probe=probe,
        errors=error_values,
    )
    return layer, record


def _identity_fields(
    payload: object,
) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    if not isinstance(payload, dict):
        return None, None, None, None, None
    source = payload.get("source")
    installed = payload.get("installed")
    return (
        _nullable_text(payload.get("contract_version")),
        _nullable_text(payload.get("identity_sha256")),
        _nullable_text(source.get("commit")) if isinstance(source, dict) else None,
        _nullable_text(source.get("managed_content_sha256")) if isinstance(source, dict) else None,
        _nullable_text(installed.get("managed_content_sha256")) if isinstance(installed, dict) else None,
    )


def _core_check_result(payload: object, returncode: int) -> tuple[str, list[str]]:
    expected = {"format", "status", "identity_sha256", "checks", "errors", "authority"}
    if not isinstance(payload, dict) or set(payload) != expected:
        raise ValueError("helper_result_shape_invalid")
    if payload.get("format") != "sejong.core-install-identity-check/v0.1":
        raise ValueError("helper_result_format_invalid")
    if payload.get("authority") != "provenance_only":
        raise ValueError("helper_result_authority_invalid")
    status = payload.get("status")
    if status not in {"compatible", "missing", "malformed", "source_drift", "installed_tampered"}:
        raise ValueError("helper_status_invalid")
    if (returncode == 0) != (status == "compatible"):
        raise ValueError("helper_exit_status_mismatch")
    checks = payload.get("checks")
    expected_checks = {"identity_present", "identity_well_formed", "source_matches", "installed_matches"}
    if not isinstance(checks, dict) or set(checks) != expected_checks:
        raise ValueError("helper_checks_invalid")
    for name, value in checks.items():
        if name in {"identity_present", "identity_well_formed"}:
            if not isinstance(value, bool):
                raise ValueError("helper_checks_invalid")
        elif value is not None and not isinstance(value, bool):
            raise ValueError("helper_checks_invalid")
    raw_errors = payload.get("errors")
    if not isinstance(raw_errors, list) or not all(isinstance(item, str) and item for item in raw_errors):
        raise ValueError("helper_errors_invalid")
    return status, list(raw_errors)


def _inspect_installed(
    identity_path: Path,
    codex_home: Path,
    source_layer: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    layer: dict[str, JsonValue] = {
        "status": "missing",
        "ref": str(identity_path),
        "contract_version": None,
        "identity_sha256": None,
        "source_commit": None,
        "source_managed_content_sha256": None,
        "installed_managed_content_sha256": None,
        "errors": [],
    }
    if not identity_path.exists() and not identity_path.is_symlink():
        layer["errors"] = ["identity_missing"]
        return layer
    if not _regular_file(identity_path):
        layer.update(status="malformed", errors=["identity_unsafe"])
        return layer
    source_ref = source_layer.get("ref")
    source_commit = source_layer.get("commit")
    if not isinstance(source_ref, str) or not isinstance(source_commit, str) or source_layer.get("baseline_binding") != "verified":
        layer.update(status="unavailable", errors=["source_candidate_unverified"])
        return layer
    try:
        identity_before = read_path_bytes(identity_path)
        with tempfile.TemporaryDirectory(prefix="agent-company-core-identity-") as temporary:
            helper = Path(temporary) / CORE_HELPER_RELATIVE_PATH.name
            pinned = subprocess.run(
                ["git", *SAFE_GIT_CONFIG, "show", f"{source_commit}:{CORE_HELPER_RELATIVE_PATH.as_posix()}"],
                cwd=source_ref,
                env=git_environment(),
                capture_output=True,
                check=False,
                timeout=CORE_HELPER_TIMEOUT_SECONDS,
            )
            if pinned.returncode != 0:
                raise InstallError("core_identity_helper_missing", pinned.stderr.decode(errors="replace").strip())
            helper.write_bytes(pinned.stdout)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(helper),
                    "verify",
                    "--identity",
                    str(identity_path),
                    "--source-root",
                    source_ref,
                    "--installed-root",
                    str(codex_home),
                ],
                cwd=temporary,
                env=git_environment(),
                text=True,
                capture_output=True,
                check=False,
                timeout=CORE_HELPER_TIMEOUT_SECONDS,
            )
        payload = json.loads(completed.stdout)
        status, raw_errors = _core_check_result(payload, completed.returncode)
        identity_after = read_path_bytes(identity_path)
        if identity_after != identity_before:
            raise ValueError("identity_changed_during_inspection")
        identity_payload = json.loads(identity_before)
    except (OSError, UnicodeDecodeError, subprocess.TimeoutExpired, json.JSONDecodeError, InstallError, ValueError) as exc:
        layer.update(status="unavailable", errors=[f"core_identity_helper_failed:{type(exc).__name__}"])
        return layer
    contract_version, identity_sha256, source_commit, source_digest, installed_digest = _identity_fields(identity_payload)
    error_values: list[JsonValue] = [item for item in sorted(set(raw_errors))]
    layer.update(
        status=status,
        contract_version=contract_version,
        identity_sha256=identity_sha256,
        source_commit=source_commit,
        source_managed_content_sha256=source_digest,
        installed_managed_content_sha256=installed_digest,
        errors=error_values,
    )
    return layer


def _text_hash_map(value: JsonValue, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise InstallError("mixed_generation", f"{field} is not an object")
    result: dict[str, str] = {}
    for name, digest in value.items():
        if not isinstance(name, str) or not isinstance(digest, str) or not _valid_sha256(digest):
            raise InstallError("mixed_generation", f"{field} contains invalid hashes")
        result[name] = digest
    return result


def _verify_active_ledgers(
    paths: InstallPaths,
    active: dict[str, JsonValue],
    snapshot_id: str,
) -> None:
    hashes = read_json(paths.root / "installed-hashes.json", "malformed_input")
    if hashes.get("snapshot_id") != snapshot_id:
        raise InstallError("mixed_generation", "active and installed-hash generations disagree")
    files = _text_hash_map(hashes.get("files"), "installed snapshot files")
    for relative, expected in files.items():
        if sha256_file(paths.snapshots / snapshot_id / safe_relative(relative)) != expected:
            raise InstallError("hash_mismatch", f"installed snapshot drift: {relative}")
    index = load_index(paths)
    if active.get("schema_version") == "0.2" and index is None:
        raise InstallError("mixed_generation", "v0.2 active generation has no managed index")
    if index is None:
        return
    if index.snapshot_id != snapshot_id:
        raise InstallError("mixed_generation", "active and managed-index generations disagree")
    index_hash = sha256_file(paths.root / "managed-index.json")
    if active.get("managed_index_sha256") != index_hash or hashes.get("managed_index_sha256") != index_hash:
        raise InstallError("managed_drift", "active/hash ledger disagrees with managed index")
    if _text_hash_map(hashes.get("skills"), "installed skills") != index.skills:
        raise InstallError("mixed_generation", "installed skill hashes disagree with managed index")
    if _text_hash_map(hashes.get("agents"), "installed agents") != index.agents:
        raise InstallError("mixed_generation", "installed agent hashes disagree with managed index")
    active_skills = active.get("skills")
    active_agents = active.get("agents")
    if not isinstance(active_skills, dict) or active_skills.get("installed") != sorted(index.skills):
        raise InstallError("mixed_generation", "active skill set disagrees with managed index")
    if (
        not isinstance(active_agents, dict)
        or active_agents.get("installed") != sorted(index.agents)
        or active_agents.get("installed_count") != len(index.agents)
    ):
        raise InstallError("mixed_generation", "active agent set disagrees with managed index")
    for name, expected in index.skills.items():
        if hash_managed(paths, f"skills/{name}", "dir") != expected:
            raise InstallError("managed_drift", f"managed skill changed: {name}")
    for name, expected in index.agents.items():
        if hash_managed(paths, f"agents/{name}", "file") != expected:
            raise InstallError("managed_drift", f"managed agent changed: {name}")


def _inspect_active(codex_home: Path) -> dict[str, JsonValue]:
    paths = install_paths(codex_home)
    active_path = paths.root / "active.json"
    layer: dict[str, JsonValue] = {
        "status": "missing",
        "ref": str(active_path),
        "snapshot_id": None,
        "agent_company_ref": None,
        "embedded_core_commit": None,
        "embedded_core_content_sha256": None,
        "errors": [],
    }
    if not active_path.is_file():
        layer["errors"] = ["active_snapshot_missing"]
        return layer
    try:
        active = read_json(active_path, "stale_state")
        if active.get("schema_version") not in {"0.1", "0.2"}:
            raise InstallError("mixed_generation", "active ledger version is unsupported")
        snapshot_id = active.get("snapshot_id")
        if not isinstance(snapshot_id, str) or len(safe_relative(snapshot_id).parts) != 1:
            raise InstallError("stale_state", "active snapshot id is invalid")
        snapshot = paths.snapshots / snapshot_id
        manifest_path = snapshot / "manifest.json"
        expected_manifest = active.get("manifest_sha256")
        if not isinstance(expected_manifest, str) or sha256_file(manifest_path) != expected_manifest:
            raise InstallError("mixed_generation", "active manifest digest mismatch")
        manifest = read_json(manifest_path, "malformed_input")
        agent_ref = _nullable_text(active.get("agent_company_ref")) or _nullable_text(manifest.get("agent_company_commit"))
        lock_layer = _inspect_lock(snapshot / "repo/agent-company.lock.json")
        if lock_layer["status"] != "available":
            raise InstallError("mixed_generation", "active snapshot Core lock is unavailable")
        _verify_active_ledgers(paths, active, snapshot_id)
    except InstallError as exc:
        layer.update(
            status="tampered" if exc.code in {"hash_mismatch", "managed_drift", "mixed_generation"} else "malformed",
            errors=[f"active_snapshot:{exc.code}"],
        )
        return layer
    layer.update(
        status="available",
        snapshot_id=snapshot_id,
        agent_company_ref=agent_ref,
        embedded_core_commit=lock_layer["commit"],
        embedded_core_content_sha256=lock_layer["content_sha256"],
        errors=[],
    )
    return layer


def _state(
    source: dict[str, JsonValue],
    installed: dict[str, JsonValue],
    active: dict[str, JsonValue],
) -> str:
    installed_status = installed["status"]
    source_status = source["status"]
    if installed_status == "missing":
        return "missing_core_identity"
    if source_status == "dirty" or source.get("baseline_binding") == "blocked" or installed_status == "source_drift":
        return "source_runtime_diverged"
    if (
        source_status != "clean"
        or source["contract_probe"] != "ok"
        or installed_status != "compatible"
        or active["status"] in {"malformed", "tampered"}
    ):
        return "incompatible"
    if active["status"] == "missing":
        return "candidate_available"
    if (
        active["embedded_core_commit"] != source["commit"]
        or active["embedded_core_content_sha256"] != source["content_sha256"]
    ):
        return "candidate_available"
    return "healthy"


def build_sync_status(
    *,
    env: Mapping[str, str] | None = None,
    generated_at: str | None = None,
) -> dict[str, JsonValue]:
    selected_env = os.environ if env is None else env
    codex_home = _codex_home(selected_env)
    sejong_home = _sejong_home(selected_env, codex_home)
    tracked_path = ROOT / "agent-company.lock.json"
    test_lock = selected_env.get("AGENT_COMPANY_TEST_TRACKED_LOCK")
    if test_lock:
        candidate = Path(test_lock).expanduser().resolve()
        if candidate == codex_home / ".agent-company-test-core.lock.json" and _regular_file(candidate):
            tracked_path = candidate
    tracked = _inspect_lock(tracked_path)
    source, _ = _inspect_source(selected_env, tracked)
    installed = _inspect_installed(sejong_home / CORE_IDENTITY_RELATIVE_PATH, codex_home, source)
    active = _inspect_active(codex_home)
    state = _state(source, installed, active)
    allowed = state in {"healthy", "candidate_available"}
    reason = "exact_pair_verified" if state == "healthy" else "candidate_binding_required" if allowed else state
    return {
        "format": FORMAT,
        "generated_at": _timestamp(generated_at),
        "state": state,
        "mutation": "none",
        "authority": "compatibility_evidence_only",
        "layers": {
            "tracked_baseline_lock": tracked,
            "core_source_candidate": source,
            "installed_core_runtime": installed,
            "active_company_snapshot": active,
        },
        "activation": {
            "allowed": allowed,
            "automatic_action": "proceed" if allowed else "defer",
            "manual_action": "proceed" if allowed else "block",
            "reason": reason,
        },
    }


def deferred_result(action: str, status: dict[str, JsonValue]) -> dict[str, JsonValue]:
    state = status.get("state")
    reason = state if isinstance(state, str) else "incompatible"
    return {
        "format": DEFERRED_FORMAT,
        "status": "deferred",
        "action": action,
        "reason": reason,
        "mutation": "none",
        "core_sync": status,
    }


def invalidate_sync_status(
    status: dict[str, JsonValue],
    *,
    state: str,
    error: str,
) -> dict[str, JsonValue]:
    cloned = json.loads(json.dumps(status, sort_keys=True))
    if not isinstance(cloned, dict):
        raise ValueError("sync status clone is not an object")
    cloned["state"] = state
    cloned["activation"] = {
        "allowed": False,
        "automatic_action": "defer",
        "manual_action": "block",
        "reason": state,
    }
    layers = cloned.get("layers")
    if isinstance(layers, dict):
        source = layers.get("core_source_candidate")
        if isinstance(source, dict):
            raw_errors = source.get("errors")
            errors = [item for item in raw_errors if isinstance(item, str)] if isinstance(raw_errors, list) else []
            source["errors"] = sorted(set((*errors, error)))
    return cloned


def isolated_legacy_fixture_override(env: Mapping[str, str] | None = None) -> bool:
    selected = os.environ if env is None else env
    if selected.get("AGENT_COMPANY_ENFORCE_CORE_IDENTITY") == "1":
        return False
    if selected.get("AGENT_COMPANY_ALLOW_DIRTY") != "1" or selected.get("AGENT_COMPANY_ALLOW_DIRTY_DEPENDENCY") != "1":
        return False
    marker = selected.get("AGENT_COMPANY_TEST_LAUNCHCTL")
    if not marker:
        return False
    codex_home = _codex_home(selected)
    marker_path = Path(marker).expanduser().resolve()
    return marker_path.name == ".agent-company-test-launchctl" and marker_path.parent == codex_home and marker_path.is_file()
