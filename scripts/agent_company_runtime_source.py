#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

from agent_company_deps import JsonValue, run_git
from agent_company_install_source import ROOT, working_tree_hash
from agent_company_runtime_values import issue
from agent_company_install_io import read_json
from agent_company_install_types import InstallError


def source_report() -> tuple[dict[str, JsonValue], list[JsonValue]]:
    # Installed snapshot repos are deliberately Git-free. Integrity is checked
    # against active/manifest/index by installed_report, not an ancestor Git repo.
    manifest_path = ROOT.parent / "manifest.json"
    if ROOT.parent.parent.name == "snapshots" and not (ROOT / ".git").exists():
        try:
            manifest = read_json(manifest_path)
            source_hash = working_tree_hash()
            return {"reachable": True, "commit": manifest.get("agent_company_commit", ""),
                    "tag": "", "worktree_status": "clean", "content_sha256": source_hash,
                    "identity_source": "stored_company_manifest"}, []
        except (InstallError, OSError, ValueError) as exc:
            return {}, [issue("source_unavailable", f"installed Company source cannot be inspected: {exc}")]
    commit = run_git(["rev-parse", "HEAD"], cwd=ROOT)
    tag = run_git(["describe", "--tags", "--exact-match"], cwd=ROOT)
    status = run_git(["status", "--porcelain"], cwd=ROOT)
    issues: list[JsonValue] = []
    if not commit.ok or not status.ok:
        issues.append(issue("source_unavailable", commit.stderr or status.stderr or "source git state unavailable"))
    try:
        content_hash = working_tree_hash()
    except (OSError, ValueError) as exc:
        content_hash = ""
        issues.append(issue("source_unavailable", f"could not hash source: {exc}"))
    return {
        "reachable": commit.ok,
        "commit": commit.stdout,
        "tag": tag.stdout if tag.ok else "",
        "worktree_status": "dirty" if status.stdout else "clean",
        "content_sha256": content_hash,
    }, issues
