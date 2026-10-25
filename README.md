# Agent Company for Orca

Agent Company helps an Orca user plan, design, implement and independently verify
work on an app portfolio. It uses Orca Task/Dispatch and requires no King Sejong
Core checkout, install, pin or account. The user retains decisions about goals,
cost, publication and irreversible actions. Workers cannot approve their own work.

Use a reviewed, pinned Git checkout of this standalone distribution. Requirements:
macOS for the optional launchd updater, Git, uv with Python 3.13+, and an Orca host
that supports the chosen agent route. The policy can use Codex, Claude Code direct,
Antigravity (its Claude route is separate), Grok or Cursor. Service selection is
intent; actual support, authentication, tools, model/effort and billing must be
verified before execution. No provider sign-in or API call occurs during setup.

```sh
git clone --branch v0.2.0 --single-branch https://github.com/JoonSCode/agent-company-distribution.git
cd agent-company-distribution
git describe --tags --exact-match  # v0.2.0
# From this reviewed pinned checkout; inspect changes before applying.
bash install.sh install --dry-run --no-input --services claude-code
bash install.sh install
# Fully specified, prompt-free alternative:
bash install.sh install --preset single --services claude-code --updater off --no-input --yes
```

Do not pipe the historical Core-bound v0.1.0 curl installer. This checkout's
`install.sh` runs terminal setup, which wraps the existing transactional installer
from a persistent managed source. A fresh public configuration has updater OFF,
API-paid OFF and no implicit connection. Enable the optional daily updater only
by explicit choice. No API-paid automatic fallback is allowed.

Configuration is Markdown: common operating rules → single/multiple preset →
private user override → explicit current task, bounded by higher-priority safety
and authority. User choices live in `<execution-home>/agent-company/user.md` and
are preserved across update/rollback/uninstall. The execution home defaults to
`~/.codex` for the existing host adapter; `--home` selects another private home.
This directory name does not require a Codex account.

```sh
bash scripts/setup.sh reconfigure --preset multiple --services claude-code,antigravity --no-input --yes
uv run --no-project --python 3.13 python scripts/agent_company_config.py explain
```

See [the configuration contract](skills/company-orchestration/references/configuration.md)
for supported keys, copied custom presets, cancellation, versioned saves, explicit
Markdown import and actual route checks. `--dry-run` writes no files and
starts no downloads/installer. Non-TTY never waits; use `--yes` after reviewing a
plan. Existing documents are merged, not silently reset to public defaults.

The packaged automatic native roles and Stop hook currently target Codex. File
installation, native hook trust and provider/runtime verification are separate
results. Review Codex native `/hooks` before its runtime probe can pass. A
Claude-only Company does not require a Codex/Astra head: in an authenticated Orca
Claude session, explicitly read the installed `skills/agent-company/SKILL.md`,
its linked configuration and role OS; use self-contained Orca worker briefs.
Selecting Claude direct adds an owned explicit `/agent-company` entry under
`~/.claude/skills` (or `--claude-home`); live discovery/auth remains unverified.
Codex Stop hooks do not run for Claude, so the lead explicitly performs the
existing completion freeze/cleanup checks. A Codex
Doctor gap does not establish Claude availability or absence. Read the exact
setup result and configuration guide before claiming native integration.

First safe task: “Read the Company entry and resolved configuration, then propose
three improvements to this repository. Do not edit files or publish.” Use a new
session when testing newly installed skills; old sessions do not reload by claim.

Setup prints the persistent Git source directory in
`installation.sources.agent_company`. Keep that path and run lifecycle commands
from that **Git source directory** (or the original reviewed pinned Git checkout).
`<execution-home>/agent-company/active.json` records the installed commit and
snapshot ID; it does not record the source path. Snapshot `repo` directories are
read-only package copies without `.git`, so do not run installer update there.
From the persistent Git source directory run:

```sh
uv run --no-project --python 3.13 python scripts/doctor.py --json
uv run --no-project --python 3.13 python scripts/sync-status.py --json
uv run --no-project --python 3.13 python scripts/agent_company_installer.py update --dry-run
uv run --no-project --python 3.13 python scripts/agent_company_installer.py recover
uv run --no-project --python 3.13 python scripts/agent_company_installer.py rollback
uv run --no-project --python 3.13 python scripts/agent_company_installer.py uninstall --dry-run
```

Set `CODEX_HOME` for these commands when using a custom execution home. Keep the
explicit Claude configuration root (`CLAUDE_CONFIG_DIR` or the saved `claude_home`)
when using a custom Claude location. Doctor and sync report installation/runtime
gaps separately; a Claude-only file install does not certify Codex hook readiness.
Inspect a
dry-run before update or uninstall. Rollback restores package generations and
preserves the current private document; unsupported document versions are rejected
and preserved. Setup reports package files applied with runtime verification pending; no
Codex binary or credentials are needed for that file-only install. A partial
install is not runtime verification. Private evaluation
inputs and internal history are excluded from this runtime distribution.

See [v0.2.0 release notes](CHANGELOG.md) for the release scope and verification boundaries.
