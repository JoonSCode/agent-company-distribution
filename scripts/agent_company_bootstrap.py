#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
# uv run --script scripts/agent_company_bootstrap.py install --user --dry-run
# uv run --script scripts/agent_company_bootstrap.py install --user
# uv run --script scripts/agent_company_bootstrap.py verify
# ──────────────────

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, Literal

from agent_company_bootstrap_sources import (
    BootstrapError,
    CommandRequest,
    SourceSpec,
    checked,
    command,
    core_spec,
    managed_container,
    lexical_home,
    materialize_source,
    source_identity,
    source_target,
    validate_materialized,
)

type Action = Literal["install", "verify"]
type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
ROOT: Final[Path] = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class BootstrapConfig:
    action: Action
    codex_home: Path
    user: bool
    dry_run: bool
    replace_core: bool
    codex_guidance: str


def install_environment(config: BootstrapConfig, core: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "CODEX_HOME": str(config.codex_home),
        "SEJONG_HOME": str(config.codex_home / "sejong"),
        "AGENT_COMPANY_DEP_MODE": "local",
        "AGENT_COMPANY_KING_SEJONG_LOCAL_PATH": str(core),
    })
    return env


def verify_core(config: BootstrapConfig, core: Path, env: dict[str, str]) -> None:
    installer = core / "scripts" / "install-sejong.sh"
    checked(CommandRequest(("bash", str(installer), "--verify", "--scope", "user", "--codex-guidance", config.codex_guidance), core, env, "core_verify_failed"))


def verify_company(config: BootstrapConfig, company: Path, core: Path, env: dict[str, str]) -> None:
    installer = company / "scripts" / "agent_company_installer.py"
    checked(CommandRequest((sys.executable, str(installer), "update", "--dry-run"), company, env, "company_verify_failed"))
    sejong_home = Path(env["SEJONG_HOME"])
    output = checked(CommandRequest((sys.executable, str(company / "scripts" / "agent_company_sync_status.py"), "--codex-home", str(config.codex_home), "--sejong-home", str(sejong_home), "--core-source", str(core)), company, env, "company_verify_failed"))
    try:
        status: JsonValue = json.loads(output)
    except json.JSONDecodeError as exc:
        raise BootstrapError("company_verify_failed", "Core sync status was not JSON") from exc
    activation = status.get("activation") if isinstance(status, dict) else None
    if not isinstance(status, dict) or status.get("state") != "healthy" or not isinstance(activation, dict) or activation.get("allowed") is not True:
        raise BootstrapError("company_verify_failed", "Core sync status is not healthy")


def selected_sources(config: BootstrapConfig, source_root: Path) -> tuple[SourceSpec, SourceSpec, dict[str, Path]]:
    company_spec = source_identity(source_root)
    king_spec = core_spec(source_root)
    return company_spec, king_spec, {
        "agent_company": source_target(config.codex_home, company_spec),
        "king_sejong": source_target(config.codex_home, king_spec),
    }


def bootstrap(config: BootstrapConfig, *, source_root: Path = ROOT) -> dict[str, JsonValue]:
    config = replace(config, codex_home=lexical_home(config.codex_home))
    company_spec, king_spec, targets = selected_sources(config, source_root)
    if config.dry_run:
        container = managed_container(config.codex_home, create=False)
        if container.exists():
            for target, spec in ((targets["agent_company"], company_spec), (targets["king_sejong"], king_spec)):
                if target.exists() or target.is_symlink():
                    validate_materialized(target, spec)
        return {"status": "dry_run", "sources": {key: str(value) for key, value in targets.items()}, "king_sejong_commit": king_spec.commit}
    if config.action == "verify":
        _ = managed_container(config.codex_home, create=False)
        for target, spec in ((targets["agent_company"], company_spec), (targets["king_sejong"], king_spec)):
            if not target.exists():
                raise BootstrapError("source_missing", str(target))
            validate_materialized(target, spec)
    else:
        targets["agent_company"] = materialize_source(config.codex_home, company_spec)
        targets["king_sejong"] = materialize_source(config.codex_home, king_spec)
    company, core = targets["agent_company"], targets["king_sejong"]
    env = install_environment(config, core)
    identity = Path(env["SEJONG_HOME"]) / "state" / "core-install-identity.json"
    if config.action == "install":
        core_args = ["bash", str(core / "scripts" / "install-sejong.sh"), "--scope", "user"]
        if identity.exists():
            verified = command(CommandRequest((*core_args[:2], "--verify", "--scope", "user", "--codex-guidance", config.codex_guidance), core, env))
            if verified.returncode != 0 and not config.replace_core:
                raise BootstrapError("core_install_conflict", "installed Core differs; rerun with --replace-core only if replacement is intended")
            if verified.returncode != 0:
                checked(CommandRequest((*core_args, "--force", "--codex-guidance", config.codex_guidance), core, env, "core_install_failed"))
        else:
            checked(CommandRequest((*core_args, "--dry-run", "--codex-guidance", config.codex_guidance), core, env, "core_preflight_failed"))
            checked(CommandRequest((*core_args, "--codex-guidance", config.codex_guidance), core, env, "core_install_failed"))
        verify_core(config, core, env)
        action = "update" if (config.codex_home / "agent-company" / "active.json").is_file() else "install"
        installer = company / "scripts" / "agent_company_installer.py"
        checked(CommandRequest((sys.executable, str(installer), action, "--dry-run"), company, env, "company_preflight_failed"))
        checked(CommandRequest((sys.executable, str(installer), action, *(["--user"] if config.user else [])), company, env, "company_install_failed"))
    else:
        verify_core(config, core, env)
        action = "verify"
    verify_company(config, company, core, env)
    return {"status": "verified" if config.action == "verify" else "installed", "company_action": action, "sources": {key: str(value) for key, value in targets.items()}, "king_sejong_commit": king_spec.commit}


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Agent Company with its exact King Sejong Core dependency")
    parser.add_argument("action", nargs="?", choices=("install", "verify"), default="install")
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))))
    parser.add_argument("--user", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace-core", action="store_true")
    parser.add_argument("--codex-guidance", choices=("default", "none", "user"), default="default")
    args = parser.parse_args()
    try:
        result = bootstrap(BootstrapConfig(args.action, lexical_home(args.codex_home), args.user, args.dry_run, args.replace_core, args.codex_guidance))
    except BootstrapError as exc:
        print(json.dumps({"status": "blocked", "error": exc.code, "detail": exc.detail}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
