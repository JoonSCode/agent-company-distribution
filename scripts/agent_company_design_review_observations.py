from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
from datetime import datetime

from agent_company_design_review_common import (
    DesignReviewContractError,
    configured_texts,
    exact,
    records,
    text,
    texts,
)
from agent_company_design_review_context import TrustedReviewContext
from agent_company_role_schema import JsonValue


def _observed_at(value: JsonValue | None, index: int) -> datetime:
    raw = text(value)
    if raw is None:
        raise DesignReviewContractError(
            "observation_provenance_incomplete",
            f"observations[{index}].observed_at is required",
        )
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DesignReviewContractError(
            "observation_provenance_incomplete",
            f"observations[{index}].observed_at is invalid",
        ) from exc
    if parsed.tzinfo is None:
        raise DesignReviewContractError(
            "observation_provenance_incomplete",
            f"observations[{index}].observed_at must include a timezone",
        )
    return parsed


def validate_observation_coverage(
    payload: dict[str, JsonValue],
    candidate_id: str | None,
    ledger: dict[str, JsonValue],
    context: TrustedReviewContext,
) -> None:
    scenario_environments: dict[str, str] = {}
    for scenario in records(payload.get("scenarios"), "scenarios"):
        scenario_id = text(scenario.get("scenario_id"))
        environment_id = text(scenario.get("environment_id"))
        if scenario_id is not None and environment_id is not None:
            scenario_environments[scenario_id] = environment_id
    required_layers = frozenset(
        text(layer.get("layer_id"))
        for layer in records(ledger.get("verification_layers"), "verification layers")
    )
    if None in required_layers:
        raise DesignReviewContractError(
            "verification_layers_incomplete",
            "configured verification layer identities are invalid",
        )
    layer_owners: dict[str, str] = {}
    for index, layer in enumerate(
        records(payload.get("verification_layers"), "verification_layers")
    ):
        layer_id = text(layer.get("layer_id"))
        owner_id = text(layer.get("verification_owner_id"))
        if (
            layer_id is None
            or owner_id is None
            or layer_id in layer_owners
        ):
            raise DesignReviewContractError(
                "verification_layers_incomplete",
                f"verification_layers[{index}] has ambiguous ownership",
            )
        layer_owners[layer_id] = owner_id
    trusted_owner_ids = {owner.owner_id for owner in context.verification_owners}
    observation_fields = frozenset(
        configured_texts(ledger, "observation_provenance_fields")
    )
    observed_pairs: set[tuple[str, str]] = set()
    observation_ids: set[str] = set()
    observations = records(payload.get("observations"), "observations")
    if not observations:
        raise DesignReviewContractError(
            "observation_coverage_incomplete",
            "at least one fresh observation is required",
        )
    for index, observation in enumerate(observations):
        exact(observation, observation_fields, f"observations[{index}]")
        observation_id = text(observation.get("observation_id"))
        scenario_id = text(observation.get("scenario_id"))
        environment_id = text(observation.get("environment_id"))
        observer_id = text(observation.get("observer_id"))
        layer_ids = frozenset(
            texts(observation.get("evidence_layer_ids"), "evidence_layer_ids")
        )
        if observation.get("candidate_id") != candidate_id:
            raise DesignReviewContractError(
                "candidate_inheritance_forbidden",
                f"observations[{index}] binds a different candidate",
            )
        if (
            observation_id is None
            or observation_id in observation_ids
            or scenario_id not in scenario_environments
            or environment_id != scenario_environments.get(scenario_id)
            or observer_id is None
            or text(observation.get("method")) is None
            or not texts(observation.get("artifact_refs"), "artifact_refs")
            or not layer_ids
            or not layer_ids.issubset(required_layers)
        ):
            raise DesignReviewContractError(
                "observation_provenance_incomplete",
                f"observations[{index}] is not bound to the exact scenario and candidate",
            )
        expected_owners = {layer_owners.get(layer_id) for layer_id in layer_ids}
        if (
            observer_id == context.implementation_owner.owner_id
            or observer_id not in trusted_owner_ids
            or expected_owners != {observer_id}
        ):
            raise DesignReviewContractError(
                "observation_owner_mismatch",
                f"observations[{index}] owner differs from its trusted layer owner",
            )
        observed_at = _observed_at(observation.get("observed_at"), index)
        if not (
            context.task_started_at
            <= observed_at
            <= context.evidence_deadline_at
        ):
            raise DesignReviewContractError(
                "observation_not_fresh",
                f"observations[{index}] falls outside the trusted task window",
            )
        observation_ids.add(observation_id)
        observed_pairs.update((scenario_id, layer_id) for layer_id in layer_ids)
    expected_pairs = {
        (scenario_id, layer_id)
        for scenario_id in scenario_environments
        for layer_id in required_layers
    }
    if observed_pairs != expected_pairs:
        raise DesignReviewContractError(
            "observation_coverage_incomplete",
            "every named scenario requires fresh evidence for every verification layer",
        )
