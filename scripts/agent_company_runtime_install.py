#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

import hashlib
import os
import stat

from agent_company_deps import JsonValue
from agent_company_install_engine import EXPECTED_AGENT_FILES, verify_prior
from agent_company_install_fs import sha256_file
from agent_company_install_io import read_json
from agent_company_install_managed_fs import hash_managed
from agent_company_install_source import COPY_ENTRIES
from agent_company_install_state import load_index
from agent_company_install_types import InstallError, InstallPaths
from agent_company_runtime_values import RuntimePaths, issue, map_field, text_field


def installer_paths(paths: RuntimePaths) -> InstallPaths:
    return InstallPaths(
        paths.codex_home,
        paths.root,
        paths.state,
        paths.root / "staging",
        paths.snapshots,
        paths.rollback,
        paths.state / "install-transaction.json",
        paths.state / "transactions",
    )


def load_active(paths: RuntimePaths) -> tuple[dict[str, JsonValue], list[JsonValue]]:
    path = paths.root / "active.json"
    if not path.exists():
        return {}, [issue("not_installed", "active install is missing", path)]
    try:
        return read_json(path), []
    except InstallError as exc:
        return {}, [issue("malformed_input", f"could not read active.json: {exc}", path)]


def load_manifest(paths: RuntimePaths, snapshot_id: str) -> tuple[dict[str, JsonValue], list[JsonValue]]:
    path = paths.snapshots / snapshot_id / "manifest.json"
    try:
        return read_json(path), []
    except FileNotFoundError:
        return {}, [issue("missing_manifest", "installed manifest is missing", path)]
    except InstallError as exc:
        return {}, [issue("malformed_input", f"could not read manifest: {exc}", path)]


def installed_content_hash(manifest: dict[str, JsonValue]) -> str:
    files = map_field(manifest, "files")
    digest = hashlib.sha256()
    found = False
    for entry in COPY_ENTRIES:
        prefix = f"repo/{entry}"
        selected = sorted((name, value) for name, value in files.items() if name == prefix or name.startswith(f"{prefix}/"))
        for name, value in selected:
            if not isinstance(value, str):
                return ""
            digest.update(name.removeprefix("repo/").encode())
            digest.update(value.encode())
            found = True
    return digest.hexdigest() if found else ""


def verify_snapshot_hashes(paths: RuntimePaths, snapshot_id: str) -> list[JsonValue]:
    ledger = paths.root / "installed-hashes.json"
    try:
        hashes = read_json(ledger)
    except FileNotFoundError:
        return [issue("missing_hashes", "installed hashes file is missing", ledger)]
    except InstallError as exc:
        return [issue("malformed_input", f"invalid installed hashes: {exc}", ledger)]
    files = map_field(hashes, "files")
    if not files:
        return [issue("malformed_input", "installed hashes files map is missing", ledger)]
    issues: list[JsonValue] = []
    for relative, expected in files.items():
        if not isinstance(expected, str):
            issues.append(issue("malformed_input", f"hash for {relative} must be a string", ledger))
            continue
        try:
            actual = sha256_file(paths.snapshots / snapshot_id / relative)
        except FileNotFoundError:
            issues.append(issue("missing_installed_file", "installed file is missing", paths.snapshots / snapshot_id / relative))
        except OSError as exc:
            issues.append(issue("stale_state", f"could not hash installed file: {exc}"))
        else:
            if actual != expected:
                issues.append(issue("hash_mismatch", f"installed file digest differs: {relative}"))
    return issues


def managed_agent_report(paths: RuntimePaths) -> tuple[int, list[JsonValue]]:
    install_paths = installer_paths(paths)
    try:
        index = load_index(install_paths)
    except InstallError as exc:
        return 0, [issue("malformed_index", str(exc))]
    if index is None:
        return 0, [issue("missing_managed_index", "managed install index is missing")]
    valid = 0
    issues: list[JsonValue] = []
    for name, expected in index.agents.items():
        try:
            actual = hash_managed(install_paths, f"agents/{name}", "file")
        except InstallError as exc:
            issues.append(issue("missing_managed_agent", f"{name}: {exc}"))
        else:
            if actual == expected:
                valid += 1
            else:
                issues.append(issue("managed_agent_drift", f"managed agent digest differs: {name}"))
    if len(index.agents) != 6:
        issues.append(issue("managed_agent_count", f"expected 6 managed agents, index has {len(index.agents)}"))
    return valid, issues


def exact_generated_agent_issues(paths: RuntimePaths) -> list[JsonValue]:
    root = paths.codex_home / "agents"
    try:
        metadata = root.lstat()
    except FileNotFoundError:
        return [issue("missing_managed_agent", "managed agent directory is missing")]
    except OSError:
        return [issue("unexpected_managed_agent", "managed agent directory is unsafe")]
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        return [issue("unexpected_managed_agent", "managed agent directory is unsafe")]
    expected = set(EXPECTED_AGENT_FILES)
    try:
        with os.scandir(root) as entries:
            generated = {
                entry.name
                for entry in entries
                if entry.name.startswith("agent-company-") and entry.name.endswith(".toml")
            }
    except OSError:
        return [issue("unexpected_managed_agent", "managed agent directory cannot be inspected")]
    extras = sorted(generated - expected)
    return [] if not extras else [issue("unexpected_managed_agent", f"unexpected generated agents: {', '.join(extras)}")]


def installed_report(paths: RuntimePaths) -> tuple[dict[str, JsonValue], list[JsonValue]]:
    active, issues = load_active(paths)
    install_paths = installer_paths(paths)
    try:
        verify_prior(install_paths, load_index(install_paths))
    except InstallError as exc:
        issues.append(issue(exc.code, str(exc)))
    snapshot_id = text_field(active, "snapshot_id")
    manifest: dict[str, JsonValue] = {}
    if snapshot_id:
        manifest, manifest_issues = load_manifest(paths, snapshot_id)
        issues.extend(manifest_issues)
        issues.extend(verify_snapshot_hashes(paths, snapshot_id))
    managed_count, managed_issues = managed_agent_report(paths)
    issues.extend(managed_issues)
    issues.extend(exact_generated_agent_issues(paths))
    king = map_field(manifest, "king_sejong")
    github = map_field(king, "github_ref_fallback")
    report: dict[str, JsonValue] = {
        "root": str(paths.root),
        "snapshot_id": snapshot_id,
        "installed_ref": text_field(manifest, "agent_company_commit"),
        "manifest_sha256": text_field(active, "manifest_sha256"),
        "installed_content_sha256": installed_content_hash(manifest),
        "resolved_king_sejong_ref": text_field(github, "resolved_commit") or text_field(king, "commit"),
        "king_sejong_dependency_mode": text_field(king, "selected_source"),
        "managed_agent_count": managed_count,
        "hash_status": "ok" if not issues else "fail",
    }
    return report, issues
