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

## First worker task: opt-in local catalog

Use **one** installed entry: Codex `$agent-company` **or** Claude Code direct
`/agent-company`, according to the current agent. Entry availability is separate
from worker routing: the checked catalog launcher below starts Codex workers only.
A short first request is enough:

> Read this repository's README and write a five-item onboarding checklist to a
> new file. Have a separate reviewer check it against the README. Do not change
> code, publish, install, switch accounts or enable paid API use. Stop if the
> required launch evidence is missing; report acceptance separately from worker completion.

The lead confirms the output path and bounded execution budget before launch.
Use the existing exact host-listed worktree on **local Orca 1.4.245, 1.4.261,
1.4.263 or 1.4.268**, with a
fresh **non-measurement** `--spec` attempt. This is an explicit opt-in, not the
default route, a new-worktree path or an end-to-end preparation command.

From the reviewed checkout, inspect options without starting workers:

```sh
uv run --offline --no-python-downloads --no-project --python 3.13 python -B scripts/doctor.py --help
uv run --offline --no-python-downloads --no-project --python 3.13 python -B scripts/sync-status.py --help
uv run --offline --no-python-downloads --no-project --python 3.13 python -B scripts/agent_company_config.py explain --help
```

Use the [health checks below](#health-update-and-uninstall) with the actual
installation home, and inspect resolved configuration with `explain`. Keep private
configuration output local. Diagnostics do not grant worker authority.

The lead uses the [catalog preparation reference](host-model-catalog.md) in this order:

1. Collect fresh metadata for the exact host-listed worktree and use the semantic
   settings helper for the active profile. On 1.4.268, Orca needs a recent verified
   listing for that workspace and the helper takes `--app-version 1.4.268`.
   Preserve original observations.
2. Prepare the real record and decision: current Run/session ownership, resources,
   exact spec, profile/selection, configuration, authentication, tools, billing and
   support evidence remain required. The collector/helper do not fill these in.
   Optionally use the [nonlaunching private bundle](host-model-catalog.md#nonlaunching-preparation-bundle)
   via `routing_prepare.py prepare`, then `check`, from those existing inputs.
   Preserve its unused private output directory; a missing/partial manifest or
   `missing_fields` means stop, not permission to launch. Profile preparation,
   measurement capture and completion registration remain separate; no authority
   or observation is invented by the bundle.
3. Run `record_check.py routing-check DECISION --record RECORD --json`, then the
   existing checked `routing_launch.py` with the same worktree and actual sender,
   spec, decision/record and unused receipt/result paths. See [routing prelaunch](routing-prelaunch.md).
4. Read back exact Task/Dispatch and effective model/effort, review the actual
   artifact independently, then settle owned resources. Worker success is not
   acceptance of the artifact. Give the reviewer a separately prepared decision.

Stop on missing/changed authority, unsupported host/settings, selection mismatch,
unknown start, timeout or incomplete readback. Preserve receipts and reconcile;
never retry under a new filename, weaken evidence or use raw `worker-start` to
bypass denial. Model-list presence grants neither authentication nor billing;
there is no paid-API switch or automatic fallback. Measurement-required work
keeps its separate [lifecycle gates](measurement-lifecycle.md).

### Candidate versus installed evidence

At the 2026-11-09 pre-release handoff, this source candidate had an observed live
writer → separate Company reviewer flow; the reviewer returned **HOLD** on ambiguous
entry wording in the original checklist. This guide makes the two entries
alternatives; it does not rewrite or retrospectively accept that original local
acceptance evidence. The installed package was still `3fdb97` until the new
release installation. Candidate observations are not proof that an installed
session loaded this change: require the release's installed identity, Doctor/sync
and independent runtime verification before claiming the update is active.

## Organization/work panel and native operations

Read the [organization/work panel guide](status-tui.md) for `status_tui.py` and
the [Company-native operations guide](native-operations.md) for
`native_operations.py`. Both are in this package's `scripts` directory, need only
Python 3.13+ and can be inspected with `--help`. In a reviewed source checkout
their paths are `skills/company-orchestration/scripts/status_tui.py` and
`skills/company-orchestration/scripts/native_operations.py`; for installed use,
resolve the exact installed package path in the chosen execution home rather
than assuming a development checkout or changing existing sessions.

The panel's default combined view links company/team lead/member labels to
team-grouped tasks by explicit IDs; task dependency arrows never mean reporting
relationships. Start `status_tui.py --record /private/run/record.json --mode combined`
in the caller-owned PTY, or add `--once --json` for a read-only snapshot. This
directly refreshes the explicitly selected ordinary supplementary record as it
changes; basic use needs no manifest generation or manual SHA re-pin. Missing
task title, classification, organization, specialist and dependency metadata stay
unknown rather than being inferred from roles or registry entries.

For explicit enriched organization/task labels, use optional
`--metadata /private/run/view.json` with `--record`, or the existing
`--manifest /private/run/view.json` mode. That immutable metadata still pins the
exact record path/SHA/scope/revision and referenced sources. A stale attachment
rejects the whole candidate (ERROR plus last-good while resident); the owner
must explicitly supply refreshed metadata, not expect automatic re-pinning or
mixing old organization with a newer record.

For normal enriched state refresh, first use existing valid planning metadata:

```sh
python3.13 -B /path/to/company-orchestration/scripts/status_tui.py --record /private/run/record.json --metadata /private/run/view.json --capture-context /private/view/context.json
python3.13 -B /path/to/company-orchestration/scripts/status_tui.py --record /private/run/record.json --context /private/view/context.json
```

The output must be new; its parent must already be private and caller-owned.
Capture writes only that mode0600 file, not records or metadata. Keep the original
metadata and all pinned sources. The read-only context consumer preserves declared
title/classification/team/model/actual-specialist/explicit-needs through
ACCEPTED→SUBMITTED→ACCEPTED without hash edits. It freezes exact goal/scope/revision,
Task order/IDs and current Dispatch/actor/model/routing assignment. Changed
assignment or planning source rejects the whole candidate (ERROR plus last-good),
requiring explicit new metadata/context; no silent re-pin or partial stale merge.
Absent fields remain unknown. Captured organization acceptance is unknown, not
current consent or live execution. Original `--manifest`/`--metadata` stale guards
are unchanged. There is no automatic metadata producer, actual Run selection or
staffed-run capture. Synthetic fixtures do not prove actual staffing.
The program neither discovers private sessions nor creates
a lower Orca pane. Host targeting/placement and upper input/log preservation
require separate approved host work.

`native_operations.py storage report|plan --request ...` is read-only for exact
Company-owned Run roots. Explicit `storage apply` is destructive and requires
separate authorization, exact plan hash and unchanged completion guards; do not
use test fixtures as user cleanup authority. `usage report --request ...` unions
bound Codex response receipts and preserves unknown coverage, not account costs.
`reasoning prepare --request ... --output ...` and `reasoning check --bundle ...`
prepare/check the next unchanged Codex checked-launch inputs. Deep/ultrathink is
intent, not an automatic effort increase or current-turn switch: an approved low
effort remains low. Prepared resource/budget authorization is unknown/not supplied;
where required the next launcher still needs `--require-resource-manifest`,
`--resource-manifest`, `--declared-host`, `--declared-tool`, `--declared-billing`
and `--declared-spend`, plus actual sender and unused receipt/result paths.
Follow the exact spec-content and original request/decision bindings in the
native guide. No tool here calls Claude, launches a real model automatically,
changes global defaults or supplies missing permission.

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
