from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportUnnecessaryComparison=false, reportUnusedCallResult=false
from dataclasses import dataclass
from typing import Final, Literal, assert_never, override

from agent_company_deps import JsonValue

RecommendationKind = Literal["selected", "blocked", "evidence_only"]

MAX_TEXT: Final[int] = 500
MAX_ITEMS: Final[int] = 30
SHA256_LENGTH: Final[int] = 64
DISPOSITIONS: Final[frozenset[str]] = frozenset({"material", "preserved", "not_applicable", "unknown"})
CLAIM_STATUSES: Final[frozenset[str]] = frozenset({"known", "proposed", "unknown"})
RECOMMENDATIONS: Final[frozenset[str]] = frozenset({"selected", "blocked", "evidence_only"})
RECOMMENDATION_VALUES: Final[dict[str, RecommendationKind]] = {
    "selected": "selected",
    "blocked": "blocked",
    "evidence_only": "evidence_only",
}
EVIDENCE_KINDS: Final[frozenset[str]] = frozenset({
    "implementation", "independent_security", "recovery_exercise",
})
CONTROL_FIELDS: Final[dict[str, frozenset[str]]] = {
    "migration": frozenset((
        "last_known_good", "rollback_dependency", "rollback_dependency_detail",
        "forward_recovery", "cleanup_owner", "irreversible_transition_disclosure",
    )),
    "trust_boundary": frozenset((
        "replay_control", "signer_key_loss_response", "compromise_response",
        "independent_security_evidence_id",
    )),
    "distributed_serving": frozenset((
        "authoritative_serving", "cache_propagation", "monitoring",
        "served_state_oracle",
    )),
    "break_glass_recovery": frozenset((
        "access_path", "recovery_dependency", "circular_access_dependency",
        "evidence_id",
    )),
}


@dataclass(frozen=True, slots=True)
class ArchitectureSafetyPacket:
    recommendation_kind: RecommendationKind
    blocking_unknowns: tuple[str, ...]
    material_domains: tuple[str, ...]
    claim_count: int


@dataclass(frozen=True, slots=True)
class ArchitectureSafetyError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return self.detail


def _object(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    match value:
        case dict():
            return value
        case str() | int() | float() | bool() | None | list():
            raise ArchitectureSafetyError(f"{label} must be an object")
        case unreachable:
            assert_never(unreachable)


def _list(value: JsonValue | None, label: str, *, allow_empty: bool) -> list[JsonValue]:
    match value:
        case list() if len(value) <= MAX_ITEMS and (allow_empty or value):
            return value
        case str() | int() | float() | bool() | None | dict() | list():
            qualifier = "bounded" if allow_empty else "non-empty bounded"
            raise ArchitectureSafetyError(f"{label} must be a {qualifier} list")
        case unreachable:
            assert_never(unreachable)


def _text(value: JsonValue | None, label: str) -> str:
    match value:
        case str() if value.strip() and len(value) <= MAX_TEXT:
            return value
        case str() | int() | float() | bool() | None | list() | dict():
            raise ArchitectureSafetyError(f"{label} must be bounded non-empty text")
        case unreachable:
            assert_never(unreachable)


def _boolean(value: JsonValue | None, label: str) -> bool:
    match value:
        case bool():
            return value
        case str() | int() | float() | None | list() | dict():
            raise ArchitectureSafetyError(f"{label} must be boolean")
        case unreachable:
            assert_never(unreachable)


def _exact_fields(value: dict[str, JsonValue], fields: frozenset[str], label: str) -> None:
    if frozenset(value) != fields:
        raise ArchitectureSafetyError(f"{label} must contain exactly {sorted(fields)}")


def _sha256(value: JsonValue | None, label: str) -> str:
    digest = _text(value, label)
    if len(digest) != SHA256_LENGTH or any(char not in "0123456789abcdef" for char in digest):
        raise ArchitectureSafetyError(f"{label} must be a SHA-256 digest")
    return digest


def _issued_evidence(value: JsonValue | None) -> dict[str, str]:
    records = _list(value, "issued_evidence", allow_empty=False)
    identifiers: dict[str, str] = {}
    for index, raw in enumerate(records, start=1):
        label = f"issued_evidence[{index}]"
        record = _object(raw, label)
        _exact_fields(record, frozenset({"id", "kind", "ref", "sha256"}), label)
        identifier = _text(record.get("id"), f"{label}.id")
        if identifier in identifiers:
            raise ArchitectureSafetyError("issued_evidence ids must be unique")
        kind = _text(record.get("kind"), f"{label}.kind")
        if kind not in EVIDENCE_KINDS:
            raise ArchitectureSafetyError(f"{label}.kind is unsupported")
        _text(record.get("ref"), f"{label}.ref")
        _sha256(record.get("sha256"), f"{label}.sha256")
        identifiers[identifier] = kind
    return identifiers


def _claims(value: JsonValue | None, evidence_ids: dict[str, str]) -> int:
    records = _list(value, "claims", allow_empty=False)
    for index, raw in enumerate(records, start=1):
        label = f"claims[{index}]"
        claim = _object(raw, label)
        _exact_fields(claim, frozenset({"claim", "status", "evidence_ids"}), label)
        _text(claim.get("claim"), f"{label}.claim")
        status = _text(claim.get("status"), f"{label}.status")
        if status not in CLAIM_STATUSES:
            raise ArchitectureSafetyError(f"{label}.status is unsupported")
        bindings = tuple(
            _text(item, f"{label}.evidence_ids")
            for item in _list(claim.get("evidence_ids"), f"{label}.evidence_ids", allow_empty=True)
        )
        if status == "known" and not bindings:
            raise ArchitectureSafetyError(f"{label} known claim requires issued evidence")
        if any(binding not in evidence_ids for binding in bindings):
            raise ArchitectureSafetyError(f"{label} references evidence outside issued evidence")
    return len(records)


def _dispositions(value: JsonValue | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    records = _list(value, "domain_dispositions", allow_empty=False)
    material: list[str] = []
    blocking: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(records, start=1):
        label = f"domain_dispositions[{index}]"
        record = _object(raw, label)
        _exact_fields(
            record,
            frozenset({"domain", "disposition", "rationale", "decision_blocking"}),
            label,
        )
        domain = _text(record.get("domain"), f"{label}.domain")
        if domain in seen:
            raise ArchitectureSafetyError("domain_dispositions domains must be unique")
        seen.add(domain)
        disposition = _text(record.get("disposition"), f"{label}.disposition")
        if disposition not in DISPOSITIONS:
            raise ArchitectureSafetyError(f"{label}.disposition is unsupported")
        _text(record.get("rationale"), f"{label}.rationale")
        decision_blocking = _boolean(
            record.get("decision_blocking"), f"{label}.decision_blocking"
        )
        if decision_blocking and disposition != "unknown":
            raise ArchitectureSafetyError("only unknown disposition may block a decision")
        if disposition == "material":
            material.append(domain)
        if decision_blocking:
            blocking.append(domain)
    return tuple(material), tuple(blocking)


def _recommendation(value: JsonValue | None, blocking: tuple[str, ...]) -> RecommendationKind:
    record = _object(value, "recommendation")
    _exact_fields(record, frozenset({"kind", "detail"}), "recommendation")
    kind = _text(record.get("kind"), "recommendation.kind")
    if kind not in RECOMMENDATIONS:
        raise ArchitectureSafetyError("recommendation.kind is unsupported")
    _text(record.get("detail"), "recommendation.detail")
    if blocking and kind not in {"blocked", "evidence_only"}:
        raise ArchitectureSafetyError(
            "blocking unknown permits only blocked or evidence_only recommendation"
        )
    return RECOMMENDATION_VALUES[kind]


def _control(
    packet: dict[str, JsonValue],
    domain: str,
    evidence_ids: dict[str, str],
) -> None:
    value = packet.get(domain)
    if value is None:
        raise ArchitectureSafetyError(f"material {domain} requires its safety control")
    control = _object(value, domain)
    fields = CONTROL_FIELDS[domain]
    _exact_fields(control, fields, domain)
    for field in fields - {"circular_access_dependency"}:
        if domain == "distributed_serving" and field == "monitoring":
            monitoring = _object(control.get(field), f"{domain}.{field}")
            _exact_fields(
                monitoring,
                frozenset({"signal", "owner", "stop_action"}),
                f"{domain}.{field}",
            )
            for monitoring_field in monitoring:
                _text(
                    monitoring.get(monitoring_field),
                    f"{domain}.{field}.{monitoring_field}",
                )
            continue
        if domain == "migration" and field == "rollback_dependency":
            dependency = _text(control.get(field), f"{domain}.{field}")
            if dependency not in {"dependent", "independent"}:
                raise ArchitectureSafetyError(
                    "migration.rollback_dependency must be dependent or independent"
                )
            continue
        _text(control.get(field), f"{domain}.{field}")
    if domain == "break_glass_recovery" and _boolean(
        control.get("circular_access_dependency"),
        "break_glass_recovery.circular_access_dependency",
    ):
        raise ArchitectureSafetyError(
            "break_glass_recovery has a circular access dependency"
        )
    evidence_requirement = {
        "trust_boundary": (
            "independent_security_evidence_id",
            "independent_security",
        ),
        "break_glass_recovery": ("evidence_id", "recovery_exercise"),
    }.get(domain)
    if evidence_requirement is None:
        return
    evidence_field, required_kind = evidence_requirement
    evidence_id = _text(control.get(evidence_field), f"{domain}.{evidence_field}")
    if evidence_ids.get(evidence_id) != required_kind:
        raise ArchitectureSafetyError(
            f"{domain} requires issued {required_kind} evidence"
        )


def parse_architecture_safety_packet(
    value: JsonValue | None,
) -> ArchitectureSafetyPacket:
    packet = _object(value, "architecture_safety")
    _exact_fields(
        packet,
        frozenset({
            "issued_evidence",
            "claims",
            "domain_dispositions",
            "recommendation",
            "migration",
            "trust_boundary",
            "distributed_serving",
            "break_glass_recovery",
        }),
        "architecture_safety",
    )
    evidence_ids = _issued_evidence(packet.get("issued_evidence"))
    claim_count = _claims(packet.get("claims"), evidence_ids)
    material, blocking = _dispositions(packet.get("domain_dispositions"))
    recommendation = _recommendation(packet.get("recommendation"), blocking)
    for domain in material:
        if domain in CONTROL_FIELDS:
            _control(packet, domain, evidence_ids)
    return ArchitectureSafetyPacket(recommendation, blocking, material, claim_count)
