#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run: uv run scripts/check_core_contract.py --lock agent-company.lock.json --json
# 3. Or: python3 scripts/check_core_contract.py --lock agent-company.lock.json --json
# ─────────────────

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, assert_never


JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]

CORE_SCRIPT: Final[str] = "docs/sejong/scripts/task_class_delegation_gate.py"
CORE_MODULES: Final[tuple[str, ...]] = (
    CORE_SCRIPT,
    "docs/sejong/scripts/delegation_route_contract.py",
    "docs/sejong/scripts/delegation_route_policy.py",
    "docs/sejong/scripts/delegation_route_scoring.py",
    "docs/sejong/scripts/team_executor_runtime.py",
)
NORMATIVE_FILES: Final[tuple[str, ...]] = (
    "docs/sejong/ROUTER.md",
    "docs/sejong/DELEGATION_RUNTIME.md",
    "docs/sejong/RUNTIME_CONTRACT.md",
    "docs/sejong/SEUNGJEONGWON_EXECUTOR.md",
    "docs/sejong/ARTIFACT_STORAGE.md",
    "docs/sejong/VALIDATION.md",
    "docs/sejong/workflow-run.schema.json",
    "docs/sejong/scripts/sejong_workflow_run.py",
)
ROUTE_CASES: Final[tuple[tuple[str, ...], ...]] = (
    ("--task-class", "simple_lookup"),
    ("--task-class", "validation_review", "--evidence-breadth", "moderate", "--overhead-roi", "medium"),
    ("--task-class", "implementation", "--write-risk", "medium", "--evidence-breadth", "broad", "--overhead-roi", "high", "--worker-scope-state", "disjoint", "--team-executor-health", "healthy"),
    ("--task-class", "research", "--evidence-breadth", "unknown", "--code-coupling", "cross_module", "--overhead-roi", "medium"),
    ("--task-class", "implementation", "--write-mode", "dry_run"),
)
TIMEOUT_SECONDS: Final[int] = 20
SUPPORTED_ROUTES: Final[frozenset[str]] = frozenset(
    {"direct_execution", "bounded_subagents", "team_executor", "research_fanout", "no_write_dry_run"}
)


@dataclass(frozen=True, slots=True)
class ContractBlocker(Exception):
    code: str
    detail: str
    field: str | None = None
    path: str | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class LockedCore:
    repo: Path
    commit: str
    locked_content_sha256: str


def as_object(value: JsonValue, field: str) -> JsonObject:
    match value:
        case dict():
            return value
        case str() | int() | float() | bool() | None | list():
            raise ContractBlocker("malformed_input", f"{field} must be an object", field=field)
        case unreachable:
            assert_never(unreachable)


def text_field(values: JsonObject, field: str) -> str:
    value = values.get(field)
    match value:
        case str() if value.strip():
            return value
        case str() | int() | float() | bool() | None | list() | dict():
            raise ContractBlocker("malformed_input", f"{field} must be a non-empty string", field=field)
        case unreachable:
            assert_never(unreachable)


def load_lock(path: Path) -> LockedCore:
    try:
        parsed: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractBlocker("missing_lock_file", "lock file does not exist", path=path.name) from exc
    except json.JSONDecodeError as exc:
        raise ContractBlocker("malformed_input", f"invalid lock JSON at line {exc.lineno}") from exc
    root = as_object(parsed, "$")
    dependencies = as_object(root.get("resolved_dependencies"), "resolved_dependencies")
    king = as_object(dependencies.get("king_sejong"), "resolved_dependencies.king_sejong")
    checkout = as_object(king.get("local_develop_checkout"), "local_develop_checkout")
    if checkout.get("reproducible") is not True or checkout.get("inspectable") is not True:
        raise ContractBlocker("non_reproducible_lock", "locked Core must be reproducible and inspectable")
    repo = Path(text_field(checkout, "git_root")).expanduser()
    commit = text_field(checkout, "commit")
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise ContractBlocker("malformed_input", "commit must be a lowercase 40-character SHA", field="commit")
    return LockedCore(repo, commit, text_field(checkout, "content_sha256"))


def git_bytes(core: LockedCore, args: list[str]) -> bytes:
    try:
        result = subprocess.run(
            ["git", *args], cwd=core.repo, capture_output=True, check=False, timeout=TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as exc:
        raise ContractBlocker("git_timeout", f"git exceeded {TIMEOUT_SECONDS} seconds") from exc
    except OSError as exc:
        raise ContractBlocker("git_unavailable", "could not execute git") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip() or "git object lookup failed"
        raise ContractBlocker("locked_object_unavailable", detail)
    return result.stdout


def require_normative_files(core: LockedCore) -> None:
    for relative in (*NORMATIVE_FILES, CORE_SCRIPT):
        try:
            _ = git_bytes(core, ["cat-file", "-e", f"{core.commit}:{relative}"])
        except ContractBlocker as exc:
            raise ContractBlocker(
                "missing_normative_file", "required normative file is absent from the locked commit", path=relative
            ) from exc


def pinned_tree_sha256(core: LockedCore) -> str:
    names = git_bytes(core, ["ls-tree", "-r", "--name-only", "-z", core.commit])
    digest = hashlib.sha256()
    for relative_bytes in sorted(item for item in names.split(b"\0") if item):
        relative = relative_bytes.decode("utf-8", errors="surrogateescape")
        content = git_bytes(core, ["show", f"{core.commit}:{relative}"])
        digest.update(relative_bytes)
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def parse_gate_output(raw: str) -> JsonObject:
    try:
        parsed: JsonValue = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContractBlocker("malformed_contract_output", f"gate emitted invalid JSON at line {exc.lineno}") from exc
    report = as_object(parsed, "gate_output")
    required = (
        "format",
        "selected_route",
        "hard_gates",
        "hard_gate_failures",
        "required_evidence",
        "forbidden_claims",
        "recommended_reentry_target",
    )
    for field in required:
        if field not in report:
            raise ContractBlocker("missing_contract_field", f"gate output omits {field}", field=field)
    if not isinstance(report["format"], str) or not report["format"]:
        raise ContractBlocker("malformed_contract_field", "format must be a non-empty string", field="format")
    if report["selected_route"] not in SUPPORTED_ROUTES:
        raise ContractBlocker("malformed_contract_field", "selected_route is unsupported", field="selected_route")
    hard_gates = report["hard_gates"]
    if not isinstance(hard_gates, dict) or not hard_gates or not all(
        isinstance(name, str) and isinstance(passed, bool) for name, passed in hard_gates.items()
    ):
        raise ContractBlocker("malformed_contract_field", "hard_gates must map names to booleans", field="hard_gates")
    for field in ("hard_gate_failures", "required_evidence", "forbidden_claims"):
        value = report[field]
        required_items = field != "hard_gate_failures"
        if not isinstance(value, list) or (required_items and not value) or not all(
            isinstance(item, str) and bool(item.strip()) for item in value
        ):
            raise ContractBlocker("malformed_contract_field", f"{field} must contain strings", field=field)
    if not isinstance(report["recommended_reentry_target"], str):
        raise ContractBlocker(
            "malformed_contract_field",
            "recommended_reentry_target must be a string",
            field="recommended_reentry_target",
        )
    return report


def evaluate_locked_gate(modules: tuple[tuple[str, bytes], ...]) -> list[JsonObject]:
    reports: list[JsonObject] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        for relative, content in modules:
            target = Path(temp_dir) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        runner = Path(temp_dir) / CORE_SCRIPT
        for arguments in ROUTE_CASES:
            try:
                result = subprocess.run(
                    [sys.executable, "-E", "-S", str(runner), *arguments],
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as exc:
                raise ContractBlocker("gate_timeout", "locked gate execution timed out") from exc
            if result.returncode != 0:
                raise ContractBlocker("gate_execution_failed", result.stderr.strip() or "locked gate rejected probe")
            reports.append(parse_gate_output(result.stdout))
    return reports


def check_contract(lock_path: Path) -> JsonObject:
    core = load_lock(lock_path)
    _ = git_bytes(core, ["cat-file", "-e", f"{core.commit}^{{commit}}"])
    resolved_content_sha256 = pinned_tree_sha256(core)
    if resolved_content_sha256 != core.locked_content_sha256:
        raise ContractBlocker("content_hash_mismatch", "locked content hash does not match the pinned commit")
    require_normative_files(core)
    locked_files = frozenset(
        git_bytes(core, ["ls-tree", "-r", "--name-only", "-z", core.commit])
        .decode("utf-8", errors="surrogateescape")
        .split("\0")
    )
    modules = tuple(
        (relative, git_bytes(core, ["show", f"{core.commit}:{relative}"]))
        for relative in CORE_MODULES
        if relative in locked_files
    )
    script = modules[0][1]
    reports = evaluate_locked_gate(modules)
    routes = sorted({str(report["selected_route"]) for report in reports})
    result: JsonObject = {
        "format": "agent-company.core-contract/v0.2",
        "status": "ok",
        "resolved_commit": core.commit,
        "locked_content_sha256": core.locked_content_sha256,
        "resolved_content_sha256": resolved_content_sha256,
        "core_script_sha256": hashlib.sha256(script).hexdigest(),
        "core_modules": [relative for relative, _ in modules],
        "supported_routes": routes,
        "normative_files": list(NORMATIVE_FILES),
    }
    if (provenance := reports[0].get("backend_provenance")) is not None:
        result["backend_provenance"] = provenance
    return result


def blocker_json(blocker: ContractBlocker) -> JsonObject:
    detail: JsonObject = {"code": blocker.code, "detail": blocker.detail}
    if blocker.field is not None:
        detail["field"] = blocker.field
    if blocker.path is not None:
        detail["path"] = blocker.path
    return {
        "format": "agent-company.core-contract-blocker/v0.2",
        "status": "blocked",
        "blocker": detail,
        "remediation": "Create a separate King Sejong plan; do not import ambient files or edit Core here.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--blocker", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = check_contract(args.lock)
    except ContractBlocker as blocker:
        report = blocker_json(blocker)
        if args.blocker is not None:
            args.blocker.parent.mkdir(parents=True, exist_ok=True)
            args.blocker.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True), file=sys.stdout if args.json else sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
