#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["jsonschema>=4.25,<5"]
# ///

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable, Final

from jsonschema import Draft202012Validator, ValidationError

from agent_company_cycle_models import CycleError, JsonObject, Mutation
from agent_company_job_definition import read_object
from agent_company_projection_policy import PolicyError


ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SCHEMA_PATH: Final[Path] = ROOT / "policies" / "company-state.schema.json"


def _json_bytes(value: JsonObject) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def validate_state(value: JsonObject) -> None:
    try:
        schema = read_object(SCHEMA_PATH)
        Draft202012Validator(schema).validate(value)
    except (PolicyError, ValidationError) as exc:
        raise CycleError("malformed_state", f"company state failed schema validation: {exc}") from exc
    binding = value.get("charter_binding")
    if not isinstance(binding, dict):
        raise CycleError("malformed_state", "company state charter binding is missing")
    charter_path = ROOT / "policies" / "company-charter.json"
    try:
        charter_sha256 = hashlib.sha256(charter_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise CycleError("charter_unavailable", f"cannot read company charter: {exc}") from exc
    if binding.get("sha256") != charter_sha256:
        raise CycleError("stale_charter", "company state is bound to different charter bytes")


def _read(path: Path) -> JsonObject:
    if path.is_symlink():
        raise CycleError("unsafe_state_path", "company state must not be a symlink")
    try:
        value = read_object(path)
    except PolicyError as exc:
        raise CycleError("malformed_state", f"cannot read company state {path}: {exc}") from exc
    validate_state(value)
    return value


def _write_replace(path: Path, value: JsonObject) -> None:
    temporary: Path | None = None
    try:
        _ = path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            "wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            _ = stream.write(_json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        _ = temporary.replace(path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise CycleError("state_write_failed", f"cannot write company state {path}: {exc}") from exc


@contextmanager
def _locked(path: Path) -> Generator[None, None, None]:
    _ = path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(lock_path, flags, 0o600)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
        ):
            raise CycleError("unsafe_state_path", "company state lock has unsafe identity")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except OSError as exc:
        raise CycleError("state_lock_failed", f"cannot lock company state: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def initialize_state(path: Path, value: JsonObject) -> JsonObject:
    validate_state(value)
    with _locked(path):
        if path.exists() or path.is_symlink():
            raise CycleError("state_exists", f"company state already exists: {path}")
        _write_replace(path, value)
    return {"status": "initialized", "path": str(path.resolve()), "revision": 0, "fencing_token": 0}


def read_state(path: Path) -> JsonObject:
    return _read(path)


def mutate_state(
    path: Path,
    expected_revision: int,
    expected_fencing_token: int,
    transform: Callable[[JsonObject], Mutation],
) -> JsonObject:
    with _locked(path):
        current = _read(path)
        if (
            current.get("revision") != expected_revision
            or current.get("fencing_token") != expected_fencing_token
        ):
            raise CycleError("stale_state", "revision or fencing token does not match")
        mutation = transform(current)
        result = dict(mutation.result)
        if mutation.state is None:
            result.update({"revision": expected_revision, "fencing_token": expected_fencing_token})
            return result
        next_state = mutation.state
        next_state["revision"] = expected_revision + 1
        next_state["fencing_token"] = expected_fencing_token + 1
        validate_state(next_state)
        _write_replace(path, next_state)
        result.update({"revision": expected_revision + 1, "fencing_token": expected_fencing_token + 1})
        return result


def write_immutable(path: Path, value: JsonObject) -> str:
    payload = _json_bytes(value)
    _ = path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_file() and not path.is_symlink() and path.read_bytes() == payload:
            return str(path.resolve())
        raise CycleError("immutable_conflict", f"immutable artifact differs: {path}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            _ = stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise CycleError("artifact_write_failed", f"cannot write immutable artifact {path}: {exc}") from exc
    return str(path.resolve())
