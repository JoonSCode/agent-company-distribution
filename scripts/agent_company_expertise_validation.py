from __future__ import annotations

import re
from datetime import date
from typing import Final

from agent_company_role_schema import JsonValue

ROLES: Final[frozenset[str]] = frozenset(
    {"founder", "planning", "marketing", "design", "development", "qa-release"}
)
LAYERS: Final[tuple[str, ...]] = (
    "role_kernel",
    "task_pack",
    "current_source_set",
    "job_evidence",
    "evaluation_set",
)
SEMVER: Final[re.Pattern[str]] = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA256: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
ROLE_FIELDS: Final[frozenset[str]] = frozenset({
    "role_id", "role_os_skill", "role_kernel_id", "default_task_type",
    "default_verifier", "optional_specialists",
})
SPECIALIST_FIELDS: Final[frozenset[str]] = frozenset({
    "skill_id", "selection_status", "task_types", "decision_questions", "distinct_evidence",
    "allowed_use", "loading_cost", "stop_condition",
})
REFERENCE_REQUIRED: Final[frozenset[str]] = frozenset({
    "id", "version", "layer", "owner_role", "ref", "sha256",
    "applies_to_tasks", "decision_questions", "authority_class", "allowed_uses",
    "freshness", "loading_cost", "dependencies", "conflicts", "evaluation_refs",
    "status", "replaced_by",
})
REFERENCE_FIELDS: Final[frozenset[str]] = REFERENCE_REQUIRED | {"source_url"}
FRESHNESS_REQUIRED: Final[frozenset[str]] = frozenset(
    {"mode", "reviewed_at", "recheck_triggers"}
)
FRESHNESS_FIELDS: Final[frozenset[str]] = FRESHNESS_REQUIRED | {"expires_at"}


class CatalogShapeError(Exception):
    pass


def _object(value: JsonValue | None, field: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise CatalogShapeError(f"{field} must be an object")
    return value


def _objects(value: JsonValue | None, field: str) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list):
        raise CatalogShapeError(f"{field} must be a list")
    return tuple(_object(item, f"{field}[{index}]") for index, item in enumerate(value))


def _text(value: JsonValue | None, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogShapeError(f"{field} must be non-empty text")
    return value


def _texts(value: JsonValue | None, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CatalogShapeError(f"{field} must be a list")
    result = tuple(_text(item, field) for item in value)
    if len(result) != len(set(result)):
        raise CatalogShapeError(f"{field} must be unique")
    return result


def _exact(
    value: dict[str, JsonValue],
    required: frozenset[str],
    allowed: frozenset[str],
    field: str,
) -> None:
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing or unknown:
        raise CatalogShapeError(f"{field} has missing={missing} unknown={unknown}")


def _enum(value: JsonValue | None, allowed: set[str] | frozenset[str], field: str) -> str:
    selected = _text(value, field)
    if selected not in allowed:
        raise CatalogShapeError(f"{field} has an unsupported value")
    return selected


def _date(value: JsonValue | None, field: str) -> str:
    selected = _text(value, field)
    try:
        date.fromisoformat(selected)
    except ValueError as exc:
        raise CatalogShapeError(f"{field} must be an ISO date") from exc
    return selected


def validate_registry_document(registry: dict[str, JsonValue]) -> None:
    fields = frozenset({"format", "schema_version", "default_specialist_limit", "roles"})
    _exact(registry, fields, fields, "registry")
    if (
        registry.get("format") != "agent-company.expertise-registry/v0.1"
        or registry.get("schema_version") != "0.1"
        or registry.get("default_specialist_limit") != 2
    ):
        raise CatalogShapeError("registry header is unsupported")
    roles = _objects(registry.get("roles"), "roles")
    if len(roles) != 6:
        raise CatalogShapeError("registry must contain six roles")
    seen: set[str] = set()
    for index, role in enumerate(roles):
        _exact(role, ROLE_FIELDS, ROLE_FIELDS, f"roles[{index}]")
        role_id = _enum(role.get("role_id"), ROLES, f"roles[{index}].role_id")
        if role_id in seen:
            raise CatalogShapeError(f"duplicate role: {role_id}")
        seen.add(role_id)
        for field in ("role_os_skill", "role_kernel_id", "default_task_type", "default_verifier"):
            _text(role.get(field), f"roles[{index}].{field}")
        specialists = _objects(role.get("optional_specialists"), f"roles[{index}].optional_specialists")
        specialist_ids: set[str] = set()
        for specialist_index, specialist in enumerate(specialists):
            label = f"roles[{index}].optional_specialists[{specialist_index}]"
            _exact(specialist, SPECIALIST_FIELDS, SPECIALIST_FIELDS, label)
            skill_id = _text(specialist.get("skill_id"), f"{label}.skill_id")
            if skill_id in specialist_ids:
                raise CatalogShapeError(f"duplicate specialist: {skill_id}")
            specialist_ids.add(skill_id)
            _enum(
                specialist.get("selection_status"),
                {"automatic", "shadow_only", "demoted"},
                f"{label}.selection_status",
            )
            _texts(specialist.get("task_types"), f"{label}.task_types")
            _texts(specialist.get("decision_questions"), f"{label}.decision_questions")
            _text(specialist.get("distinct_evidence"), f"{label}.distinct_evidence")
            _enum(
                specialist.get("allowed_use"),
                {"decision_support", "evidence_gathering", "implementation", "verification"},
                f"{label}.allowed_use",
            )
            _enum(specialist.get("loading_cost"), {"small", "medium", "large"}, f"{label}.loading_cost")
            _text(specialist.get("stop_condition"), f"{label}.stop_condition")
    if seen != set(ROLES):
        raise CatalogShapeError("registry roles differ from the canonical six")


def validate_manifest_document(manifest: dict[str, JsonValue]) -> None:
    fields = frozenset({"format", "schema_version", "supported_layers", "references"})
    _exact(manifest, fields, fields, "manifest")
    if (
        manifest.get("format") != "agent-company.reference-manifest/v0.1"
        or manifest.get("schema_version") != "0.1"
    ):
        raise CatalogShapeError("manifest header is unsupported")
    if _texts(manifest.get("supported_layers"), "supported_layers") != LAYERS:
        raise CatalogShapeError("manifest must declare the exact five reference layers")
    references = _objects(manifest.get("references"), "references")
    if len(references) < 6:
        raise CatalogShapeError("manifest must contain at least six references")
    seen: set[str] = set()
    for index, reference in enumerate(references):
        label = f"references[{index}]"
        _exact(reference, REFERENCE_REQUIRED, REFERENCE_FIELDS, label)
        reference_id = _text(reference.get("id"), f"{label}.id")
        if reference_id in seen:
            raise CatalogShapeError(f"duplicate reference: {reference_id}")
        seen.add(reference_id)
        version = _text(reference.get("version"), f"{label}.version")
        digest = _text(reference.get("sha256"), f"{label}.sha256")
        if SEMVER.fullmatch(version) is None or SHA256.fullmatch(digest) is None:
            raise CatalogShapeError(f"{label} has an invalid version or digest")
        _enum(reference.get("layer"), set(LAYERS), f"{label}.layer")
        _enum(reference.get("owner_role"), ROLES, f"{label}.owner_role")
        _text(reference.get("ref"), f"{label}.ref")
        source_url = reference.get("source_url")
        if source_url is not None:
            _text(source_url, f"{label}.source_url")
        for field in (
            "applies_to_tasks", "decision_questions", "allowed_uses",
            "dependencies", "conflicts", "evaluation_refs",
        ):
            _texts(reference.get(field), f"{label}.{field}")
        _enum(
            reference.get("authority_class"),
            {"canonical", "primary", "operational", "vetted_reference", "inspiration_only"},
            f"{label}.authority_class",
        )
        _enum(reference.get("loading_cost"), {"small", "medium", "large"}, f"{label}.loading_cost")
        status = _enum(reference.get("status"), {"active", "deprecated", "rejected"}, f"{label}.status")
        replaced_by = reference.get("replaced_by")
        if replaced_by is not None:
            _text(replaced_by, f"{label}.replaced_by")
        if status == "active" and replaced_by is not None:
            raise CatalogShapeError(f"{label} active reference cannot be replaced")
        freshness = _object(reference.get("freshness"), f"{label}.freshness")
        _exact(freshness, FRESHNESS_REQUIRED, FRESHNESS_FIELDS, f"{label}.freshness")
        _enum(
            freshness.get("mode"),
            {"hash_pinned", "revalidate_before_use", "time_bounded", "job_bound", "evaluation_only"},
            f"{label}.freshness.mode",
        )
        _date(freshness.get("reviewed_at"), f"{label}.freshness.reviewed_at")
        expires_at = freshness.get("expires_at")
        if expires_at is not None:
            _date(expires_at, f"{label}.freshness.expires_at")
        _texts(freshness.get("recheck_triggers"), f"{label}.freshness.recheck_triggers")
