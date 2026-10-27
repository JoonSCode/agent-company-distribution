# Agent Company for Orca

**Turn an app goal into coordinated work, with clear ownership and independent review.**

Agent Company helps you build and run a profitable app portfolio. It brings planning,
design, development, marketing and release work into one workflow inside Orca.
Describe the outcome you want; Company helps define the work, assign specialists
and check the result against that outcome.

You keep authority over goals, cost, publication and irreversible actions.
Workers do not approve their own work.

[Install](#install) · [First task](#try-a-first-task) · [How it works](#how-it-works) · [Configuration](#configuration) · [Help](#help)

## Install

You need an Orca host that supports your chosen agent, plus Bash, Git,
[uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.13.
Prepare missing tools separately. The optional daily updater requires macOS;
the Bash entrypoints are not a native Windows installer.

Clone this distribution, review the exact revision, then keep that checkout pinned:

```sh
git clone --single-branch https://github.com/JoonSCode/agent-company-distribution.git
cd agent-company-distribution
git rev-parse HEAD
git checkout --detach HEAD
# Only if Python 3.13 is missing; this downloads Python.
uv python install 3.13
# Preview configuration before applying it interactively.
bash install.sh install --dry-run --no-input --services codex
bash install.sh install
```

Replace `codex` with your intended service when previewing. Fresh setup leaves
API-paid execution and the updater off; no service is selected implicitly.
Selecting a service does not sign you in or verify its runtime support.
Setup applies package files and reports **runtime verification pending**.
Review hook trust and agent readiness, then open a new Orca session.

Keep the persistent Git source path printed by setup. It is needed for updates
and recovery. Snapshot `repo` copies have no Git history and are not update
workspaces. See the [setup and recovery guide](skills/company-orchestration/references/getting-started.md)
for non-interactive installation and health checks.

## Try a first task

In a new Codex session, invoke `$agent-company`; for the installed Claude Code
entry, use `/agent-company`. Then start with a small, read-only request:

> Agent Company: Read the installed Company entry and resolved configuration.
> Propose three improvements to this repository, with reasons and checks for each.
> Do not edit files or publish anything.

Company should clarify material choices, identify an owner and propose observable
completion criteria. You can then authorize a bounded implementation. An unfinished
idea is enough to start; a full specification is not required.

## How it works

Company supplies the operating rules. **Orca runs the workers and records their
Tasks, Dispatches and messages.** A Task is the work; a Dispatch is one attempt.
Company's supported entry, installation, updates and recovery do not require an
external King Sejong Core checkout or installation.

1. **Agree on the outcome.** Establish scope, constraints and how to check success.
2. **Assign the work.** Use the smallest sufficient team. For multi-team goals,
   leads agree on contributions before assigning members.
3. **Work and integrate.** Specialists raise concerns, use source evidence and
   bring their results back to the responsible lead.
4. **Verify and settle.** Review the integrated result independently and account
   for workers and retained evidence before closing the goal.

The six role areas are founder strategy, planning, marketing, design, development
and QA/release. Roles are responsibilities, not fixed models or mandatory staffing.
Models and reasoning effort are selected for the task and the supported execution route.
When the actual host supports them, provider-native helpers can contribute bounded
internal work under an existing Orca owner. The owner reviews and integrates their
results; they do not replace Orca Task/Dispatch ownership or independent QA.
There is no assumed automatic bridge between the two.

Source checks, installed files, authenticated execution and user outcomes are
separate evidence. A completed worker is not proof that the overall goal succeeded.
Unreported token usage stays unknown; Company makes no measured savings claim.

## Configuration

Your choices live in private Markdown outside package generations. Precedence is:
common rules → selected preset → private user override → explicit current task,
within higher-priority instructions and permissions.

```sh
# Preview without saving.
bash scripts/setup.sh reconfigure --preset multiple --services codex,claude-code --dry-run --no-input
uv run --no-project --python 3.13 python scripts/agent_company_config.py explain
```

Available service choices are Codex, Claude Code direct, Antigravity, Grok and Cursor.
These are intent settings, not a promise of an adapter, authentication or included
billing. The automatic native role files and completion hook target Codex.
Claude Code direct has an explicit skill entry; other routes need actual host
support and self-contained briefs. Antigravity's Claude route is separate from
Claude Code direct. See the [configuration contract](skills/company-orchestration/references/configuration.md).

## Architecture

| Layer | Responsibility | Read more |
| --- | --- | --- |
| Company entry | Explicit invocation and goal ownership | [Entry](skills/agent-company/SKILL.md) |
| Coordination policy | Staffing, model selection, evidence and integration | [Operating policy](skills/company-orchestration/SKILL.md) |
| Specialist roles | Founder strategy, planning, marketing, design, development and QA/release | [Role sources](agents/) |
| Runtime tools | Configuration, installation, health and record checks | [Setup guide](skills/company-orchestration/references/getting-started.md) |
| Orca host | Actual workers, messages and lifecycle | [Execution contract](skills/company-orchestration/references/orca-contract.md) |

## Help

Use the [setup, health checks and recovery guide](skills/company-orchestration/references/getting-started.md)
when installation or updates need attention. Review dry-runs before changing an
installation. Private configuration and previous package generations have separate
preservation rules; restored files alone do not certify runtime readiness.

Read the [changelog](CHANGELOG.md), or report a reproducible problem in
[GitHub Issues](https://github.com/JoonSCode/agent-company-distribution/issues). Include the
version, expected behavior and a redacted error; omit credentials, personal paths
and raw execution traces.

## Contributing

This repository is the installable runtime projection. Start with a
[public issue](https://github.com/JoonSCode/agent-company-distribution/issues)
for bug reports or proposed changes. Include the expected behavior, observable
acceptance criteria and any checks you ran. Maintainers apply changes to the
development source and regenerate the distribution; installed role files are
not the editing surface.

## License

[MIT](LICENSE). External component terms are listed in [Third-party notices](THIRD_PARTY_NOTICES.md).
