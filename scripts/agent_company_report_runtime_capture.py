from __future__ import annotations

from agent_company_core_runtime import ReportRuntimeBindings
from agent_company_deps import JsonValue
from agent_company_evidence_digest import (
    EvidenceDigestError,
    read_stable_json_evidence,
)
from agent_company_job_policy import PolicyError
from agent_company_report_byte_provenance import (
    ReportRuntimeByteCapture,
    ReportRuntimeEvidenceSources,
    capture_report_runtime_provenance,
)

MAX_RUNTIME_BYTES = 2_000_000


def capture_report_runtime(
    delegation_input: dict[str, JsonValue],
    bindings: ReportRuntimeBindings,
) -> ReportRuntimeByteCapture | None:
    if bindings.delegation_input_ref is None:
        return None
    try:
        delegation = read_stable_json_evidence(
            bindings.delegation_input_ref,
            bindings.job_ref_path.parent,
            MAX_RUNTIME_BYTES,
        )
        job = read_stable_json_evidence(
            bindings.job_ref,
            bindings.job_ref_path.parent,
            MAX_RUNTIME_BYTES,
        )
        core_run = read_stable_json_evidence(
            bindings.core_run_ref,
            bindings.core_run_ref_path.parent,
            MAX_RUNTIME_BYTES,
        )
    except EvidenceDigestError as exc:
        raise PolicyError(f"invalid report runtime byte source: {exc}") from exc
    expected = (
        (delegation.payload, delegation_input, "delegation"),
        (job.payload, bindings.job, "job"),
        (core_run.payload, bindings.core_run, "Core run"),
    )
    for actual, supplied, label in expected:
        if actual != supplied:
            raise PolicyError(
                f"{label} stable bytes do not match the supplied object"
            )
    try:
        return capture_report_runtime_provenance(
            ReportRuntimeEvidenceSources(delegation, job, core_run)
        )
    except PolicyError:
        return None
