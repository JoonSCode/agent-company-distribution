#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv if needed.
# 2. Import through agent_company_qa_release.py; this module has no CLI.
# 3. Test: python3 scripts/test_qa_release_operating_system.py
# ─────────────────

from __future__ import annotations

from agent_company_qa_release_types import CriterionStatus, Observation, ObservationStatus, QaEvidence, QaReport
from agent_company_qa_release_validation import validate_evidence


def evaluate(evidence: QaEvidence) -> QaReport:
    validate_evidence(evidence)
    observations = {item.criterion_id: item for item in evidence.observations}
    statuses: list[CriterionStatus] = []
    grouped: dict[ObservationStatus, list[Observation]] = {status: [] for status in ObservationStatus}
    missing: list[str] = []
    for criterion in evidence.criteria:
        observation = observations.get(criterion.id)
        if observation is None:
            statuses.append(CriterionStatus(criterion.id, criterion.surface, ObservationStatus.UNVERIFIED, None))
            missing.append(f"{criterion.id}:{criterion.surface.value}")
        else:
            statuses.append(CriterionStatus(criterion.id, criterion.surface, observation.status, observation))
            grouped[observation.status].append(observation)

    cleanup_missing: list[str] = []
    if not evidence.cleanup.screenshots_removed:
        cleanup_missing.append("cleanup:screenshots")
    if not evidence.cleanup.state_reset:
        cleanup_missing.append("cleanup:state")
    unverified = tuple((*grouped[ObservationStatus.UNVERIFIED],))
    unverified_surfaces = tuple((*missing, *(f"{item.criterion_id}:{item.surface.value}" for item in unverified), *cleanup_missing))
    failed = tuple(grouped[ObservationStatus.FAILED])
    blocked = tuple(grouped[ObservationStatus.BLOCKED])
    passed = tuple(grouped[ObservationStatus.PASSED])
    status = ObservationStatus.FAILED if failed else ObservationStatus.BLOCKED if blocked else ObservationStatus.UNVERIFIED if unverified_surfaces else ObservationStatus.PASSED
    return QaReport(
        status=status,
        qa_readiness="candidate" if status is ObservationStatus.PASSED else "reject",
        candidate=evidence.candidate,
        criteria_status=tuple(statuses),
        passed_evidence=passed,
        failed_evidence=failed,
        blocked_evidence=blocked,
        unverified_surfaces=unverified_surfaces,
        cleanup=evidence.cleanup,
        residual_risks=evidence.residual_risks,
        specialist_routes=evidence.specialist_routes,
        passed_count=len(passed),
        failed_count=len(failed),
        blocked_count=len(blocked),
        unverified_count=len(unverified_surfaces),
        failed_criteria=tuple(item.criterion_id for item in failed),
        blocked_criteria=tuple(item.criterion_id for item in blocked),
        unverified_criteria=tuple(item.split(":", 1)[0] for item in unverified_surfaces),
    )
