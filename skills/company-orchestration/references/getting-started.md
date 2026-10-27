# Setup, health checks and recovery

Use a reviewed, clean, pinned Git checkout. Installation uses Company-owned
transactional snapshots and does not require an external Core. Keep the persistent
Git source path printed by setup; installed snapshot `repo` directories contain
package files without `.git` and cannot serve as lifecycle workspaces.

## Prepare and preview

Prepare Bash, Git, uv and Python 3.13 separately. See the
[official uv installation instructions](https://docs.astral.sh/uv/getting-started/installation/).
`brew install uv` is an option only on macOS with Homebrew already installed.
Python 3.13 is required; older Python is not a fallback. Setup's terminal summary
is currently Korean; `--json` provides machine-readable output.

```sh
# Only when Python 3.13 is unavailable; separate network download.
uv python install 3.13
bash install.sh install --dry-run --no-input --services codex
# Apply interactively, choosing your intended service and updater setting.
bash install.sh install
# Or, after reviewing a matching preview, apply explicit choices without prompts.
bash install.sh install --services codex --updater off --yes --no-input
```

Preview is configuration-only: it does not save configuration, check source or
runtime readiness, or invoke the installer. Setup does not sign in or call a
provider. The shell setup/bootstrap wrappers use uv with
`--offline --no-python-downloads --no-project --python 3.13`. If that runtime is
missing, prepare it explicitly and rerun. These flags constrain uv, not every
later Git or installer operation; uv may still write cache metadata. Direct
`uv run` commands do not inherit the wrapper's offline policy.

Fresh setup has no implicit service, API-paid execution off and updater off.
A zero/one-service choice derives `single`; several services derive `multiple`.
Explicit or existing presets and private overrides are preserved.
Non-interactive apply requires `--yes`; cancellation before apply saves nothing.
The optional launchd updater requires macOS. Bash/POSIX entrypoints do not certify
other host runtimes and are not a native Windows installer.

## Verify the route and start a session

Installation success is `files_applied_runtime_pending`: files were applied,
while agent authentication, tools, permissions, billing and hook trust still need
verification. An existing receipt is not a health check. Service selection records
intent and grants none of these permissions. API-paid execution needs explicit
opt-in and is never an automatic fallback.

The automatic native role TOMLs and Stop hook target Codex. Review native `/hooks`
trust before expecting the runtime probe to pass. Claude Code direct installs an
owned explicit `/agent-company` skill link. For a custom Claude root, pass
`--claude-home` or use command-scoped `CLAUDE_CONFIG_DIR`; selecting a custom
execution home requires an explicit Claude root. Live discovery and authentication
need their own verification. Codex hooks do not run for Claude, so its lead performs
the existing Company completion checks explicitly. Other service choices do not
install a fabricated provider adapter. See [configuration](configuration.md).

Open a new Orca session after installation; existing sessions do not reload by
claim. Use `$agent-company` in Codex or `/agent-company` in Claude Code and ask for
three repository improvements without file edits or publication. Check that the
agent reads the installed entry and resolved configuration before further work.

Before nested teams, check **Desktop Settings → Orchestration → Nested worker
depth**. Root 0 → lead 1 → member 2 needs at least **2**. Setup does not inspect or
change that setting. Provider-native helpers depend on actual host tools and
remain internal to their existing Orca owner.

## Configure

Private choices default to `~/.codex/agent-company/user.md` under the existing host
adapter. That directory name does not require a Codex account. `--home` selects
another execution home. For lifecycle commands below, use command-scoped
`CODEX_HOME` when checking a custom home. Keep the same Claude configuration root.

```sh
bash scripts/setup.sh reconfigure --preset multiple --services codex,claude-code --dry-run --no-input
# After reviewing the plan:
bash scripts/setup.sh reconfigure --preset multiple --services codex,claude-code --no-input --yes
# docs-audit: illustrative
uv run --no-project --python 3.13 python scripts/agent_company_config.py explain
```

Configuration follows common rules → preset → private user override → current
task, within higher-priority authority. It does not switch a running model or app
default. Private `user.md`, `custom.md` and history are preserved across package
update, recover, rollback and uninstall. Reconfigure saves configuration; an updater
registration change takes effect on the next install. See the
[configuration contract](configuration.md) for imports, custom presets and schemas.

## Health, update and uninstall

Run from the persistent Git source reported by setup, with the correct execution
home. These read-only checks report installation/runtime gaps separately:

```sh
# docs-audit: illustrative
uv run --no-project --python 3.13 python -B scripts/doctor.py --json
# docs-audit: illustrative
uv run --no-project --python 3.13 python -B scripts/sync-status.py --json
# docs-audit: illustrative
uv run --no-project --python 3.13 python scripts/agent_company_installer.py update --dry-run
# docs-audit: illustrative
uv run --no-project --python 3.13 python scripts/agent_company_installer.py uninstall --dry-run
```

Review the exact candidate and dry-run before applying `update` or `uninstall`
without `--dry-run`. Prepare and review the intended Git revision separately;
do not assume an update command proves you have the latest source. Diagnostics
cannot prove that existing sessions read new instructions or that an app goal
succeeded.

## Recover an interrupted apply

Keep the original error and inspect `configuration_restored`, `restore_pending`
and `save_outcome_unknown` in setup's failure output. Restoration preserves
concurrent edits; restored configuration does not certify package rollback.
Package and host-entry state can remain unknown. Inspect the existing transaction
journal before retrying from the same reviewed Git source and execution home.

```sh
# docs-audit: illustrative
uv run --no-project --python 3.13 python scripts/agent_company_installer.py recover
# docs-audit: illustrative
uv run --no-project --python 3.13 python scripts/agent_company_installer.py rollback
```

`recover` settles the existing transaction; `rollback` restores a retained package
generation. They are state-changing alternatives, not a sequence to run blindly.
Keep prior generations and private documents. Unsupported document versions are
rejected and preserved. Restoring historical Core-bound bytes does not certify
that historical runtime as Core-free.

For help, include the package version, expected behavior and a redacted error in
[GitHub Issues](https://github.com/JoonSCode/agent-company-distribution/issues). Do not include
private configuration, credentials, personal paths or raw traces.
