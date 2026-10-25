"""Bounded read-only Codex hooks/list observation; never invokes a hook."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import tempfile
import time


def codex_executable() -> str:
    """Resolve installed launchers also under launchd's intentionally short PATH."""
    explicit = os.environ.get("AGENT_COMPANY_CODEX_PATH")
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError("AGENT_COMPANY_CODEX_PATH must name an executable absolute path")
        return str(path)
    if binary := shutil.which("codex"):
        return binary
    home = Path.home()
    for path in [home / ".local/bin/codex", Path("/opt/homebrew/bin/codex"), Path("/usr/local/bin/codex")]:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    # Do not guess a winner among different installed nvm versions.
    candidates = list((home / ".nvm/versions/node").glob("v*/bin/codex"))
    if len(candidates) <= 16:
        available = {path.resolve(): path for path in candidates if path.is_file() and os.access(path, os.X_OK)}
        if len(available) == 1:
            return str(next(iter(available.values())))
        if len(available) > 1:
            raise ValueError("multiple installed Codex launchers; set AGENT_COMPANY_CODEX_PATH")
    raise ValueError("Codex executable unavailable for hooks/list")


class HookProbeError(ValueError):
    """A failed observation with payload-free child/process evidence."""

    def __init__(self, message: str, diagnostics: dict):
        super().__init__(message)
        self.diagnostics = diagnostics


def _stderr_summary(errors) -> dict:
    """Keep only size, bounded digest and fixed signatures, never raw stderr."""
    size = os.fstat(errors.fileno()).st_size
    errors.seek(0)
    sample = errors.read(16384)
    lower = sample.lower()
    signatures = [label for label, text in (
        ("rust_panic", b"panicked at"),
        ("resource_unavailable", b"resource temporarily unavailable"),
        ("too_many_open_files", b"too many open files"),
        ("permission_denied", b"permission denied"),
        ("address_in_use", b"address already in use"),
        ("broken_pipe", b"broken pipe"),
        ("spawn_failure", b"failed to spawn"),
        ("configuration_error", b"error loading config"),
        ("error_marker", b"error:"),
    ) if text in lower]
    return {"size_bytes": size, "sample_bytes": len(sample),
        "sample_sha256": hashlib.sha256(sample).hexdigest(),
        "sample_truncated": size > len(sample), "signatures": signatures}


def list_hooks(home: Path, *, timeout: float = 15, diagnostics: dict | None = None) -> list[dict]:
    binary = codex_executable()
    env = dict(os.environ, CODEX_HOME=str(home))
    # npm's launcher uses /usr/bin/env node. Its sibling node must remain
    # available even when the updater's PATH omits the nvm installation.
    env["PATH"] = str(Path(binary).parent) + os.pathsep + env.get("PATH", "")
    evidence = diagnostics if diagnostics is not None else {}
    evidence.update({"executable": binary, "resolved_executable": str(Path(binary).resolve()),
        "codex_home": str(home), "user_home": env.get("HOME"), "cwd": os.getcwd(),
        "node_executable": shutil.which("node", path=env["PATH"]),
        "child_path_sha256": hashlib.sha256(env["PATH"].encode()).hexdigest(),
        "timeout_seconds": timeout, "stage": "spawn", "protocol": [],
        "stdout_bytes": 0, "cleanup": []})
    started = time.monotonic()
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([binary, "app-server", "--stdio"], env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
        assert process.stdin is not None and process.stdout is not None
        evidence["pid"] = process.pid
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        pending = b""
        def send(value: dict) -> None:
            process.stdin.write((json.dumps(value) + "\n").encode())
            process.stdin.flush()
            if len(evidence["protocol"]) < 32:
                evidence["protocol"].append({"direction": "sent", "id": value.get("id"),
                    "method": value["method"]})
        try:
            evidence["stage"] = "initialize"
            send({"id": 0, "method": "initialize", "params": {"clientInfo":
                {"name": "agent-company-doctor", "version": "1"},
                "capabilities": {"experimentalApi": True}}})
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if not selector.select(timeout=min(0.2, max(0, deadline - time.monotonic()))):
                    continue
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    raise ValueError("Codex app-server closed before hooks/list response")
                evidence["stdout_bytes"] += len(chunk)
                pending += chunk
                if len(pending) > 4 * 1024 * 1024:
                    raise ValueError("hooks/list response exceeded bounded limit")
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError("Codex app-server response must be a JSON object")
                    if len(evidence["protocol"]) < 32:
                        evidence["protocol"].append({"direction": "received",
                            "id": message.get("id") if type(message.get("id")) is int and message.get("id") in (0, 1) else "other",
                            "error": "error" in message, "result": "result" in message})
                    if "id" not in message and isinstance(message.get("method"), str):
                        continue
                    request_id = message.get("id")
                    if type(request_id) is not int or request_id not in (0, 1):
                        raise ValueError("Codex app-server response has an invalid request ID")
                    expected_id = 0 if evidence["stage"] == "initialize" else 1
                    if request_id != expected_id:
                        raise ValueError("Codex app-server response arrived in an invalid phase")
                    if "error" in message:
                        # Do not echo arbitrary provider/server error data or credentials.
                        raise ValueError("Codex rejected read-only hooks/list contract")
                    if "result" not in message:
                        raise ValueError("Codex app-server response has no result")
                    if request_id == 0:
                        evidence["stage"] = "initialized"
                        send({"method": "initialized"})
                        evidence["stage"] = "hooks/list"
                        send({"id": 1, "method": "hooks/list", "params": {"cwds": [str(home)]}})
                    else:
                        evidence["stage"] = "complete"
                        return flatten_hooks(message.get("result"))
            raise ValueError("hooks/list observation timed out")
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            evidence["failure_type"] = type(exc).__name__
            raise HookProbeError(str(exc), evidence) from exc
        finally:
            evidence["returncode_before_cleanup"] = process.poll()
            selector.close()
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
            try:
                process.wait(timeout=2)
                evidence["cleanup"].append("stdin_closed_exit")
            except subprocess.TimeoutExpired:
                evidence["cleanup"].append("terminate")
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    evidence["cleanup"].append("kill")
                    process.kill()
                    process.wait(timeout=2)
            process.stdout.close()
            evidence["returncode_after_cleanup"] = process.returncode
            evidence["elapsed_seconds"] = round(time.monotonic() - started, 6)
            evidence["stderr"] = _stderr_summary(errors)


def flatten_hooks(value: object) -> list[dict]:
    if isinstance(value, dict):
        if "eventName" in value and "enabled" in value:
            return [value]
        return [item for child in value.values() for item in flatten_hooks(child)]
    if isinstance(value, list):
        return [item for child in value for item in flatten_hooks(child)]
    return []
