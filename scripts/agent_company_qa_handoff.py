from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportUnnecessaryComparison=false, reportUnusedCallResult=false
from dataclasses import dataclass
from typing import Final, assert_never

from agent_company_deps import JsonValue
from agent_company_qa_handoff_v2 import parse_qa_verification_v2
from agent_company_qa_handoff_v2_base import (
    QaV2Error,
    QaVerificationV2,
)

SHA256_LENGTH: Final[int] = 64
MAX_TEXT_LENGTH: Final[int] = 400
MAX_ACTIONS: Final[int] = 20
CELL_STATUSES: Final[frozenset[str]] = frozenset(
    {"planned", "passed", "failed", "blocked", "unverified"}
)
BLOCKER_ARTIFACT_STATUSES: Final[frozenset[str]] = frozenset(
    {"required", "captured", "unavailable"}
)
LEGACY_VERSION: Final[str] = "agent-company.execution-handoff/v0.3"
CURRENT_VERSION: Final[str] = "agent-company.execution-handoff/v0.4"


@dataclass(frozen=True, slots=True)
class QaProofCell:
    criterion_or_risk: str
    status: str


@dataclass(frozen=True, slots=True)
class QaReleaseBlocker:
    identifier: str
    owner: str
    status: str


@dataclass(frozen=True, slots=True)
class QaVerification:
    proof_cells: tuple[QaProofCell, ...]
    release_blockers: tuple[QaReleaseBlocker, ...]
    authorizes_completion: bool


@dataclass(frozen=True, slots=True)
class QaHandoffError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


def _object(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    match value:
        case dict():
            return value
        case str() | int() | float() | bool() | None | list():
            raise QaHandoffError(f"qa_verification.{label} must be an object")
        case unreachable:
            assert_never(unreachable)


def _text(value: JsonValue | None, label: str) -> str:
    match value:
        case str() if value.strip() and len(value) <= MAX_TEXT_LENGTH:
            return value
        case str() | int() | float() | bool() | None | list() | dict():
            raise QaHandoffError(
                f"qa_verification.{label} must be bounded non-empty text"
            )
        case unreachable:
            assert_never(unreachable)


def _sha256(value: JsonValue | None, label: str) -> str:
    digest = _text(value, label)
    if len(digest) != SHA256_LENGTH or any(char not in "0123456789abcdef" for char in digest):
        raise QaHandoffError(f"qa_verification.{label} must be a SHA-256 digest")
    return digest


def _exact_fields(
    value: dict[str, JsonValue],
    expected: frozenset[str],
    label: str,
) -> None:
    if set(value) != expected:
        raise QaHandoffError(
            f"qa_verification.{label} must contain exactly {sorted(expected)}"
        )


def _candidate(value: JsonValue | None, label: str) -> None:
    candidate = _object(value, label)
    fields = frozenset(candidate)
    if fields == frozenset({"identity_ref", "identity_sha256"}):
        _text(candidate.get("identity_ref"), f"{label}.identity_ref")
        _sha256(candidate.get("identity_sha256"), f"{label}.identity_sha256")
        return
    if fields == frozenset({"unknown_reason"}):
        _text(candidate.get("unknown_reason"), f"{label}.unknown_reason")
        return
    raise QaHandoffError(
        f"qa_verification.{label} must bind an exact candidate or explicit unknown"
    )


def _hashed_reference(value: JsonValue | None, label: str, *, identifier: str) -> None:
    reference = _object(value, label)
    _exact_fields(reference, frozenset({identifier, "sha256"}), label)
    _text(reference.get(identifier), f"{label}.{identifier}")
    _sha256(reference.get("sha256"), f"{label}.sha256")


def _actions(value: JsonValue | None) -> None:
    match value:
        case list() if 1 <= len(value) <= MAX_ACTIONS:
            for index, action in enumerate(value, start=1):
                action_object = _object(action, f"proof_cells.ordered_actions[{index}]")
                _exact_fields(
                    action_object,
                    frozenset({"sequence", "detail"}),
                    f"proof_cells.ordered_actions[{index}]",
                )
                sequence = action_object.get("sequence")
                if sequence != index:
                    raise QaHandoffError(
                        "qa_verification.proof_cells.ordered_actions must be ordered from 1"
                    )
                _text(action_object.get("detail"), f"proof_cells.ordered_actions[{index}].detail")
        case str() | int() | float() | bool() | None | dict() | list():
            raise QaHandoffError(
                "qa_verification.proof_cells.ordered_actions must be a non-empty bounded list"
            )
        case unreachable:
            assert_never(unreachable)


def _proof_cell(value: JsonValue, index: int) -> QaProofCell:
    cell = _object(value, f"proof_cells[{index}]")
    _exact_fields(
        cell,
        frozenset(
            {
                "criterion_or_risk",
                "candidate",
                "fixture",
                "environment",
                "initial_state",
                "ordered_actions",
                "binary_observable",
                "matching_surface",
                "expected_sanitized_artifact",
                "cleanup",
                "stop_condition",
                "status",
            }
        ),
        f"proof_cells[{index}]",
    )
    criterion = _text(cell.get("criterion_or_risk"), f"proof_cells[{index}].criterion_or_risk")
    _candidate(cell.get("candidate"), f"proof_cells[{index}].candidate")
    _hashed_reference(cell.get("fixture"), f"proof_cells[{index}].fixture", identifier="id")
    _hashed_reference(cell.get("environment"), f"proof_cells[{index}].environment", identifier="config_ref")
    _text(cell.get("initial_state"), f"proof_cells[{index}].initial_state")
    _actions(cell.get("ordered_actions"))
    observable = _object(cell.get("binary_observable"), f"proof_cells[{index}].binary_observable")
    _exact_fields(observable, frozenset({"assertion", "observed"}), f"proof_cells[{index}].binary_observable")
    _text(observable.get("assertion"), f"proof_cells[{index}].binary_observable.assertion")
    if not isinstance(observable.get("observed"), bool):
        raise QaHandoffError(f"qa_verification.proof_cells[{index}].binary_observable.observed must be boolean")
    _text(cell.get("matching_surface"), f"proof_cells[{index}].matching_surface")
    _hashed_reference(cell.get("expected_sanitized_artifact"), f"proof_cells[{index}].expected_sanitized_artifact", identifier="ref")
    _text(cell.get("cleanup"), f"proof_cells[{index}].cleanup")
    _text(cell.get("stop_condition"), f"proof_cells[{index}].stop_condition")
    status = _text(cell.get("status"), f"proof_cells[{index}].status")
    if status not in CELL_STATUSES:
        raise QaHandoffError(f"qa_verification.proof_cells[{index}].status is unsupported")
    return QaProofCell(criterion, status)


def _blocker(value: JsonValue, index: int) -> QaReleaseBlocker:
    blocker = _object(value, f"release_blockers[{index}]")
    _exact_fields(
        blocker,
        frozenset(
            {
                "id",
                "lane",
                "owner",
                "candidate",
                "next_check",
                "binary_artifact",
                "cleanup",
                "stop_condition",
                "status",
            }
        ),
        f"release_blockers[{index}]",
    )
    identifier = _text(blocker.get("id"), f"release_blockers[{index}].id")
    _text(blocker.get("lane"), f"release_blockers[{index}].lane")
    owner = _text(blocker.get("owner"), f"release_blockers[{index}].owner")
    _candidate(blocker.get("candidate"), f"release_blockers[{index}].candidate")
    _text(blocker.get("next_check"), f"release_blockers[{index}].next_check")
    artifact = _object(blocker.get("binary_artifact"), f"release_blockers[{index}].binary_artifact")
    _exact_fields(artifact, frozenset({"ref", "sha256", "status"}), f"release_blockers[{index}].binary_artifact")
    _text(artifact.get("ref"), f"release_blockers[{index}].binary_artifact.ref")
    _sha256(artifact.get("sha256"), f"release_blockers[{index}].binary_artifact.sha256")
    artifact_status = _text(artifact.get("status"), f"release_blockers[{index}].binary_artifact.status")
    if artifact_status not in BLOCKER_ARTIFACT_STATUSES:
        raise QaHandoffError(f"qa_verification.release_blockers[{index}].binary_artifact.status is unsupported")
    _text(blocker.get("cleanup"), f"release_blockers[{index}].cleanup")
    _text(blocker.get("stop_condition"), f"release_blockers[{index}].stop_condition")
    status = _text(blocker.get("status"), f"release_blockers[{index}].status")
    if status not in CELL_STATUSES:
        raise QaHandoffError(f"qa_verification.release_blockers[{index}].status is unsupported")
    return QaReleaseBlocker(identifier, owner, status)


def _parse_legacy_qa_verification(value: JsonValue | None) -> QaVerification:
    verification = _object(value, "")
    _exact_fields(verification, frozenset({"proof_cells", "release_blockers"}), "")
    raw_cells = verification.get("proof_cells")
    if not isinstance(raw_cells, list) or not raw_cells:
        raise QaHandoffError("qa_verification.proof_cells must be a non-empty list")
    cells = tuple(_proof_cell(cell, index) for index, cell in enumerate(raw_cells, start=1))
    raw_blockers = verification.get("release_blockers")
    if not isinstance(raw_blockers, list):
        raise QaHandoffError("qa_verification.release_blockers must be a list")
    blockers = tuple(_blocker(blocker, index) for index, blocker in enumerate(raw_blockers, start=1))
    return QaVerification(cells, blockers, False)


def parse_qa_verification(
    value: JsonValue | None,
    execution_version: str = LEGACY_VERSION,
) -> QaVerification | QaVerificationV2:
    if execution_version == LEGACY_VERSION:
        return _parse_legacy_qa_verification(value)
    if execution_version == CURRENT_VERSION:
        try:
            return parse_qa_verification_v2(value)
        except QaV2Error as exc:
            raise QaHandoffError(f"qa_verification: {exc}") from exc
    raise QaHandoffError("qa_verification execution version is unsupported")
