"""Load the source-bound, refreshable subscription-credit rate-card contract."""

from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportUnnecessaryComparison=false
import hashlib
import json
import math
import re
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Final, assert_never

from agent_company_expertise_eval_encoding import parse_json_object
from agent_company_expertise_eval_io import read_bytes, require_inside
from agent_company_expertise_eval_models import ExpertiseEvaluationError
from agent_company_model_routing_models import (
    MeteredEquivalentRate,
    ModelRoutingError,
    Rate,
    RateCard,
    RateCardFreshness,
)
from agent_company_role_schema import JsonValue

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
RATE_CARD_REF: Final[str] = "policies/model-rate-card.json"
MAX_RATE_CARD_BYTES: Final[int] = 256_000
FORMAT: Final[str] = "agent-company.model-rate-card/v0.1"
SURFACE: Final[str] = "standard_chatgpt_subscription_credit"

RateCardError = ModelRoutingError


class _Availability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INAPPLICABLE = "inapplicable"


def _text(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RateCardError("rate_card_malformed", f"{label} must be nonempty text")
    return value


def _object(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise RateCardError("rate_card_malformed", f"{label} must be an object")
    return value


def _objects(value: JsonValue | None, label: str) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list):
        raise RateCardError("rate_card_malformed", f"{label} must be a list")
    return tuple(_object(item, f"{label}[{index}]") for index, item in enumerate(value))


def _number(value: JsonValue | None, label: str, *, nullable: bool = False, positive: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        detail = f"scheduled metered {label} must be positive" if positive else f"{label} must be nonnegative"
        raise RateCardError("rate_card_malformed", detail)
    if not math.isfinite(value):
        raise RateCardError("rate_card_malformed", f"{label} must be finite")
    if value < 0 or positive and value == 0:
        detail = f"scheduled metered {label} must be positive" if positive else f"{label} must be nonnegative"
        raise RateCardError("rate_card_malformed", detail)
    return float(value)


def _timestamp(value: JsonValue | None, label: str, *, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RateCardError("rate_card_malformed", f"{label} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise RateCardError("rate_card_malformed", f"{label} requires an offset")
    return parsed.astimezone(UTC)


def _read(root: Path) -> tuple[dict[str, JsonValue], bytes, Path]:
    try:
        path = require_inside(root, root / RATE_CARD_REF)
        content = read_bytes(path, MAX_RATE_CARD_BYTES)
    except ExpertiseEvaluationError as exc:
        raise RateCardError("rate_card_unsafe", RATE_CARD_REF) from exc
    try:
        return parse_json_object(content, str(path)), content, path
    except ExpertiseEvaluationError as exc:
        raise RateCardError("rate_card_malformed", RATE_CARD_REF) from exc


def normalized_rate_digest(surface: str, rates: tuple[Rate, ...]) -> str:
    """Hash the stable surface plus sorted normalized rate evidence."""
    rows: list[dict[str, JsonValue]] = []
    for rate in sorted(rates, key=lambda item: item.model_id):
        rows.append({"model_id": rate.model_id, "metered_equivalent_credits_per_million": {"input": rate.input_credits_per_million, "cached_input": rate.cached_input_credits_per_million, "output": rate.output_credits_per_million}, "cache_write_billing": rate.cache_write_billing, "provider_debited_credits": rate.provider_debited_credits, "currency_price": rate.currency_price, "effective_from": None if rate.effective_from is None else rate.effective_from.isoformat().replace("+00:00", "Z")})
    encoded = json.dumps({"surface": surface, "rates": rows}, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _freshness(availability: _Availability, surface: str, observed_at: datetime, now: datetime, refresh_after: int, hard_stale_after: int) -> RateCardFreshness:
    match availability:
        case _Availability.UNAVAILABLE:
            return RateCardFreshness.UNAVAILABLE
        case _Availability.INAPPLICABLE:
            return RateCardFreshness.INAPPLICABLE
        case _Availability.AVAILABLE:
            pass
        case unreachable:
            assert_never(unreachable)
    if surface != SURFACE:
        return RateCardFreshness.INAPPLICABLE
    age = (now - observed_at).total_seconds()
    if age > hard_stale_after:
        return RateCardFreshness.HARD_STALE
    if age > refresh_after:
        return RateCardFreshness.REFRESH_DUE
    return RateCardFreshness.FRESH


def load_model_rate_card(root: Path = ROOT, now: datetime | None = None) -> RateCard:
    """Parse one no-follow rate card with a mandatory aware injected clock."""
    if now is None or now.tzinfo is None:
        raise RateCardError("rate_card_clock", "now must be timezone-aware")
    payload, content, path = _read(root)
    if set(payload) != {"format", "availability", "surface", "source", "freshness_policy", "rates"} or payload.get("format") != FORMAT:
        raise RateCardError("rate_card_malformed", "unsupported header")
    try:
        availability = _Availability(_text(payload.get("availability"), "availability"))
    except ValueError as exc:
        raise RateCardError("rate_card_malformed", "availability is invalid") from exc
    surface = _text(payload.get("surface"), "surface")
    source = _object(payload.get("source"), "source")
    if set(source) != {"primary_url", "corroborating_url", "source_updated_at", "observed_at", "normalized_extracted_rate_digest"}:
        raise RateCardError("rate_card_malformed", "source shape is invalid")
    # Preserve historical two-source observations; a directly observed official
    # pricing page may leave independent corroboration explicitly unknown.
    source_pair = (source.get("primary_url"), source.get("corroborating_url"))
    if source_pair not in (
        ("https://help.openai.com/en/articles/20001106-codex-rate-card", "https://learn.chatgpt.com/docs/pricing"),
        ("https://learn.chatgpt.com/docs/pricing", None),
    ):
        raise RateCardError("rate_card_malformed", "source URL roles are invalid")
    source_updated_at = _timestamp(source.get("source_updated_at"), "source_updated_at", nullable=True)
    observed_at = _timestamp(source.get("observed_at"), "observed_at")
    if observed_at is None or source_updated_at is not None and source_updated_at > observed_at:
        raise RateCardError("rate_card_malformed", "source timestamps are invalid")
    digest = _text(source.get("normalized_extracted_rate_digest"), "normalized_extracted_rate_digest")
    if re.fullmatch(r"[a-f0-9]{64}", digest) is None:
        raise RateCardError("rate_card_malformed", "rate digest is invalid")
    freshness = _object(payload.get("freshness_policy"), "freshness_policy")
    refresh_after = freshness.get("refresh_after_seconds")
    hard_stale_after = freshness.get("hard_stale_after_seconds")
    if set(freshness) != {"refresh_after_seconds", "hard_stale_after_seconds", "policy_label"} or not isinstance(refresh_after, int) or not isinstance(hard_stale_after, int) or isinstance(refresh_after, bool) or isinstance(hard_stale_after, bool) or refresh_after < 1 or hard_stale_after <= refresh_after or freshness.get("policy_label") != "agent_company_policy":
        raise RateCardError("rate_card_malformed", "freshness policy is invalid")
    rates: dict[str, Rate] = {}
    for raw in _objects(payload.get("rates"), "rates"):
        if set(raw) != {"model_id", "credits_per_million", "cache_write_billing", "currency_price", "provider_debited_credits", "effective_from"}:
            raise RateCardError("rate_card_malformed", "rate shape is invalid")
        model_id = _text(raw.get("model_id"), "model_id")
        credits = _object(raw.get("credits_per_million"), "credits_per_million")
        if set(credits) != {"input", "cached_input", "output"} or model_id in rates:
            raise RateCardError("rate_card_malformed", "rates must be unique and complete")
        cache_write = _text(raw.get("cache_write_billing"), "cache_write_billing")
        if cache_write not in {"not_charged", "unknown"}:
            raise RateCardError("rate_card_malformed", "cache-write billing is invalid")
        input_credits = _number(credits.get("input"), "input", positive=True)
        cached_credits = _number(credits.get("cached_input"), "cached_input", positive=True)
        output_credits = _number(credits.get("output"), "output", positive=True)
        if input_credits is None or cached_credits is None or output_credits is None:
            raise RateCardError("rate_card_malformed", "metered equivalent is required")
        rates[model_id] = Rate(model_id, MeteredEquivalentRate(input_credits, cached_credits, output_credits), cache_write, _number(raw.get("provider_debited_credits"), "provider_debited_credits", nullable=True), _number(raw.get("currency_price"), "currency_price", nullable=True), _timestamp(raw.get("effective_from"), "effective_from", nullable=True))
    if set(rates) not in ({"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}, {"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-6-astra"}):
        raise RateCardError("rate_card_malformed", "all official model rows are required")
    if normalized_rate_digest(surface, tuple(rates.values())) != digest:
        raise RateCardError("rate_card_digest", "normalized rate rows disagree with digest")
    normalized_now = now.astimezone(UTC)
    if normalized_now < observed_at:
        raise RateCardError("rate_card_clock", "now precedes observed_at")
    status = _freshness(availability, surface, observed_at, normalized_now, refresh_after, hard_stale_after)
    cost_sensitive_enabled = status in {RateCardFreshness.FRESH, RateCardFreshness.REFRESH_DUE}
    verified_rate_schedule_enabled = status == RateCardFreshness.FRESH
    return RateCard(path, RATE_CARD_REF, hashlib.sha256(content).hexdigest(), surface, status, source_updated_at, observed_at, digest, MappingProxyType(rates), cost_sensitive_enabled, verified_rate_schedule_enabled)
