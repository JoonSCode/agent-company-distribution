from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import copy
from pathlib import Path

from agent_company_deps import JsonValue
from agent_company_plan_models import PlanError, object_value
from agent_company_qa_handoff import (
    CURRENT_VERSION as QA_EXECUTION_VERSION,
)
from agent_company_qa_handoff import (
    QaHandoffError,
    parse_qa_verification,
)


def qa_plan_binding(
    raw: dict[str, JsonValue],
    role: str,
    path: Path,
) -> JsonValue | None:
    """Return the validated, isolated QA contract for one role plan."""
    if role != "qa-release":
        if "qa_verification" in raw:
            raise PlanError(
                "malformed_input",
                f"{path}.qa_verification",
                "is only supported for qa-release",
            )
        return None
    qa_verification = object_value(
        raw.get("qa_verification"),
        f"{path}.qa_verification",
    )
    try:
        _ = parse_qa_verification(
            qa_verification,
            QA_EXECUTION_VERSION,
        )
    except QaHandoffError as exc:
        raise PlanError(
            "malformed_input",
            f"{path}.qa_verification",
            str(exc),
        ) from exc
    return copy.deepcopy(qa_verification)
