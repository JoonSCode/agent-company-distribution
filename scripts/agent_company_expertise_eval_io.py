from __future__ import annotations

# pyright: reportImplicitRelativeImport=false
import fcntl
import os
import secrets
import stat
from collections.abc import Generator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from pathlib import Path

import agent_company_expertise_eval_encoding as _encoding
from agent_company_expertise_eval_models import ExpertiseEvaluationError
from agent_company_role_schema import JsonValue

canonical = _encoding.canonical
digest_bytes = _encoding.digest_bytes
now = _encoding.now
parse_json_object = _encoding.parse_json_object
MAX_RUNTIME_BYTES = 8_000_000
_READ_SNAPSHOT: ContextVar[dict[Path, bytes] | None] = ContextVar(
    "agent_company_evaluation_read_snapshot",
    default=None,
)


def _absolute(path: Path) -> Path:
    selected = Path(os.path.abspath(os.fspath(path.expanduser())))
    if len(selected.parts) < 2:
        return selected
    top_level = Path(selected.anchor) / selected.parts[1]
    try:
        metadata = os.lstat(top_level)
    except OSError:
        return selected
    if not stat.S_ISLNK(metadata.st_mode) or metadata.st_uid != 0:
        return selected
    canonical_top_level = Path(os.path.realpath(os.fspath(top_level)))
    return canonical_top_level.joinpath(*selected.parts[2:])


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )


def open_parent_directory(path: Path, *, create: bool) -> tuple[int, str]:
    selected = _absolute(path)
    if selected == Path("/") or not selected.name:
        raise OSError("file path resolves to root")
    directory_fd = os.open("/", _directory_flags())
    opened = False
    try:
        for part in selected.parts[1:-1]:
            try:
                next_fd = os.open(
                    part,
                    _directory_flags(),
                    dir_fd=directory_fd,
                )
            except FileNotFoundError:
                if not create:
                    raise
                with suppress(FileExistsError):
                    os.mkdir(part, 0o700, dir_fd=directory_fd)
                next_fd = os.open(
                    part,
                    _directory_flags(),
                    dir_fd=directory_fd,
                )
            os.close(directory_fd)
            directory_fd = next_fd
        opened = True
        return directory_fd, selected.name
    finally:
        if not opened:
            os.close(directory_fd)


def _opened_regular_file(path: Path) -> int:
    directory_fd, name = open_parent_directory(path, create=False)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        return os.open(name, flags, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)


def _fingerprint(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def read_bytes_limited(path: Path, maximum: int) -> bytes:
    descriptor = -1
    try:
        descriptor = _opened_regular_file(path)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("not a regular file")
        chunks: list[bytes] = []
        size = 0
        while size <= maximum:
            chunk = os.read(descriptor, min(65_536, maximum + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise ExpertiseEvaluationError("evaluation_runtime_unsafe", str(path)) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    content = b"".join(chunks)
    if len(content) > maximum:
        raise ExpertiseEvaluationError("evaluation_runtime_oversized", str(path))
    if _fingerprint(before) != _fingerprint(after):
        raise ExpertiseEvaluationError("evaluation_runtime_unsafe", str(path))
    return content


def read_bytes(
    path: Path,
    maximum: int = MAX_RUNTIME_BYTES,
) -> bytes:
    selected = _absolute(path)
    snapshot = _READ_SNAPSHOT.get()
    if snapshot is None:
        return read_bytes_limited(selected, maximum)
    cached = snapshot.get(selected)
    if cached is not None:
        if len(cached) > maximum:
            raise ExpertiseEvaluationError(
                "evaluation_runtime_oversized",
                str(path),
            )
        return cached
    content = read_bytes_limited(selected, maximum)
    snapshot[selected] = content
    return content


@contextmanager
def pinned_read_snapshot() -> Generator[None]:
    """Reuse the first descriptor-verified bytes for every path in one audit."""
    if _READ_SNAPSHOT.get() is not None:
        yield
        return
    token = _READ_SNAPSHOT.set({})
    try:
        yield
    finally:
        _READ_SNAPSHOT.reset(token)


def read_json(path: Path) -> dict[str, JsonValue]:
    return parse_json_object(read_bytes(path), str(path))


def active_run_id(run_root: Path) -> str:
    payload = read_json(run_root / "seungjeongwon-run.json")
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or payload.get("status") != "active":
        raise ExpertiseEvaluationError("evaluation_run_invalid", str(run_root))
    return run_id


def write_bytes(path: Path, content: bytes) -> None:
    temporary = f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp"
    directory_fd = -1
    descriptor = -1
    try:
        directory_fd, name = open_parent_directory(path, create=True)
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            _ = stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(
            temporary,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
    except OSError as exc:
        raise ExpertiseEvaluationError("evaluation_runtime_unsafe", str(path)) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if directory_fd >= 0:
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=directory_fd)
            os.close(directory_fd)


def write_json(path: Path, value: dict[str, JsonValue]) -> None:
    write_bytes(path, canonical(value) + b"\n")


def require_inside(root: Path, path: Path) -> Path:
    selected_root = _absolute(root)
    selected = _absolute(path)
    if not selected.is_relative_to(selected_root):
        raise ExpertiseEvaluationError("evaluation_runtime_escape", str(path))
    directory_fd = -1
    try:
        directory_fd, _ = open_parent_directory(selected, create=False)
    except OSError as exc:
        raise ExpertiseEvaluationError("evaluation_runtime_unsafe", str(path)) from exc
    finally:
        if directory_fd >= 0:
            os.close(directory_fd)
    return selected


def secure_regular_file_exists(path: Path) -> bool:
    directory_fd = -1
    try:
        directory_fd, name = open_parent_directory(path, create=False)
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ExpertiseEvaluationError("evaluation_runtime_unsafe", str(path)) from exc
    finally:
        if directory_fd >= 0:
            os.close(directory_fd)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ExpertiseEvaluationError("evaluation_runtime_unsafe", str(path))
    return True


@contextmanager
def secure_exclusive_file_lock(
    target: Path,
    *,
    create_parent: bool = True,
) -> Generator[None]:
    directory_fd = -1
    try:
        directory_fd, _ = open_parent_directory(target, create=create_parent)
        metadata = os.fstat(directory_fd)
        if not stat.S_ISDIR(metadata.st_mode):
            raise OSError("unsafe lock directory")
        fcntl.flock(directory_fd, fcntl.LOCK_EX)
    except OSError as exc:
        if directory_fd >= 0:
            os.close(directory_fd)
        raise ExpertiseEvaluationError("evaluation_lock_failed", str(target)) from exc
    try:
        yield
    finally:
        if directory_fd >= 0:
            try:
                fcntl.flock(directory_fd, fcntl.LOCK_UN)
            finally:
                os.close(directory_fd)
