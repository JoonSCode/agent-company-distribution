from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HandoffValidation:
    valid: bool
    output_ref: str | None
    reason: str
    context_id: str | None
    knowledge_receipt_id: str | None
    required_reference_ids: tuple[str, ...]
    outcome: str | None
    assignment_bound: bool


class HandoffContractError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)

    def __str__(self) -> str:
        return self.detail
