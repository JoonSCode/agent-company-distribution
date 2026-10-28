# Company documents and terminal setup

Markdown is canonical. No separately maintained JSON mirrors user values.
`assets/config/common.md` supplies common rules. Its selected immutable source
preset is `assets/config/presets/single.md` (default) or `multiple.md`.
`${CODEX_HOME:-~/.codex}/agent-company/user.md` is private and outside managed
package generations. A small copied private `custom.md` can serve as a preset.
`--task-config` supplies a current-task Markdown document. Apply common → preset
→ user → task, bounded by higher-priority safety and authority. Prose instructions
remain ordered and source-linked; later machine fields replace complete values.
Explicit current-task choices do not edit the persistent user document.

Run from the reviewed source or installed snapshot repository:

```sh
uv run --no-project --python 3.13 python scripts/agent_company_config.py explain
uv run --no-project --python 3.13 python scripts/agent_company_setup.py install
uv run --no-project --python 3.13 python scripts/agent_company_setup.py reconfigure --no-input --yes --preset single --services claude-code --updater off
uv run --no-project --python 3.13 python scripts/agent_company_setup.py install --no-input --dry-run --services codex
```

The setup shows a concise Korean summary in a terminal (`--json` selects machine
output), including target, configuration, installer changes, updater, hook trust and
first safe task before applying. All prompts have flags; non-TTY never waits and
requires `--yes` for changes. `--dry-run` writes nothing and starts no installer,
provider call, authentication or download. Ctrl-C before apply preserves the user
document. Installation uses existing transactional bootstrap/install/recover,
not another execution engine. Setup saves intent before package activation, and restores previous document bytes
if installation fails or is interrupted. Existing transactional recover handles
an interrupted package operation. Package-file verification avoids Codex probes;
setup reports files_applied_runtime_pending, never runtime/auth/hook readiness.
Full bootstrap verification and Doctor remain available and unchanged in scope.

Front matter is optional for prose-only overrides. When machine values are present,
use schema_version: 1. An explicit malformed/unsupported header is rejected.
Front matter supports only flat keys, JSON-style YAML string lists, quoted or
simple strings, booleans and integer values. Duplicate/unknown keys, unsupported
versions, nested YAML and invalid combinations fail before a save. Example:

```markdown
---
schema_version: 1
preset: single
services: ["claude-code"]
updater: false
api_paid: false
---

# My choices
Use an independent reviewer for material outcomes.
```

Supported machine fields: schema_version (1), preset (single/multiple/custom),
services (unique selected service IDs), updater/api_paid (booleans), head_model
and head_effort (opaque strings), head_efforts (allowed opaque effort list;
head_effort is its preferred choice), excluded_models/excluded_model_prefixes
(denied exact IDs/prefixes) and service_order (unique service list),
max_workers (1–32; also bounded by actual task resource permission). Lists replace,
not append. service_order must use supported service IDs. A single preset allows
at most one service. Empty services means connection verification pending, not
Codex implied. The resolver's `show`/`explain` gives each source path and SHA-256.
Unknown critical settings never silently disappear. Put human judgment in prose;
there is no role/plan-to-model map or generic provider adapter framework.

Use `--config file.md` to import a user document, `--custom-preset file.md --preset
custom` to copy a modest preset, and `--head-model`, `--head-effort`,
`--head-efforts`, `--exclude-model`, `--services`, `--updater`, `--api-paid` to change explicit
machine values. Updater registration changes from reconfigure apply on the next install. Explicit
updater OFF at install unregisters the owned optional updater; an unconfigured
legacy installation preserves its existing registration. Reconfigure saves with an expected previous hash and an atomic
replace. Previous bytes are retained privately in `user-history/`. Update,
recover, rollback and uninstall leave user.md/custom.md/history intact. A newer
unsupported version is preserved and rejected; use its compatible reader rather
than automatically downgrading it. Source presets are never edited by setup.

No-config behavior: a fresh home has single/empty services/updater OFF/API OFF.
An existing active install without a document reports legacy_unconfigured and
keeps existing files and updater registration. It does not infer the previous
user's choices. Import explicitly supplied versioned Markdown with `--config`,
or use the documented flags to select machine values. Prose-only input stays
prose; setup does not infer model IDs, effort or service order from it. Existing
private documents remain intact during package update, recovery and rollback.
The former owner-specific translation flag is unsupported; keep its private
source and express any intended settings explicitly instead.

## Service intent and actual execution

Initial choices always include Codex (`codex`), Claude Code direct (`claude-code`),
Antigravity (`antigravity`, including its distinct Claude path), Grok (`grok`) and
Cursor (`cursor`). Selecting one is intent only. Before launch, the responsible
operator verifies host support, authentication, supported model/effort, tools,
permissions and subscription/API billing with dated source evidence. Unknown
billing blocks execution. A missing CLI is not no subscription. API-paid routes
require explicit opt-in and current authority; permission is never automatic
fallback. Setup/resolver tests perform no provider calls or sign-ins.

## Claude-only and other host integrations

Company policy does not require a Codex/Astra head. Selecting Claude Code direct
installs a thin explicit `/agent-company` wrapper through an owned symlink at
`~/.claude/skills/agent-company`. Use `--claude-home` for setup or the command-scoped
`CLAUDE_CONFIG_DIR` to select a different Claude configuration root. The explicit
--claude-home choice is saved privately as claude_home. An alternate execution
home requires an explicit Claude root so temporary installs cannot accidentally
write the real personal Claude directory. The template stays in Company assets outside Codex discovery; the rendered
managed wrapper is <execution-home>/agent-company/claude-entry/SKILL.md and contains absolute Company entry/configuration paths for its exact
installation home. Existing foreign directories, symlinks and changed wrappers
are preserved and rejected. Package update/rollback/recover/uninstall use the
existing transaction backup/restore with a derived ownership/hash registry;
private user documents remain outside that generation rollback.

This discovery contract follows [Claude skills documentation](https://code.claude.com/docs/en/skills):
personal skills, folder symlinks, explicit `/name` and disable-model-invocation.
It is not proof a live Claude session loaded the skill. The automatic native
role TOMLs, completion hook and runtime Doctor probe still target Codex. No Codex
binary or credentials are needed for package-file installation, document resolution
or the explicit Claude entry. Setup uses package-file verification; run full
runtime verification separately when using the Codex adapter.

In a new authenticated Orca Claude session, invoke `/agent-company` and verify it
reads the linked Company entry and resolved configuration. A first safe task is
“Propose three repository improvements; do not edit files or publish.” Use actual
supported Orca `--agent claude` Dispatches for handoffs. Give each worker a
self-contained scope, must/must-not, sources, approved role OS/kernel/task pack,
acceptance, independent verifier and actual Task/Dispatch lifecycle. Codex TOML
permissions/sandbox do not carry over to Claude; do not invent provider hooks.
The accepted lead explicitly runs the existing run_completion.py freeze/cleanup
checks at overall completion because Codex's Stop hook does not run for Claude.
A Claude turn end or worker_done is not overall acceptance or cleanup authority.

Antigravity Claude remains a separate service/auth/billing route from direct
Claude. Grok and Cursor use actual supported host launch and the same explicit
brief boundary; their selection installs no fabricated native adapter. Service
intent never proves authentication, model/effort support or included billing.

Invoke `record_check.py` with the same CODEX_HOME. For a run-local override pass
`AGENT_COMPANY_TASK_CONFIG=/absolute/task.md` to the specific command; for a
non-default user document pass `AGENT_COMPANY_CONFIG=/absolute/user.md`. These
are process-local inputs, not global setting changes. The checker validates
configuration gates and existing evidence/Task bindings; it is not a scheduler,
provider authentication verifier or live launch intercept. Synthetic receipts
prove only their own bounded structure and never authorize account execution.

## Python bytecode cache

Company's current configuration, setup, installer, updater, Doctor, sync,
recovery, role compiler, handoff, cycle-state, expertise manifest/example,
review-verdict and orchestration-script entrypoints select Python's
normal bytecode-cache prefix at `~/.cache/agent-company/python` before their
first Company import. The path belongs to the current user, is outside managed
skills and snapshots, and can be regenerated from the source. Company Python
children receive the same `PYTHONPYCACHEPREFIX`; the isolated Doctor probe uses
Python's equivalent `-X pycache_prefix` because `-I` ignores environment flags.
The prefix changes the current process only, not shell or other application
settings. `-B` still prevents cache writes when requested; the prefix also keeps
reads away from old caches in managed trees. Arbitrary Python imports performed
by another application are outside this entrypoint contract. Documented legacy
compatibility projections, historical evaluation tooling and developer-only
test/audit/benchmark scripts are also outside this current workflow contract;
their documentation or continued availability does not establish cache isolation.
Existing managed
files, including unexpected caches, remain subject to full integrity checking;
this setting does not repair or authorize removing them.
