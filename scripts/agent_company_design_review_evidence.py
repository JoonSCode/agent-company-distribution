from __future__ import annotations

from dataclasses import dataclass

# pyright: reportImplicitRelativeImport=false
from agent_company_design_review_common import (
    DesignReviewContractError,
    configured_texts,
    exact,
    records,
    text,
)
from agent_company_design_review_context import TrustedReviewContext
from agent_company_role_schema import JsonValue


@dataclass(frozen=True, slots=True)
class ProvenanceContext:
    candidate_id: str | None
    scenario_environments: frozenset[str]
    ledger: dict[str, JsonValue]


def validate_provenance(
    payload: dict[str, JsonValue],
    context: ProvenanceContext,
) -> None:
    environment_fields = frozenset(
        configured_texts(context.ledger, "environment_provenance_fields")
    )
    environments: set[str] = set()
    for index, environment in enumerate(
        records(payload.get("environments"), "environments")
    ):
        if frozenset(environment) != environment_fields:
            raise DesignReviewContractError(
                "environment_provenance_incomplete",
                f"environments[{index}] fields differ",
            )
        environment_id = text(environment.get("environment_id"))
        width = environment.get("viewport_width")
        if (
            environment_id is None
            or environment.get("candidate_id") != context.candidate_id
            or any(
                text(environment.get(field)) is None
                for field in (
                    "platform",
                    "os_version",
                    "text_size",
                    "locale",
                    "input_mode",
                )
            )
            or not isinstance(width, int)
            or isinstance(width, bool)
            or width <= 0
            or not isinstance(environment.get("accessibility_settings"), list)
        ):
            code = (
                "candidate_inheritance_forbidden"
                if environment.get("candidate_id") != context.candidate_id
                else "environment_provenance_incomplete"
            )
            raise DesignReviewContractError(code, f"environments[{index}] is invalid")
        environments.add(environment_id)
    if environments != set(context.scenario_environments):
        raise DesignReviewContractError(
            "environment_provenance_incomplete",
            "scenario and environment identities differ",
        )

def validate_visual_contract(
    payload: dict[str, JsonValue],
    ledger: dict[str, JsonValue],
) -> None:
    motion_fields = frozenset(configured_texts(ledger, "motion_token_fields"))
    for index, token in enumerate(records(payload.get("motion_tokens"), "motion_tokens")):
        if frozenset(token) != motion_fields or any(
            text(token.get(field)) is None for field in motion_fields
        ):
            raise DesignReviewContractError(
                "motion_disposition_incomplete",
                f"motion_tokens[{index}] is incomplete",
            )

    reflow_fields = frozenset(
        configured_texts(ledger, "reflow_expectation_fields")
    )
    widths: list[int] = []
    for index, expectation in enumerate(
        records(payload.get("reflow_expectations"), "reflow_expectations")
    ):
        width = expectation.get("viewport_width")
        if (
            frozenset(expectation) != reflow_fields
            or not isinstance(width, int)
            or isinstance(width, bool)
            or width <= 0
            or any(
                text(expectation.get(field)) is None
                for field in reflow_fields - {"viewport_width"}
            )
        ):
            raise DesignReviewContractError(
                "reflow_expectation_invalid",
                f"reflow_expectations[{index}] is incomplete",
            )
        widths.append(width)
    if len(widths) < 2 or len(set(widths)) != len(widths):
        raise DesignReviewContractError(
            "reflow_expectation_invalid",
            "at least two distinct exact widths are required",
        )


def validate_verification_layers(
    payload: dict[str, JsonValue],
    context: TrustedReviewContext,
    ledger: dict[str, JsonValue],
) -> None:
    configured = {
        (text(item.get("layer_id")), text(item.get("evidence_kind")))
        for item in records(ledger.get("verification_layers"), "verification layers")
    }
    actual: set[tuple[str | None, str | None]] = set()
    for index, layer in enumerate(
        records(payload.get("verification_layers"), "verification_layers")
    ):
        exact(
            layer,
            frozenset({"layer_id", "evidence_kind", "verification_owner_id"}),
            f"verification_layers[{index}]",
        )
        owner_id = text(layer.get("verification_owner_id"))
        trusted_owners = {
            owner.owner_id: owner.role for owner in context.verification_owners
        }
        owner_role = trusted_owners.get(owner_id) if owner_id is not None else None
        if (
            owner_id is None
            or owner_role is None
            or owner_id == context.implementation_owner.owner_id
            or owner_role == context.implementation_owner.role
        ):
            raise DesignReviewContractError(
                "verification_owner_not_independent",
                f"verification_layers[{index}] owner is not independent",
            )
        actual.add((text(layer.get("layer_id")), text(layer.get("evidence_kind"))))
    if actual != configured or len(actual) != 3:
        raise DesignReviewContractError(
            "verification_layers_incomplete",
            "all three configured verification layers are required",
        )
