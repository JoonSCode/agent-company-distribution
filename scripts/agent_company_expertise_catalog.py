from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import hashlib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

from agent_company_expertise_eval_io import (
    parse_json_object,
    read_bytes,
    require_inside,
)
from agent_company_expertise_eval_models import ExpertiseEvaluationError
from agent_company_expertise_models import (
    ExpertiseCatalog,
    ExpertiseCatalogError,
)
from agent_company_expertise_parsing import (
    parse_references,
    parse_roles,
    validate_reference_graph,
)
from agent_company_expertise_validation import (
    CatalogShapeError,
    validate_manifest_document,
    validate_registry_document,
)
from agent_company_role_schema import JsonValue

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
REGISTRY_REF: Final[str] = "policies/expertise-registry.json"
MANIFEST_REF: Final[str] = "policies/reference-manifest.json"
ROLES: Final[frozenset[str]] = frozenset(
    {"founder", "planning", "marketing", "design", "development", "qa-release"}
)
MAX_CATALOG_BYTES: Final[int] = 2_000_000


def _secure_bytes(root: Path, reference: str) -> bytes:
    relative = Path(reference)
    if relative.is_absolute() or ".." in relative.parts:
        raise ExpertiseCatalogError("reference_escape", f"unsafe reference: {reference}")
    try:
        target = require_inside(root, root / relative)
        return read_bytes(target, MAX_CATALOG_BYTES)
    except ExpertiseEvaluationError as exc:
        raise ExpertiseCatalogError("reference_unavailable", f"cannot open reference: {reference}") from exc


def _json_object(content: bytes, label: str) -> dict[str, JsonValue]:
    try:
        return parse_json_object(content, label)
    except ExpertiseEvaluationError as exc:
        raise ExpertiseCatalogError("catalog_malformed", f"{label} is not valid JSON") from exc


def load_expertise_catalog(root: Path = ROOT, today: date | None = None) -> ExpertiseCatalog:
    registry_bytes = _secure_bytes(root, REGISTRY_REF)
    manifest_bytes = _secure_bytes(root, MANIFEST_REF)
    registry = _json_object(registry_bytes, REGISTRY_REF)
    manifest = _json_object(manifest_bytes, MANIFEST_REF)
    try:
        validate_registry_document(registry)
        validate_manifest_document(manifest)
    except CatalogShapeError as exc:
        raise ExpertiseCatalogError("catalog_malformed", str(exc)) from exc
    roles = parse_roles(registry)
    references = parse_references(
        root,
        manifest,
        today or datetime.now(UTC).date(),
        _secure_bytes,
    )
    validate_reference_graph(references)
    for role, expertise in roles.items():
        _ = _secure_bytes(root, f"skills/{expertise.role_os_skill}/SKILL.md")
        kernel = references.get(expertise.role_kernel_id)
        if kernel is None or kernel.owner_role != role or kernel.layer != "role_kernel" or kernel.status != "active":
            raise ExpertiseCatalogError("catalog_malformed", f"invalid role kernel for {role}")
    return ExpertiseCatalog(
        root=root.absolute(),
        registry_sha256=hashlib.sha256(registry_bytes).hexdigest(),
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        default_specialist_limit=2,
        roles=roles,
        references=references,
    )
