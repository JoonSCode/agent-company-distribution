from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportImplicitOverride=false
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from agent_company_role_schema import JsonValue, load_json_file


@dataclass(frozen=True, slots=True)
class DesignReviewContractError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


ROOT: Final[Path] = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final[Path] = (
    ROOT / "skills/design-operating-system/references/design-contract.json"
)


def record(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise DesignReviewContractError(
            "review_shape_invalid",
            f"{label} must be an object",
        )
    return value


def records(
    value: JsonValue | None,
    label: str,
) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list):
        raise DesignReviewContractError(
            "review_shape_invalid",
            f"{label} must be a list",
        )
    return tuple(record(item, f"{label}[{index}]") for index, item in enumerate(value))


def texts(value: JsonValue | None, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise DesignReviewContractError(
            "review_shape_invalid",
            f"{label} must contain text",
        )
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise DesignReviewContractError(
                "review_shape_invalid",
                f"{label} must contain text",
            )
        result.append(item)
    return tuple(result)


def text(value: JsonValue | None) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def exact(
    value: dict[str, JsonValue],
    fields: frozenset[str],
    label: str,
) -> None:
    if frozenset(value) != fields:
        raise DesignReviewContractError(
            "review_shape_invalid",
            f"{label} fields differ: {sorted(set(value) ^ fields)}",
        )


def contract_ledger() -> dict[str, JsonValue]:
    parsed, issue = load_json_file(CONTRACT_PATH)
    if issue is not None or parsed is None:
        raise DesignReviewContractError(
            "review_contract_unavailable",
            "Design implementation review ledger could not be loaded",
        )
    contract = record(parsed, "design contract")
    return record(contract.get("implementation_review_ledger"), "review ledger")


def configured_texts(
    ledger: dict[str, JsonValue],
    field: str,
) -> tuple[str, ...]:
    return texts(ledger.get(field), f"review ledger.{field}")
