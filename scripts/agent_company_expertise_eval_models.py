from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, final, override

from agent_company_role_schema import JsonValue

type EvaluationCommand = Literal["plan", "status", "run-next", "summarize"]


class EvaluationArguments(argparse.Namespace):
    """Mutable command namespace populated by argparse."""

    command: EvaluationCommand = "plan"
    run_root: Path | None = None
    max_calls: int = 1


def parse_evaluation_args(argv: list[str]) -> EvaluationArguments:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    _ = sub.add_parser("plan")
    status = sub.add_parser("status")
    _ = status.add_argument("--run-root", type=Path, required=True)
    run = sub.add_parser("run-next")
    _ = run.add_argument("--run-root", type=Path, required=True)
    _ = run.add_argument("--max-calls", type=int, default=1)
    summarize = sub.add_parser("summarize")
    _ = summarize.add_argument("--run-root", type=Path, required=True)
    parsed = EvaluationArguments()
    _ = parser.parse_args(argv, namespace=parsed)
    return parsed


@final
class ExpertiseEvaluationError(Exception):
    __slots__ = ("code", "detail")

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)
        self.code = code
        self.detail = detail

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class EvaluationPolicy:
    path: Path
    sha256: str
    baseline_commit: str
    model: str
    reasoning_effort: str
    repeats: int
    timeout_seconds: int
    max_concurrency: int
    persistent_workers: bool
    background_workers: bool
    quality_gates: dict[str, int | float]


@dataclass(frozen=True, slots=True)
class EvaluationCriterion:
    criterion_id: str
    max_points: int
    full_credit: str


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    task_type: str
    prompt: str
    supplied_evidence: tuple[dict[str, JsonValue], ...]
    hidden_rubric: tuple[EvaluationCriterion, ...]
    critical_failures: tuple[str, ...]
    expected_reference_ids: tuple[str, ...]
    specialist_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RoleEvaluationSuite:
    role: str
    path: Path
    sha256: str
    cases: tuple[EvaluationCase, ...]


@dataclass(frozen=True, slots=True)
class EvaluationAction:
    sequence: int
    kind: str
    lane: str
    role: str
    repeat_id: str
    case_ids: tuple[str, ...]
    ablated_specialist_id: str | None


@dataclass(frozen=True, slots=True)
class EvaluationMaterial:
    material_id: str
    source_ref: str
    sha256: str
    content: str
    case_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExecutionBundle:
    role: str
    repeat_id: str
    lane: str
    case_ids: tuple[str, ...]
    specialist_ids: tuple[str, ...]
    ablated_specialist_id: str | None
    material_ids: frozenset[str]
    materials: tuple[EvaluationMaterial, ...]
    prompt: str
    prompt_sha256: str


@dataclass(frozen=True, slots=True)
class BlindReviewBundle:
    role: str
    repeat_id: str
    case_ids: tuple[str, ...]
    label_map: dict[str, dict[str, str]]
    prompt: str
    prompt_sha256: str


@dataclass(frozen=True, slots=True)
class ModelUsage:
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None


@dataclass(frozen=True, slots=True)
class ModelCallResult:
    output: dict[str, JsonValue]
    events: bytes
    diagnostics: bytes
    elapsed_ms: int
    effective_model: str | None
    usage: ModelUsage
    tool_count: int


@dataclass(frozen=True, slots=True)
class BlindReviewScores:
    points: dict[str, dict[str, int]]
    critical_failure_ids: dict[str, dict[str, tuple[str, ...]]]


@dataclass(frozen=True, slots=True)
class AttemptMetrics:
    tokens: int
    elapsed_ms: int
    tool_count: int


@dataclass(frozen=True, slots=True)
class EvaluationObservations:
    review_scores: dict[tuple[str, str], BlindReviewScores]
    attempt_metrics: dict[tuple[str, str, str], AttemptMetrics]
