"""Typed values for the separate model-routing policy boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, override


# Contract support is not proof of availability on the selected host.
SUPPORTED_MODELS: Final[frozenset[str]] = frozenset({"gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-6-astra"})
SUPPORTED_EFFORTS: Final[frozenset[str]] = frozenset({"low", "medium", "high", "xhigh", "max"})
SUPPORTED_SERVICE_TIERS: Final[frozenset[str]] = frozenset({"default", "priority"})


class RateCardFreshness(StrEnum):
    """The deterministic usability state of an external rate observation."""

    FRESH = "fresh"
    REFRESH_DUE = "refresh_due"
    HARD_STALE = "hard_stale"
    INAPPLICABLE = "inapplicable"
    UNAVAILABLE = "unavailable"


class ModelProfileAuthority(StrEnum):
    """Authorities that may own a semantic model profile."""

    EXECUTOR = "executor"
    ROLE_LEAD = "role_lead"
    COMPANY_ROOT = "company_root"


@dataclass(frozen=True, slots=True)
class MeteredEquivalentRate:
    """Scheduled subscription-credit rate for one million tokens."""

    input_credits: float
    cached_input_credits: float
    output_credits: float


@dataclass(frozen=True, slots=True)
class ModelRoutingError(Exception):
    """A typed fail-closed error at a model-routing contract boundary."""

    code: str
    detail: str

    @override
    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class Rate:
    model_id: str
    metered_equivalent: MeteredEquivalentRate
    cache_write_billing: str
    provider_debited_credits: float | None
    currency_price: float | None
    effective_from: datetime | None

    @property
    def input_credits_per_million(self) -> float:
        return self.metered_equivalent.input_credits

    @property
    def cached_input_credits_per_million(self) -> float:
        return self.metered_equivalent.cached_input_credits

    @property
    def output_credits_per_million(self) -> float:
        return self.metered_equivalent.output_credits


@dataclass(frozen=True, slots=True)
class RateCard:
    path: Path
    reference: str
    sha256: str
    surface: str
    freshness: RateCardFreshness
    source_updated_at: datetime | None
    observed_at: datetime
    normalized_extracted_rate_digest: str
    rates: Mapping[str, Rate]
    cost_sensitive_enabled: bool
    verified_rate_schedule_enabled: bool


@dataclass(frozen=True, slots=True)
class ModelProfile:
    semantic_profile: str
    model_id: str
    reasoning_effort: str
    authority: ModelProfileAuthority
    dispatchable: bool
    administrative_status: str
    runtime_availability_required: bool
    service_tier_default: str
    speed_trait: str
    credit_trait: str
    allowed_task_types: tuple[str, ...]
    capability_rank: int
    capability_floor: int
    fallback_profile: str | None
    concurrency_cap: int
    rate_card_model_id: str


@dataclass(frozen=True, slots=True)
class ModelProfileRegistry:
    path: Path
    sha256: str
    rate_card_sha256: str
    cost_sensitive_enabled: bool
    profiles: Mapping[str, ModelProfile]


@dataclass(frozen=True, slots=True)
class RoutingPrecedenceRule:
    priority: int
    predicate_id: str
    disposition: str
    profile: str
    trigger_summary: str


@dataclass(frozen=True, slots=True)
class ModelRoutingPolicy:
    path: Path
    sha256: str
    required_inputs: tuple[str, ...]
    precedence: tuple[RoutingPrecedenceRule, ...]
