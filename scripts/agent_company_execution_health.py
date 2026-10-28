"""Shared installation-to-execution checks for Doctor and sync-status.

Reads configuration and hook state, probes only the registered Python and
Codex's read-only hooks/list. Never runs Stop, cleanup or a Core dispatcher.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import tomllib

from agent_company_completion_hook_install import (
    HOOKS, PREFIX, REGISTRY, SCRIPT, _decode, _owned, _read, _registry_entry, verify_hook,
)
from agent_company_hook_probe import list_hooks
import agent_company_routing_hook_install as routing_hook
from agent_company_install_io import install_paths, read_json
from agent_company_install_types import InstallError
from agent_company_runtime_values import issue


def installation_home(requested: Path) -> Path:
    """Resolve a shared-skill or standard Orca home to its installation, read-only."""
    requested = requested.expanduser().absolute()
    if (requested / "agent-company/active.json").is_file():
        return requested
    package = requested / "skills/company-orchestration"
    if package.is_dir():
        resolved = package.resolve()
        candidate = resolved.parent.parent
        if resolved.parent.name == "skills" and (candidate / "agent-company/active.json").is_file():
            return candidate
    canonical = Path.home() / ".codex"
    orca = Path.home() / "Library/Application Support/orca/codex-runtime-home/home"
    if (requested == orca and not package.exists() and
            (canonical / "agent-company/active.json").is_file()):
        # Orca need not mirror skills: the registered command explicitly names
        # the canonical installed callback. Never infer this for arbitrary homes.
        return canonical
    return requested


def execution_homes(home: Path, extra: list[Path] | None = None) -> list[Path]:
    homes = [home, *(extra or [])]
    if home == Path.home() / ".codex":
        orca = Path.home() / "Library/Application Support/orca/codex-runtime-home/home"
        if orca.is_dir():
            homes.append(orca)
    return list(dict.fromkeys(path.expanduser().absolute() for path in homes))


def probe_python(entry: dict, home: Path, *, resolve_home: bool = True, prefix: str = PREFIX) -> dict:
    args = shlex.split(entry["hooks"][0]["command"][len(prefix):])
    python = Path(args[0])
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError(f"registered Python is missing or not executable: {python}")
    # Import only the owned, hash-verified lifecycle helper, never the Stop entry.
    helper = Path(args[2]).with_name("run_completion.py")
    code = "import json,sys; result={'version':list(sys.version_info[:3])}; "
    if resolve_home and helper.is_file():
        code += ("sys.path.insert(0," + repr(str(helper.parent)) + "); "
                 "import run_completion; result['sejong_home']=str(run_completion.default_home()); ")
    code += "print(json.dumps(result))"
    cache_prefix = str(Path.home() / ".cache/agent-company/python")
    # -I ignores PYTHONPYCACHEPREFIX, so use Python's equivalent -X switch.
    result = subprocess.run([str(python), "-I", "-S", "-B", "-X", f"pycache_prefix={cache_prefix}", "-c", code],
        env=dict(os.environ, CODEX_HOME=str(home), PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=cache_prefix),
        capture_output=True, text=True, timeout=8)
    if result.returncode != 0:
        raise ValueError(f"registered Python/lifecycle read-only probe failed: {python}")
    value = json.loads(result.stdout)
    version = value.get("version")
    if not isinstance(version, list) or len(version) != 3 or not all(type(n) is int for n in version):
        raise ValueError("registered Python returned an invalid version")
    if tuple(version) < (3, 13, 0):
        raise ValueError(f"registered Python requires 3.13 or newer: {python}")
    return {"executable": str(python), **value}


def attach_execution_health(payload: dict, home: Path, *, runtime_homes: list[Path] | None = None,
                            probe_hooks: bool | None = None) -> dict:
    paths = install_paths(home)
    issues = []
    reports = []
    try:
        active = read_json(paths.root / "active.json") if (paths.root / "active.json").is_file() else {}
        required = any(("completion_hook_sha256" in active,
                        (home / REGISTRY).exists(), (home / SCRIPT).exists()))
        entry = None
        if required:
            expected = active.get("completion_hook_sha256")
            if not isinstance(expected, str):
                raise ValueError("active generation has no completion hook binding")
            payload["completion_hook"] = verify_hook(paths, expected)
            entry = _registry_entry(paths, _read(paths, REGISTRY))
    except (InstallError, OSError, ValueError) as exc:
        payload["completion_hook"] = {"status": "error", "reason": str(exc)}
        issues.append(issue("completion_hook_invalid", str(exc)))
        required, entry = True, None
    routing_required, routing_entry = False, None
    try:
        active = read_json(paths.root / 'active.json') if (paths.root / 'active.json').is_file() else {}
        routing_required = 'routing_hook_sha256' in active or (home / routing_hook.REGISTRY).exists()
        if routing_required:
            expected = active.get('routing_hook_sha256')
            if not isinstance(expected, str):
                raise ValueError('active generation has no routing hook binding')
            payload['routing_hook'] = routing_hook.verify_hook(paths, expected)
            routing_entry = routing_hook.registry_entry(paths, _read(paths, routing_hook.REGISTRY))
    except (InstallError, OSError, ValueError) as exc:
        routing_required = True
        payload['routing_hook'] = {'status': 'error', 'reason': str(exc)}
        issues.append(issue('routing_hook_invalid', str(exc)))
    homes = execution_homes(home, runtime_homes)
    observed = probe_hooks if probe_hooks is not None else (home == Path.home() / ".codex" or bool(runtime_homes))
    for runtime in homes:
        row = {"codex_home": str(runtime), "status": "ok", "effective_hooks": "not_observed"}
        errors = []
        def fail(code: str, message: str) -> None:
            errors.append(issue(code, message, runtime))
        try:
            cfg = tomllib.loads((_read(install_paths(runtime), "config.toml") or b"").decode())
            if routing_required and routing_entry is not None:
                document = _decode(_read(install_paths(runtime), HOOKS))
                entries = document.get('hooks', {}).get('PreToolUse', [])
                if not isinstance(entries, list) or entries.count(routing_entry) != 1:
                    fail('routing_hook_missing_or_changed', 'execution home lacks the bound routing PreToolUse command')
                elif cfg.get('hooks', {}).get('state', {}).get(f'{runtime / HOOKS}:pre_tool_use:{entries.index(routing_entry)}:0', {}).get('enabled') is False:
                    fail('routing_hook_disabled', 'routing hook is disabled in execution-home config')
                if cfg.get('features', {}).get('hooks') is False:
                    fail('routing_hooks_feature_disabled', 'Codex hooks feature is explicitly disabled')
                try:
                    row['routing_python'] = probe_python(routing_entry, runtime, resolve_home=False, prefix=routing_hook.PREFIX)
                except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                    fail('routing_python_unusable', str(exc))
            if required and entry is not None:
                _, stop, owned = _owned(_decode(_read(install_paths(runtime), HOOKS)))
                if len(owned) != 1 or owned[0] != entry:
                    fail("completion_hook_missing_or_changed", "execution home does not contain the bound Company Stop command")
                else:
                    index = stop.index(owned[0])
                    key = f"{runtime / HOOKS}:stop:{index}:0"
                    row["hook_key"] = key
                    if cfg.get("hooks", {}).get("state", {}).get(key, {}).get("enabled") is False:
                        fail("completion_hook_disabled", "Company Stop command is disabled in execution-home config")
                if cfg.get("features", {}).get("hooks") is False:
                    fail("completion_hooks_feature_disabled", "Codex hooks feature is explicitly disabled")
                try:
                    # A failed installation integrity check cannot authorize
                    # importing installed helper code. The fixed version probe
                    # still runs without site packages or environment imports.
                    row["python"] = probe_python(entry, runtime,
                        resolve_home=payload.get("material_failure") is not True)
                    root = row["python"].get("sejong_home")
                    expected_root = Path(os.environ.get("SEJONG_HOME", str(home / "sejong"))).expanduser()
                    if root is not None and Path(root).resolve() != expected_root.resolve():
                        fail("completion_home_mismatch", "producer and callback resolve different Company record homes")
                except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                    fail("completion_python_unusable", str(exc))
            if (required or routing_required) and observed:
                probe_diagnostics = {}
                try:
                    hooks = list_hooks(runtime, diagnostics=probe_diagnostics)
                    row["effective_hooks"] = "observed"
                    company = [h for h in hooks if isinstance(h.get("command"), str) and h["command"].startswith(PREFIX)]
                    if required and (entry is None or len(company) != 1 or
                            company[0].get("command") != entry["hooks"][0]["command"]):
                        fail("completion_hook_not_loaded", "fresh Codex hooks/list did not load the bound Company Stop command")
                    elif required:
                        row["enabled"] = company[0].get("enabled")
                        row["trust_status"] = company[0].get("trustStatus")
                        if company[0].get("enabled") is not True:
                            fail("completion_hook_disabled", "fresh Codex hooks/list reports Company Stop disabled")
                        if company[0].get("trustStatus") != "trusted":
                            fail("completion_hook_untrusted", "fresh Codex hooks/list does not report Company Stop trusted")
                    if routing_required:
                        routed = [h for h in hooks if isinstance(h.get('command'), str) and h['command'].startswith(routing_hook.PREFIX)]
                        if routing_entry is None or len(routed) != 1 or routed[0].get('command') != routing_entry['hooks'][0]['command']:
                            fail('routing_hook_not_loaded', 'fresh Codex hooks/list did not load the routing command')
                        elif routed[0].get('enabled') is not True or routed[0].get('trustStatus') != 'trusted':
                            fail('routing_hook_untrusted', 'fresh Codex hooks/list does not report enabled trusted routing hook')
                except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                    row["effective_hooks"] = "unverifiable"
                    fail("hook_observation_unavailable", str(exc))
                finally:
                    if probe_diagnostics:
                        row["hook_probe"] = probe_diagnostics
        except (InstallError, OSError, ValueError, TypeError, AttributeError) as exc:
            fail("execution_home_invalid", str(exc))
        row["issues"] = errors
        if errors:
            row["status"] = "error"
        reports.append(row)
        issues.extend(errors)
    payload["execution_health"] = {"status": "error" if issues else "ok", "installation_home": str(home),
        "homes": reports, "scope": "Installation bindings, Python and fresh hook configuration; not loaded TUI context, model authentication or outcome verification."}
    if issues:
        payload.setdefault("issues", []).extend(issues)
        payload.update(status="error", severity="corrupt", material_failure=True, reproducible=False,
                       remediation="repair the reported execution-home hook/configuration; preserve unrelated hooks and disabled plugins")
    return payload
