from __future__ import annotations

# pyright: reportImplicitRelativeImport=false, reportUnnecessaryComparison=false
import hashlib
from pathlib import Path
from types import MappingProxyType
from typing import Final

from agent_company_expertise_catalog import load_expertise_catalog
from agent_company_expertise_eval_io import (
    parse_json_object,
    read_bytes,
    require_inside,
)
from agent_company_expertise_eval_models import ExpertiseEvaluationError
from agent_company_expertise_models import ExpertiseCatalog
from agent_company_expertise_routing_models import (
    RoleRouting,
    RoutingPolicy,
    RoutingPolicyError,
    SpecialistRule,
    TaskRule,
)
from agent_company_role_schema import JsonValue

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
POLICY_REF: Final[str] = "policies/expertise-routing.json"
FORMAT: Final[str] = "agent-company.expertise-routing/v0.1"
ROLES: Final[frozenset[str]] = frozenset(
    {"founder", "planning", "marketing", "design", "development", "qa-release"}
)
MAX_BYTES: Final[int] = 256_000


def _object(value: JsonValue | None, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise RoutingPolicyError("routing_policy_malformed", f"{label} must be an object")
    return value


def _objects(value: JsonValue | None, label: str) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list):
        raise RoutingPolicyError("routing_policy_malformed", f"{label} must be a list")
    return tuple(_object(item, f"{label}[{index}]") for index, item in enumerate(value))


def _text(value: JsonValue | None, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoutingPolicyError("routing_policy_malformed", f"{label} must be text")
    return value


def _texts(value: JsonValue | None, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RoutingPolicyError("routing_policy_malformed", f"{label} must be a list")
    result = tuple(_text(item, label).casefold() for item in value)
    if not result or len(result) != len(set(result)):
        raise RoutingPolicyError("routing_policy_malformed", f"{label} must be nonempty and unique")
    return result


def _read_policy(root: Path) -> tuple[dict[str, JsonValue], bytes, Path]:
    try:
        path = require_inside(root, root / POLICY_REF)
        content = read_bytes(path, MAX_BYTES)
    except ExpertiseEvaluationError as exc:
        raise RoutingPolicyError(
            "routing_policy_unsafe",
            "routing policy must be a stable regular repository file",
        ) from exc
    try:
        parsed = parse_json_object(content, str(path))
    except ExpertiseEvaluationError as exc:
        raise RoutingPolicyError("routing_policy_malformed", "routing policy is not JSON") from exc
    return parsed, content, path


def _task_rule(raw: dict[str, JsonValue]) -> TaskRule:
    fields = {"task_type", "reference_id", "triggers"}
    if set(raw) != fields:
        raise RoutingPolicyError("routing_policy_malformed", "task rule shape is invalid")
    return TaskRule(
        _text(raw.get("task_type"), "task_type"),
        _text(raw.get("reference_id"), "reference_id"),
        _texts(raw.get("triggers"), "task triggers"),
    )


def _specialist_rule(raw: dict[str, JsonValue]) -> SpecialistRule:
    if set(raw) != {"skill_id", "triggers"}:
        raise RoutingPolicyError("routing_policy_malformed", "specialist rule shape is invalid")
    return SpecialistRule(
        _text(raw.get("skill_id"), "skill_id"),
        _texts(raw.get("triggers"), "specialist triggers"),
    )


def _validate_role(role: RoleRouting, catalog: ExpertiseCatalog) -> None:
    expertise = catalog.roles.get(role.role_id)
    if expertise is None or expertise.default_task_type != role.default_task_type:
        raise RoutingPolicyError("routing_policy_mismatch", f"role default differs for {role.role_id}")
    if len(role.task_rules) != 3 or len({item.task_type for item in role.task_rules}) != 3:
        raise RoutingPolicyError("routing_policy_malformed", f"{role.role_id} needs three tasks")
    if role.default_task_type not in {item.task_type for item in role.task_rules}:
        raise RoutingPolicyError("routing_policy_mismatch", f"default task is unroutable for {role.role_id}")
    for rule in role.task_rules:
        reference = catalog.references.get(rule.reference_id)
        if (
            reference is None
            or reference.layer != "task_pack"
            or reference.owner_role != role.role_id
            or rule.task_type not in reference.applies_to_tasks
            or reference.status != "active"
        ):
            raise RoutingPolicyError("routing_policy_mismatch", f"invalid task pack {rule.reference_id}")
    expected = set(expertise.automatic_specialist_ids)
    actual = {item.skill_id for item in role.specialist_rules}
    if expected != actual or len(actual) != len(role.specialist_rules):
        raise RoutingPolicyError("routing_policy_mismatch", f"specialist rules differ for {role.role_id}")


def load_routing_policy(
    root: Path = ROOT,
    catalog: ExpertiseCatalog | None = None,
) -> RoutingPolicy:
    payload, content, path = _read_policy(root)
    selected = catalog or load_expertise_catalog(root)
    if set(payload) != {"format", "roles"} or payload.get("format") != FORMAT:
        raise RoutingPolicyError("routing_policy_malformed", "routing policy header is unsupported")
    roles: dict[str, RoleRouting] = {}
    for raw in _objects(payload.get("roles"), "roles"):
        if set(raw) != {"role_id", "default_task_type", "task_rules", "specialist_rules"}:
            raise RoutingPolicyError("routing_policy_malformed", "role routing shape is invalid")
        role_id = _text(raw.get("role_id"), "role_id")
        role = RoleRouting(
            role_id,
            _text(raw.get("default_task_type"), "default_task_type"),
            tuple(_task_rule(item) for item in _objects(raw.get("task_rules"), "task_rules")),
            tuple(
                _specialist_rule(item)
                for item in _objects(raw.get("specialist_rules"), "specialist_rules")
            ),
        )
        if role_id not in ROLES or role_id in roles:
            raise RoutingPolicyError("routing_policy_malformed", f"invalid role {role_id}")
        _validate_role(role, selected)
        roles[role_id] = role
    if set(roles) != ROLES:
        raise RoutingPolicyError("routing_policy_malformed", "routing policy must contain six roles")
    return RoutingPolicy(
        path,
        hashlib.sha256(content).hexdigest(),
        MappingProxyType(roles),
    )
