#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

from __future__ import annotations

from pathlib import Path

from agent_company_install_faults import midpoint, race_staged_target
from agent_company_install_integrity import verify_staged_snapshot, verify_target_bytes
from agent_company_install_managed_fs import remove_managed
from agent_company_install_pinned import (
    pin_staged_source,
    pinned_digest,
    pinned_file_hashes,
    replace_with_pinned,
    verify_installed_pinned,
)
from agent_company_install_types import (
    ApplyBatch,
    InstallError,
    InstallPaths,
    InstallTarget,
    StagedGeneration,
)


def remove_target(paths: InstallPaths, target: InstallTarget) -> None:
    remove_managed(paths, target.relative)


def apply_targets(paths: InstallPaths, batch: ApplyBatch) -> None:
    verify_target_bytes(batch.desired)
    changed = 0
    for target in batch.desired:
        source = target.source
        if source is None:
            raise InstallError("stale_state", f"missing staged source for {target.relative}")
        pinned = pin_staged_source(paths, source, target.kind)
        if pinned_digest(pinned) != target.expected_hash:
            raise InstallError("staged_source_drift", f"staged source changed: {target.relative}")
        verify_target_bytes((target,))
        if changed == 0 and batch.staging_root is not None and batch.race_kind is not None:
            race_staged_target(batch.staging_root, batch.race_kind)
        verify_target_bytes((target,))
        replace_with_pinned(paths, pinned, target.relative)
        verify_installed_pinned(paths, target.relative, pinned)
        verify_target_bytes((target,))
        changed += 1
        if changed == 1:
            midpoint(batch.midpoint)
    for target in batch.stale:
        remove_target(paths, target)
        changed += 1
        if changed == 1:
            midpoint(batch.midpoint)


def apply_snapshot(
    paths: InstallPaths,
    stage: Path,
    staged: StagedGeneration,
) -> None:
    pinned = pin_staged_source(paths, stage / "snapshot", "dir")
    if pinned_file_hashes(pinned) != staged.files:
        raise InstallError("staged_source_drift", "staged snapshot changed")
    verify_staged_snapshot(stage, staged)
    race_staged_target(stage, "snapshot")
    verify_staged_snapshot(stage, staged)
    relative = f"agent-company/snapshots/{staged.snapshot_id}"
    replace_with_pinned(paths, pinned, relative)
    verify_installed_pinned(paths, relative, pinned)
    verify_staged_snapshot(stage, staged)


__all__ = ["apply_snapshot", "apply_targets", "remove_target"]
