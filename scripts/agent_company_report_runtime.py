"""Company-owned, read-only evidence contract for report projection.

This validates stored records, not a live worker or model. Historical `sejong`
format names are accepted as data; no external engine or pin is interpreted.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from agent_company_deps import JsonValue
from agent_company_evidence_digest import (
    EvidenceDigestError, read_stable_json_evidence, require_unchanged_evidence,
)
from agent_company_external_action_validation import validate_external_action_ledger
from agent_company_job_policy import PolicyError, object_list, string_list, text
from agent_company_privacy import PrivacyError, reject_sensitive


@dataclass(frozen=True, slots=True)
class ReportRuntimeBindings:
    job: dict[str, JsonValue]
    job_ref: str
    core_run: dict[str, JsonValue]
    core_run_ref: str
    delegation_input_ref: str | None = None
    verification_run: dict[str, JsonValue] | None = None
    verification_run_ref: str | None = None
    external_action_ledger: dict[str, JsonValue] | None = None
    external_action_ledger_ref: str | None = None

    @property
    def job_ref_path(self) -> Path:
        return Path(os.path.abspath(Path(self.job_ref).expanduser()))

    @property
    def core_run_ref_path(self) -> Path:
        return Path(os.path.abspath(Path(self.core_run_ref).expanduser()))


@dataclass(frozen=True, slots=True)
class ValidatedRuntime:
    external_action_ledger_sha256: str | None


def _unique(values: list[str], label: str) -> set[str]:
    if len(values) != len(set(values)):
        raise PolicyError(f"Company record {label} repeats identifiers")
    return set(values)


def _validate_cleanup(receipt: dict[str, JsonValue]) -> None:
    capability, status = receipt.get("cleanup_capability"), receipt.get("cleanup_status")
    if capability not in {"core_owned_exact", "host_owned_exact", "audit_only"} or status not in {"released", "preserved", "failed", "audit_only"}:
        raise PolicyError("Company record cleanup capability or status is invalid")
    resources = {
        field: _unique(string_list(receipt.get(field), field), field)
        for field in ("released_resource_ids", "preserved_resource_ids", "failed_resource_ids")
    }
    released, preserved, failed = resources.values()
    if released & preserved or released & failed or preserved & failed:
        raise PolicyError("Company record cleanup resource dispositions overlap")
    if not _unique(string_list(receipt.get("proof_refs"), "cleanup proof"), "cleanup proof"):
        raise PolicyError("Company record cleanup lacks proof")
    blocker = receipt.get("blocker")
    if status == "released":
        if capability == "audit_only":
            raise PolicyError("Company record cleanup capability cannot certify released resources")
        if receipt.get("backend_worker_ref") not in released or preserved or failed or blocker is not None:
            raise PolicyError("Company record released cleanup retains resources or blocker")
    else:
        text(blocker, "cleanup blocker")
        if (status == "preserved" and not preserved) or (status == "failed" and not failed) or (status == "audit_only" and capability != "audit_only"):
            raise PolicyError("Company record cleanup disposition lacks its authority or resources")


def validate_run(run: dict[str, JsonValue]) -> None:
    """Validate only the lifecycle evidence that Company reports consume."""
    if run.get("format") != "sejong.delegation-run/v0.1-draft":
        raise PolicyError("Company record Core run has an unsupported format")
    run_id = text(run.get("run_id"), "Core run_id")
    workers = object_list(run.get("workers"), "Core workers")
    worker_ids = _unique([text(w.get("worker_id"), "worker_id") for w in workers], "workers")
    worker_by_id = {str(w["worker_id"]): w for w in workers}
    waves = object_list(run.get("waves"), "Core waves")
    _unique([text(w.get("wave_id"), "wave_id") for w in waves], "waves")
    wave_by_id = {str(w["wave_id"]): w for w in waves}
    receipts = object_list(run.get("receipts"), "Core receipts")
    _unique([text(r.get("receipt_id"), "receipt_id") for r in receipts], "receipts")
    by_id = {str(r["receipt_id"]): r for r in receipts}
    terminal_workers: set[str] = set()
    for receipt in receipts:
        if receipt.get("run_id") != run_id:
            raise PolicyError("Company record Core receipt belongs to another run")
        wave = wave_by_id.get(str(receipt.get("wave_id")))
        if wave is None:
            raise PolicyError("Company record Core receipt belongs to an unknown wave")
        kind = receipt.get("receipt_type")
        authority = {"worker_terminal": "evidence_only", "worker_cleanup": "cleanup_evidence_only", "fan_in": "orchestration_evidence_only"}.get(str(kind))
        if authority is None or receipt.get("authority") != authority:
            raise PolicyError("Company record has invalid Core receipt authority")
        expected_format = {"worker_terminal": "sejong.delegation-worker-receipt/v0.1-draft", "worker_cleanup": "sejong.worker-cleanup-receipt/v0.1-draft", "fan_in": "sejong.delegation-fan-in-receipt/v0.1-draft"}[str(kind)]
        if receipt.get("format") != expected_format:
            raise PolicyError("Company record has invalid Core receipt format")
        if kind in {"worker_terminal", "worker_cleanup"}:
            worker_id = text(receipt.get("worker_id"), "worker_id")
            worker = worker_by_id.get(worker_id)
            if worker is None or worker_id not in string_list(wave.get("required_worker_ids"), "wave workers"):
                raise PolicyError("Company record Core worker/wave binding is invalid")
            if receipt.get("backend") not in {"native", "tmux"} or receipt.get("backend") != worker.get("backend"):
                raise PolicyError("Company record has invalid Core backend")
            if kind == "worker_terminal":
                if receipt.get("backend") == "native" and not str(receipt.get("backend_worker_ref", "")).startswith("codex-thread://"):
                    raise PolicyError("native terminal receipt lacks a Codex thread identity")
                try:
                    reject_sensitive(text(receipt.get("summary"), "worker summary"))
                except PrivacyError as exc:
                    raise PolicyError("report privacy rejected the worker summary") from exc
                if worker_id in terminal_workers or receipt.get("terminal_status") != worker.get("status"):
                    raise PolicyError("Company record Core worker terminal state is inconsistent")
                terminal_workers.add(worker_id)
                if receipt.get("terminal_status") not in {"completed", "failed", "blocked", "cancelled", "timed_out"}:
                    raise PolicyError("Company record has invalid Core terminal status")
                for field in ("worker_contract_ref", "worker_output_ref"):
                    text(receipt.get(field), field)
                evidence = _unique(string_list(receipt.get("evidence_refs"), "terminal evidence"), "terminal evidence")
                if receipt.get("terminal_status") == "completed":
                    if not evidence or receipt.get("blocker") is not None:
                        raise PolicyError("Company record completed terminal requires evidence and cannot carry a blocker")
                else:
                    text(receipt.get("blocker"), "terminal blocker")
            else:
                _validate_cleanup(receipt)
    for wave in waves:
        required = _unique(string_list(wave.get("required_worker_ids"), "wave workers"), "wave workers")
        if not required.issubset(worker_ids):
            raise PolicyError("Company record Core wave has unknown workers")
        fan_in_id = wave.get("fan_in_receipt_id")
        if fan_in_id is None:
            if wave.get("status") in {"passed", "failed", "blocked"}:
                raise PolicyError("Company record closed wave requires its fan-in receipt")
            continue  # An incomplete wave cannot become verified in report projection.
        fan_in = by_id.get(str(fan_in_id))
        if fan_in is None or fan_in.get("receipt_type") != "fan_in" or fan_in.get("wave_id") != wave.get("wave_id"):
            raise PolicyError("Company record Core wave fan-in is missing or mismatched")
        if _unique(string_list(fan_in.get("required_worker_ids"), "fan-in workers"), "fan-in workers") != required:
            raise PolicyError("Company record Core fan-in worker coverage differs")
        references = []
        for field, kind in (("terminal_receipt_ids", "worker_terminal"), ("cleanup_receipt_ids", "worker_cleanup")):
            ids = _unique(string_list(fan_in.get(field), field), field)
            selected = [by_id.get(rid) for rid in ids]
            if any(r is None or r.get("receipt_type") != kind or r.get("wave_id") != wave.get("wave_id") for r in selected):
                raise PolicyError("Company record Core fan-in receipt references are invalid")
            if kind == "worker_terminal" and {str(r.get("worker_id")) for r in selected if r} != required:
                raise PolicyError("Company record Core fan-in terminal coverage differs")
            if kind == "worker_cleanup":
                cleanup_workers = [text(r.get("worker_id"), "cleanup worker") for r in selected if r]
                if _unique(cleanup_workers, "cleanup workers") != required:
                    raise PolicyError("Company record fan-in cleanup coverage differs")
                terminals = {str(r.get("worker_id")): r for r in receipts if r.get("receipt_type") == "worker_terminal"}
                for cleanup in selected:
                    assert cleanup is not None
                    terminal = terminals.get(str(cleanup["worker_id"]))
                    if terminal is None:
                        raise PolicyError("Company record cleanup has no bound terminal")
                    if cleanup.get("backend_worker_ref") != terminal.get("backend_worker_ref"):
                        raise PolicyError("Company record cleanup does not bind the terminal worker")
            references.extend(r for r in selected if r is not None)
        blockers = {str(r["receipt_id"]) for r in references if r.get("terminal_status") not in {None, "completed"} or r.get("cleanup_status") not in {None, "released"}}
        if _unique(string_list(fan_in.get("blocking_receipt_ids"), "fan-in blockers"), "fan-in blockers") != blockers:
            raise PolicyError("Company record Core fan-in blockers are inconsistent")
        aggregate = "failed" if any(r.get("terminal_status") in {"failed", "timed_out"} for r in references) else "blocked" if blockers else "passed"
        if fan_in.get("aggregate_status") != aggregate or wave.get("status") != aggregate:
            raise PolicyError("Company record Core fan-in aggregate is inconsistent")


def validate_report_runtime(bindings: ReportRuntimeBindings) -> ValidatedRuntime:
    captures = []
    ledger_hash = None
    for value, reference, label in (
        (bindings.job, bindings.job_ref, "job"),
        (bindings.core_run, bindings.core_run_ref, "Core run"),
        (bindings.verification_run, bindings.verification_run_ref, "verification run"),
        (bindings.external_action_ledger, bindings.external_action_ledger_ref, "external-action ledger"),
    ):
        if (value is None) != (reference is None):
            raise PolicyError(f"{label} bytes and reference must be supplied together")
        if value is None:
            continue
        assert reference is not None
        try:
            capture = read_stable_json_evidence(reference, bindings.job_ref_path.parent, 2_000_000)
        except EvidenceDigestError as exc:
            raise PolicyError(f"invalid {label} byte source: {exc}") from exc
        if capture.payload != value:
            raise PolicyError(f"{label} ref bytes do not match the supplied object")
        captures.append(capture)
        if label == "external-action ledger":
            ledger_hash = capture.sha256
    validate_run(bindings.core_run)
    if bindings.external_action_ledger is not None:
        validate_external_action_ledger(bindings.external_action_ledger)
    if bindings.verification_run is not None:
        verification = bindings.verification_run
        if verification.get("format") != "sejong.seungjeongwon-run/v0.1-draft":
            raise PolicyError("historical verification run has an unsupported format")
        if verification.get("status") == "completed" and (verification.get("blockers") or verification.get("uigwe_reentry_requests")):
            raise PolicyError("completed verification cannot retain blockers")
    try:
        for capture in captures:
            require_unchanged_evidence(capture)
    except EvidenceDigestError as exc:
        raise PolicyError(f"report byte source changed: {exc}") from exc
    return ValidatedRuntime(ledger_hash)
