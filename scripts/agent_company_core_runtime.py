from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final

from agent_company_deps import JsonValue
from agent_company_job_policy import PolicyError
from check_core_contract import ContractBlocker, check_contract, git_bytes, load_lock

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DEFAULT_LOCK: Final[Path] = ROOT / "agent-company.lock.json"
CORE_SCRIPTS: Final[tuple[str, ...]] = (
    "delegation_run.py",
    "delegation_run_model.py",
    "delegation_wave.py",
    "delegation_wave_validation.py",
    "seungjeongwon_run.py",
    "sejong_paths.py",
    "external_action_contract.py",
    "external_action_storage.py",
    "external_action_receipt.py",
    "sejong_runtime_lock.py",
)
OPTIONAL_CORE_SCRIPTS: Final[tuple[str, ...]] = (
    "delegation_cleanup.py",
    "delegation_receipt_validation.py",
)
TIMEOUT_SECONDS: Final[int] = 30


@dataclass(frozen=True, slots=True)
class ReportRuntimeBindings:
    job: dict[str, JsonValue]
    job_ref: str
    core_run: dict[str, JsonValue]
    core_run_ref: str
    delegation_input_ref: str | None = None
    verification_run: dict[str, JsonValue] | None = None
    verification_run_ref: str | None = None
    external_action_ledger: dict[str, JsonValue] | None = None
    external_action_ledger_ref: str | None = None
    core_lock_ref: str | None = None

    @property
    def job_ref_path(self) -> Path:
        return Path(self.job_ref).expanduser().resolve()

    @property
    def core_run_ref_path(self) -> Path:
        return Path(self.core_run_ref).expanduser().resolve()


@dataclass(frozen=True, slots=True)
class ValidatedRuntime:
    external_action_ledger_sha256: str | None


def _read_object(path: Path, label: str) -> tuple[dict[str, JsonValue], str]:
    try:
        raw = path.read_bytes()
        value: JsonValue = json.loads(raw)
    except FileNotFoundError as exc:
        raise PolicyError(f"{label} ref does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PolicyError(f"{label} ref is invalid JSON at line {exc.lineno}") from exc
    except OSError as exc:
        raise PolicyError(f"cannot read {label} ref {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PolicyError(f"{label} ref must contain a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _local_ref(ref: str, label: str) -> Path:
    if "://" in ref:
        raise PolicyError(f"{label} must be a local artifact path")
    return Path(ref).expanduser().resolve()


def _require_exact_ref(
    ref: str, expected: dict[str, JsonValue], label: str,
) -> tuple[Path, str]:
    path = _local_ref(ref, label)
    value, sha256 = _read_object(path, label)
    if value != expected:
        raise PolicyError(f"{label} ref bytes do not match the supplied object")
    return path, sha256


def _require_unchanged(
    path: Path, expected: dict[str, JsonValue], sha256: str, label: str,
) -> None:
    value, current_sha256 = _read_object(path, label)
    if value != expected or current_sha256 != sha256:
        raise PolicyError(f"{label} changed during pinned Core validation")


def _run_core(script: Path, arguments: tuple[str, ...], label: str) -> None:
    try:
        result = subprocess.run(
            [sys.executable, "-E", "-S", str(script), *arguments],
            text=True,
            capture_output=True,
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise PolicyError(f"pinned Core {label} validation timed out") from exc
    except OSError as exc:
        raise PolicyError(f"pinned Core {label} validator could not start") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "validation failed"
        raise PolicyError(f"pinned Core rejected {label}: {detail}")


@lru_cache(maxsize=4)
def _pinned_scripts(lock_bytes: bytes) -> tuple[tuple[str, bytes], ...]:
    with tempfile.TemporaryDirectory(prefix="agent-company-core-lock-") as tmp:
        lock_path = Path(tmp) / "agent-company.lock.json"
        lock_path.write_bytes(lock_bytes)
        try:
            check_contract(lock_path)
            core = load_lock(lock_path)
            tree = frozenset(
                git_bytes(
                    core,
                    ["ls-tree", "-r", "--name-only", "-z", core.commit],
                ).split(b"\0")
            )
            scripts = (
                *CORE_SCRIPTS,
                *(
                    filename
                    for filename in OPTIONAL_CORE_SCRIPTS
                    if f"docs/sejong/scripts/{filename}".encode() in tree
                ),
            )
            return tuple(
                (
                    filename,
                    git_bytes(core, ["show", f"{core.commit}:docs/sejong/scripts/{filename}"]),
                )
                for filename in scripts
            )
        except ContractBlocker as exc:
            raise PolicyError(f"pinned Core contract is invalid: {exc}") from exc


def _materialize_core(lock_path: Path, destination: Path) -> str:
    try:
        lock_bytes = lock_path.read_bytes()
    except OSError as exc:
        raise PolicyError(f"cannot read pinned Core lock: {lock_path}") from exc
    modules = _pinned_scripts(lock_bytes)
    for filename, content in modules:
        (destination / filename).write_bytes(content)
    return hashlib.sha256(lock_bytes).hexdigest()


def _require_lock_unchanged(lock_path: Path, expected_sha256: str) -> None:
    try:
        current_sha256 = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise PolicyError(f"cannot re-read pinned Core lock: {lock_path}") from exc
    if current_sha256 != expected_sha256:
        raise PolicyError("pinned Core lock changed during validation")


def validate_report_runtime(bindings: ReportRuntimeBindings) -> ValidatedRuntime:
    job = bindings.job
    job_ref = bindings.job_ref
    core_run = bindings.core_run
    core_run_ref = bindings.core_run_ref
    verification_run = bindings.verification_run
    verification_run_ref = bindings.verification_run_ref
    external_action_ledger = bindings.external_action_ledger
    external_action_ledger_ref = bindings.external_action_ledger_ref
    core_lock_ref = bindings.core_lock_ref
    job_path, job_sha256 = _require_exact_ref(job_ref, job, "job")
    core_path, core_sha256 = _require_exact_ref(core_run_ref, core_run, "Core run")
    verification_path: Path | None = None
    verification_sha256: str | None = None
    if verification_run is not None:
        if verification_run_ref is None:
            raise PolicyError("verification_run_ref is required with verification_run")
        verification_path, verification_sha256 = _require_exact_ref(
            verification_run_ref, verification_run, "verification run",
        )
    elif verification_run_ref is not None:
        raise PolicyError("verification_run_ref requires verification_run")
    ledger_path: Path | None = None
    ledger_sha256: str | None = None
    if external_action_ledger is not None:
        if external_action_ledger_ref is None:
            raise PolicyError("external_action_ledger_ref is required with a ledger")
        ledger_path, ledger_sha256 = _require_exact_ref(
            external_action_ledger_ref, external_action_ledger, "external-action ledger",
        )
    elif external_action_ledger_ref is not None:
        raise PolicyError("external_action_ledger_ref requires an external-action ledger")
    lock_path = Path(core_lock_ref).expanduser().resolve() if core_lock_ref else DEFAULT_LOCK
    with tempfile.TemporaryDirectory(prefix="agent-company-pinned-core-") as tmp:
        scripts = Path(tmp)
        lock_sha256 = _materialize_core(lock_path, scripts)
        _run_core(scripts / "delegation_run.py", ("check", str(core_path)), "Core run")
        if verification_path is not None:
            _run_core(
                scripts / "seungjeongwon_run.py",
                ("check", "--path", str(verification_path)),
                "verification run",
            )
        if ledger_path is not None:
            _run_core(
                scripts / "external_action_receipt.py",
                ("check", str(ledger_path)),
                "external-action ledger",
            )
    _require_lock_unchanged(lock_path, lock_sha256)
    _require_unchanged(job_path, job, job_sha256, "job")
    _require_unchanged(core_path, core_run, core_sha256, "Core run")
    if (
        verification_run is not None
        and verification_path is not None
        and verification_sha256 is not None
    ):
        _require_unchanged(
            verification_path, verification_run, verification_sha256, "verification run",
        )
    if (
        external_action_ledger is not None
        and ledger_path is not None
        and ledger_sha256 is not None
    ):
        _require_unchanged(
            ledger_path, external_action_ledger, ledger_sha256, "external-action ledger",
        )
    return ValidatedRuntime(external_action_ledger_sha256=ledger_sha256)


def validate_external_action_ledger(
    ledger: dict[str, JsonValue], core_lock_ref: str | None = None,
) -> None:
    lock_path = Path(core_lock_ref).expanduser().resolve() if core_lock_ref else DEFAULT_LOCK
    with tempfile.TemporaryDirectory(prefix="agent-company-pinned-action-") as tmp:
        root = Path(tmp)
        lock_sha256 = _materialize_core(lock_path, root)
        ledger_path = root / "external-action-ledger.json"
        ledger_path.write_text(
            json.dumps(ledger, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _run_core(
            root / "external_action_receipt.py",
            ("check", str(ledger_path)),
            "external-action ledger",
        )
    _require_lock_unchanged(lock_path, lock_sha256)


__all__ = [
    "DEFAULT_LOCK",
    "ReportRuntimeBindings",
    "ValidatedRuntime",
    "validate_external_action_ledger",
    "validate_report_runtime",
]
