from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Final

from agent_company_expertise_models import (
    ExpertiseCatalogError,
    ReferenceFreshness,
    ReferenceSpec,
    RoleExpertise,
    SpecialistSpec,
)
from agent_company_role_schema import JsonValue

ROLES: Final[frozenset[str]] = frozenset(
    {"founder", "planning", "marketing", "design", "development", "qa-release"}
)
SHA256: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
BytesReader = Callable[[Path, str], bytes]


def _text(values: dict[str, JsonValue], field: str) -> str:
    value = values.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ExpertiseCatalogError("catalog_malformed", f"{field} must be non-empty text")
    return value


def _object(value: JsonValue | None, field: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ExpertiseCatalogError("catalog_malformed", f"{field} must be an object")
    return value


def _objects(value: JsonValue | None, field: str) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list):
        raise ExpertiseCatalogError("catalog_malformed", f"{field} must be a list")
    return tuple(_object(item, f"{field}[{index}]") for index, item in enumerate(value))


def _texts(value: JsonValue | None, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ExpertiseCatalogError("catalog_malformed", f"{field} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ExpertiseCatalogError(
                "catalog_malformed",
                f"{field} must contain non-empty text",
            )
        result.append(item)
    if len(set(result)) != len(result):
        raise ExpertiseCatalogError("catalog_malformed", f"{field} must be unique")
    return tuple(result)


def _nullable_text(value: JsonValue | None, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ExpertiseCatalogError("catalog_malformed", f"{field} must be text or null")
    return value


def parse_roles(registry: dict[str, JsonValue]) -> Mapping[str, RoleExpertise]:
    if registry.get("format") != "agent-company.expertise-registry/v0.1":
        raise ExpertiseCatalogError("catalog_malformed", "unsupported expertise registry format")
    if registry.get("default_specialist_limit") != 2:
        raise ExpertiseCatalogError("catalog_malformed", "default specialist limit must be two")
    roles: dict[str, RoleExpertise] = {}
    for index, raw in enumerate(_objects(registry.get("roles"), "roles")):
        role = _text(raw, "role_id")
        if role not in ROLES or role in roles:
            raise ExpertiseCatalogError("catalog_malformed", f"invalid or duplicate role: {role}")
        specialists = _objects(raw.get("optional_specialists"), f"roles[{index}].optional_specialists")
        parsed = tuple(
            SpecialistSpec(
                skill_id=_text(item, "skill_id"),
                selection_status=_text(item, "selection_status"),
                task_types=_texts(item.get("task_types"), "task_types"),
                decision_questions=_texts(item.get("decision_questions"), "decision_questions"),
                distinct_evidence=_text(item, "distinct_evidence"),
                allowed_use=_text(item, "allowed_use"),
                loading_cost=_text(item, "loading_cost"),
                stop_condition=_text(item, "stop_condition"),
            )
            for item in specialists
        )
        if len({item.skill_id for item in parsed}) != len(parsed):
            raise ExpertiseCatalogError("catalog_malformed", f"duplicate specialist for {role}")
        roles[role] = RoleExpertise(
            role_id=role,
            role_os_skill=_text(raw, "role_os_skill"),
            role_kernel_id=_text(raw, "role_kernel_id"),
            default_task_type=_text(raw, "default_task_type"),
            default_verifier=_text(raw, "default_verifier"),
            optional_specialists=parsed,
        )
    if set(roles) != ROLES:
        raise ExpertiseCatalogError("catalog_malformed", "registry must contain the exact six roles")
    return MappingProxyType(roles)


def parse_references(
    root: Path,
    manifest: dict[str, JsonValue],
    today: date,
    read_bytes: BytesReader,
) -> Mapping[str, ReferenceSpec]:
    if manifest.get("format") != "agent-company.reference-manifest/v0.1":
        raise ExpertiseCatalogError("catalog_malformed", "unsupported reference manifest format")
    references: dict[str, ReferenceSpec] = {}
    for index, raw in enumerate(_objects(manifest.get("references"), "references")):
        label = f"references[{index}]"
        reference_id = _text(raw, "id")
        if reference_id in references:
            raise ExpertiseCatalogError("catalog_malformed", f"duplicate reference id: {reference_id}")
        digest = _text(raw, "sha256")
        if SHA256.fullmatch(digest) is None:
            raise ExpertiseCatalogError("catalog_malformed", f"invalid digest for {reference_id}")
        freshness_raw = _object(raw.get("freshness"), f"{label}.freshness")
        expires_at = freshness_raw.get("expires_at")
        try:
            expired = isinstance(expires_at, str) and date.fromisoformat(expires_at) < today
        except ValueError as exc:
            raise ExpertiseCatalogError("catalog_malformed", f"invalid expiry for {reference_id}") from exc
        if expired:
            raise ExpertiseCatalogError("reference_stale", f"reference expired: {reference_id}")
        reference = ReferenceSpec(
            id=reference_id,
            version=_text(raw, "version"),
            layer=_text(raw, "layer"),
            owner_role=_text(raw, "owner_role"),
            ref=_text(raw, "ref"),
            source_url=_nullable_text(raw.get("source_url"), "source_url"),
            sha256=digest,
            applies_to_tasks=_texts(raw.get("applies_to_tasks"), f"{label}.applies_to_tasks"),
            decision_questions=_texts(raw.get("decision_questions"), f"{label}.decision_questions"),
            authority_class=_text(raw, "authority_class"),
            allowed_uses=_texts(raw.get("allowed_uses"), f"{label}.allowed_uses"),
            freshness=ReferenceFreshness(
                mode=_text(freshness_raw, "mode"),
                reviewed_at=_text(freshness_raw, "reviewed_at"),
                expires_at=_nullable_text(expires_at, "expires_at"),
                recheck_triggers=_texts(
                    freshness_raw.get("recheck_triggers"),
                    f"{label}.freshness.recheck_triggers",
                ),
            ),
            loading_cost=_text(raw, "loading_cost"),
            dependencies=_texts(raw.get("dependencies"), f"{label}.dependencies"),
            conflicts=_texts(raw.get("conflicts"), f"{label}.conflicts"),
            evaluation_refs=_texts(raw.get("evaluation_refs"), f"{label}.evaluation_refs"),
            status=_text(raw, "status"),
            replaced_by=_nullable_text(raw.get("replaced_by"), "replaced_by"),
        )
        if reference.status == "active":
            actual = hashlib.sha256(read_bytes(root, reference.ref)).hexdigest()
            if actual != digest:
                raise ExpertiseCatalogError(
                    "reference_hash_mismatch",
                    f"{reference_id} bytes disagree with manifest",
                )
        references[reference_id] = reference
    return MappingProxyType(references)


def validate_reference_graph(references: Mapping[str, ReferenceSpec]) -> None:
    for reference in references.values():
        linked = (*reference.dependencies, *reference.conflicts, *reference.evaluation_refs)
        missing = sorted(item for item in linked if item not in references)
        if missing:
            raise ExpertiseCatalogError(
                "catalog_malformed",
                f"{reference.id} links missing references: {missing}",
            )
        if set(reference.dependencies) & set(reference.conflicts):
            raise ExpertiseCatalogError(
                "catalog_malformed",
                f"{reference.id} both depends on and conflicts with one reference",
            )
        if reference.replaced_by is not None and reference.replaced_by not in references:
            raise ExpertiseCatalogError("catalog_malformed", f"{reference.id} replacement is missing")
        if any(references[item].layer != "evaluation_set" for item in reference.evaluation_refs):
            raise ExpertiseCatalogError(
                "catalog_malformed",
                f"{reference.id} evaluation_refs must target evaluation sets",
            )
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(reference_id: str) -> None:
        if reference_id in visiting:
            raise ExpertiseCatalogError("catalog_malformed", "reference dependency cycle")
        if reference_id in visited:
            return
        visiting.add(reference_id)
        for dependency in references[reference_id].dependencies:
            visit(dependency)
        visiting.remove(reference_id)
        visited.add(reference_id)

    for reference_id in references:
        visit(reference_id)
