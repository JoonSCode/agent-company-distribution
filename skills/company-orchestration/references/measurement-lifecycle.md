# Measurement lifecycle v2

This is an opt-in local evidence contract, not a provider proxy, server-wide
execution policy, watcher, or authenticated billing service. Version 1 evidence
remains readable and is never migrated or rewritten. Its future-worker launch
rejection remains in place. Worker table v2 and profile binding v3 are unchanged.

## Boundary and authority

Use `measurement.version: 2`, `mode: required`, the existing `goal_binding`,
`objective`, `criteria`, `boundary`, and `expected_actors`, then bind `ledger`
(relative to the record) and `prepare_sha256` returned by preparation. The parent
record still uses version 1. Do not copy v1 observed `participants` into a future
roster. Preparation freezes plan/objective/criteria hashes, the exact goal, and
boundary. Every actor needs a planned Codex attempt; coordinator, executor,
technical reviewer and integration actors cannot be omitted. Extra actors and
attempts require an append-only amendment before dispatch.

The supported adapter is `orca-local-terminal/v2`. Preparation does **not**
require an existing live worker or any Dispatch row. It verifies a local, ready
runtime, the orchestration and stop capabilities, readable Dispatch columns,
and the reviewed installed source named by `collector.host_source`.

| Orca version | Installed source pin | Settings and hook store |
| --- | --- | --- |
| 1.4.245 | Slices in `assets/orca-terminal-source-contract.json` | Legacy settings JSON and version-2 `agent-hooks/last-status.json` |
| 1.4.268 | Exact runtime chunk and, when automatic titles are enabled, the main-process archive and desktop renderer in `assets/orca-terminal-source-contract-1.4.268.json` | Active `profile-state.db` settings domain v1 and `agent-hooks/last-status.db` schema 202 |

The 1.4.268 reader uses read-only SQLite reads with committed WAL data. It reads
the active settings path from `agent hooks status`, checks SQLite authority,
and requires the matching local orchestration and hook databases. A legacy hook
file beside the SQLite store makes the source ambiguous. Only persisted entry
rows are used. Authority commitments and exit rows cannot supply a hook identity.
Unknown builds, schemas and changed source pins require review.

An explicitly selected **historical** hook `sample_session` names its transcript;
`sample_turn` proves strict response-level parser compatibility. Its timestamps
and old launch hashes do not establish future identity, and its usage is never
added to the experiment. No newest-file lookup occurs. `agent hooks status`
confirms managed Codex hooks and names the settings store. The receipt retains
only the capture flags. On 1.4.268 the Codex chat preference comes from
`nativeChatProviders.codex` or the global default surface when the provider
preference is absent. Capture requires a local terminal preference and enabled
Codex hooks. The reviewed 1.4.268 desktop title code derives tab labels from
existing text with local formatting. If automatic titles are enabled, the
adapter pins the reviewed main-process layout handler and renderer bytes before
allowing preparation.
1.4.245 keeps its existing automatic-title restriction. A 1.4.268 checked start
requires an existing non-bare local worktree. A denial changes no settings.
Private capture bytes are actually written/read/fsynced (including directory
fsync). The full capability/access probe is repeated immediately before launch.

**Postlaunch** binding still requires the exact saved accepted dispatch,
matching 64-hex launch-token hashes, task/run/pane/process and current runtime,
fresh local terminal hook, native `turn:` key and exact `session_meta`.
`receivedAt` is milliseconds, provider `key` is `session_id`, and `hostTurn.owner`
is `codex:SESSION`. On 1.4.268 the start receipt must report Codex terminal
mode and the same terminal handle as the full worker readback. That readback
must identify the same runtime epoch, local terminal, and owned terminal resource
for this exact Dispatch. The worker's stored placement must show a fresh
Codex terminal without a structured preference. `worker-show --full` supplies
these fields. First usage is not required. Missing correspondence leaves
the durable attempt unbound, blocks all further starts, and cannot become measured
success. Capability support is not a guarantee that a future hook will arrive.

These are local OS-account integrity guarantees. Hashes detect modifications to
pinned evidence; they do not authenticate a hostile local account that can
rewrite both host metadata and all roots of trust. No installed public Orca
raw-accounting export was established. Missing launch hashes, remote/structured
workers, Hermes turns, resumed sessions, multiple native turns, and nested model
work are unsupported and fail closed. A completed source may bind after launch
only through the preserved prelaunch/pending/start chain, not a backdated v1
preflight. The active outer Hermes session must not be represented as Codex CLI.

## Commands and durable state

All commands below use the installed package's `scripts` directory. No command
selects a model or silently changes surface, permissions, worktree, or fallback.

1. Create a JSON plan with `adapter`, `collector: {database, hooks, host_source, sample_session, sample_turn}`, `attempts`,
   and `limits`. Each attempt has `id`, `actor`, `provider: codex`, positive
   `ordinal`, `retry_of` (null or a prior attempt ID), `decision_sha256`, and
   `spec_sha256`. Each decision is the exact existing routing decision file.
   Limits are positive integer `max_attempts`, `max_raw_tokens`,
   `deadline_seconds`, plus `concurrency: 1`, `paid_fallback: false`.
2. Run `measurement_lifecycle.py prepare` with `--record RECORD --plan PLAN`,
   `--ledger DIR --orca ORCA`. Record its ledger and prepare
   hash in `measurement`. An unavailable collector denies before any worker
   start. This command creates an exclusive private directory and immutable
   prepare receipt; it does not launch a worker.
3. Run the ordinary `routing_launch.py` command with
   `--measurement-attempt ATTEMPT`. All ordinary routing, pin, resource,
   task/spec, effective model/effort and run checks remain enabled. A ledger lock
   spans launch; changing the result filename cannot relaunch the same attempt.
   `pending` is fsynced before host invocation. The exact start envelope is
   preserved before provider binding. `identity_observed` is sufficient to bind
   a new turn; first usage is not required before launch or identity binding.
4. If acceptance was durably observed but hooks were not yet available, use
   `measurement_lifecycle.py bind --record RECORD --attempt ATTEMPT --orca ORCA`.
   It reads the **existing** saved launch result; it never dispatches again.
   A crash/timeout without saved acceptance remains unknown. No fresh start or
   invented request ID is allowed. Automated `--retry-request` reconciliation is
   not implemented because an exact recoverable mutation ID was not established.
5. After the host reports completed/failed/cancelled, run the same CLI with
   `close`. Host completion alone never finalizes a snapshot: the exact native
   turn must end and every unique response (including lifecycle roundtrips) must
   have complete usage/mirror coverage. It checks host identity and source bytes
   again before committing `closed`. A completed host with an unfinished source
   yields `native completion pending`; the driver only reads it again within its
   original deadline, preserving partial snapshots, never relaunching or reporting
   on the worker's behalf. Native activity after completion is rejected.
   Incomplete failed/cancelled accounting is retained as `partial`, never zero,
   and keeps the attempt open. A legitimate execution retry needs a new prepared
   attempt linked to the failed one, and the existing checked `--task/--retry-of`
   route. It cannot erase the predecessor's costs.
6. An explicit `amend --plan EXTRA_ATTEMPTS_JSON` adds only new attempts/actors,
   under the same numeric budget and hash-linked ledger. It cannot rewrite old
   entries or authorize extra work while an earlier invocation is unresolved.
   Additional turns in an already bound/resumed session remain unsupported;
   use separately prepared fresh sessions rather than guessing turn assignment.
7. `finalize` and the success-only `settle` require the entire initial plus amended roster to be closed. They
   compare current source bytes with the closed snapshot, rejecting late output,
   then use `provider_usage.read_usage` on preserved snapshots. Each native turn
   and response occurs exactly once. Cumulative totals and token-count mirrors
   are validation inputs, never extra charges. The CLI returns a terminal receipt hash.
8. Put that hash in `measurement.settlement_sha256`, and populate ordinary
   `usage.expected`/`entries` from the observed response union. `record_check`
   independently replays snapshots and compares every raw count/session. Task
   and current Dispatch must match the executor's actual binding. Unsettled v2
   totals stay null. Success before final coordinator usage is rejected.

### Accounting receipt schema and policy verdict

The v2 immutable prepare and hash-linked event envelopes remain unchanged. New
terminal `settlement` values use **receipt_version: 1** with exactly
`accounting_status: complete`, `prepare_sha256`, `responses`, `raw_total`, and
`policy: {verdict, reasons, max_raw_tokens, success_eligible}`. The response union
includes failed predecessor costs. Policy reasons are ordered `budget_exceeded`,
`halted`, `attempt_failed`; the first reason is the verdict, or `within_budget`
when none apply. An explicitly planned successful retry can resolve an actor's
failed outcome, but cannot erase any cost, a halt, or the frozen cap.

Accounting completion means every planned attempt is reserved, exactly bound,
closed and fully metered. It does not mean successful output, independent review,
overall acceptance, provider billing compliance or permission to launch again.
Overbudget accounting is persisted with the unchanged cap and full usage, not
discarded. A complete failed/halted roster can also be finalized as non-success;
an incomplete, missing, duplicated or changed source cannot. Repeated finalization
replays evidence and returns the same receipt without adding events. An unknown
receipt version or changed policy fields fail closed.

`finalize` exits zero for verified accounting, including policy failure, and
always returns the separate policy. `settle` and the canary `run` exit nonzero
for non-success, while returning the recorded complete receipt. Neither starts
new work during finalization. `finalize --record RECORD --output-record NEW_RECORD`
can create a distinct sibling record with exact union usage and receipt binding;
it never overwrites RECORD. Policy failure sets the derived goal/assessment to
failed with deterministic `team_checks` basis, never invented independent review.
In-budget finalization does not invent overall success. Same-byte output retries
are idempotent; a different existing output is refused.

`record_check` distinguishes record validity (`ok`) from the replayed
`measurement.accounting_status` and `measurement.policy`. A valid failed record
reports its complete raw total. A policy-failed terminal record must retain
`goal.status: failed` and `known_failure: true`; successful assessment claims are
refused. A missing receipt is reported as missing terminal accounting, not as a
claim that the coordinator remains open. Final Task/Dispatch and artifact/
acceptance evidence still need actual source bindings; the generic accounting
export does not create them or certify dynamic upstream review.

Old v1 record evidence remains on its existing validator. Legacy v2 settlement
values containing only prepare hash, response union and raw total remain readable
without rewriting; policy is recomputed from their frozen limits and history.
They do not gain success eligibility merely because the old value lacked policy
fields. New receipt fields must not be stripped or interpreted as a new prepare
version. Replay historical experiments only in a separate copy or derived evidence
directory; preserve original events, failure history, sources and frozen limits.

The generic lifecycle deadline gates new starts; the observed token limit is a
soft stop between calls, not an in-flight provider cap. Close preserves evidence
after the launch deadline. The fixed canary driver below additionally observes
120-second turn deadlines and requests an exact dispatch-scoped stop. A source
that cannot prove completion cannot yield a successful final record.

## Completion and retention

Completion uses the existing `run_completion.validate_acceptance` and retains all
existing acceptance, routing/resource and quiescence checks. This remains a
success-only cleanup API: complete accounting with failed policy is refused,
and all failure evidence remains retained. Include the
`measurement-v2` consumer in the retention manifest and settle it. Preserve
`prepare.json`, the capture probe, every event, and every prefix/final/partial
source returned by `measurement_lifecycle.retained_files`. Keep the ledger inside
the Run directory. Missing or changed retained evidence blocks cleanup. Ordinary
v1 final evidence continues through its original gate without rewrites.

## Bounded live canary (prepared, not live evidence)

`assets/measurement-canary.json` is a **synthetic task definition**, not synthetic
usage represented as live output. It freezes three prompts: worker, independent
reviewer, then coordinator final integration. Human/deterministic preparation
happens outside this new boundary; outer development costs are neither included
nor claimed zero. The fixed reviewer prompt validates the proposed constant;
the operator must also inspect actual output and bind actual artifact/verdict
bytes in the final record. The driver additionally checks exactly one completed
assistant `final_answer` and the matching native `task_complete.last_agent_message`
against `expected_outputs`, before starting the next actor. Report/tool output
is not that final answer. Wrong, absent, duplicate or whitespace-altered answers
halt the canary while retaining already measured costs.

### Owned completion report exception

The installed 1.4.245 guide, `orchestration send --help`, and injected preamble
require `orchestration send --type worker_done`, not a standalone `worker_done`
command or MCP tool. The original no-tools prompt conflicted with that contract;
a correct constant alone does not settle the host. The new prompts permit only
the owned preamble's required `orchestration check` (and returned delivery ack),
then exactly one `orchestration send --type worker_done --outcome succeeded`.
Use the live preamble's exact executable, worker handle, Task and Dispatch IDs
and any capability flag; omit unrelated destinations, files and report metadata.
The report body is three sentences; the separate final answer remains the fixed
constant. Never synthesize completion with task-update or coordinator impersonation.

The owned halted worker's offered tool declaration was inspected read-only:
`functions.exec` exposes `tools.exec_command` with `cmd`, `login`, and
`yield_time_ms`. The prompts use that shell tool only for the required local
lifecycle commands, with login initialization disabled. They do not authorize
file/network/business work, arbitrary shell commands, helpers, further model
turns, or reporting retries. Unavailable tools, fenced ownership or uncertain
reporting must stop rather than guess. This is a narrow prompt authorization,
not an OS sandbox or a guarantee that a future model will comply. Same-turn tool
roundtrips may create several responses: include them all, dedupe only identical
response IDs, reject conflicts/omissions, and never charge cumulative mirrors twice.

Existing halted runs, their prepared prompt hashes and failed usage stay immutable.
This repair only supports a separately authorized fresh experiment; it does not
resume the first attempt or convert its one-role failure into a positive result.

Prepare a real-shaped v2 record with the fixture's exact roster/boundary and
coordinator owner, plus three honestly sourced routing decisions named
`worker.json`, `independent-reviewer.json`, `coordinator.json`. Decisions must bind
SHA-256 of the exact corresponding prompt. Do not promote unit-test evidence to
host evidence. `measurement_canary.py prepare --record RECORD --decisions DIR`
with `--orca ORCA --sample-session HISTORICAL_SESSION --sample-turn HISTORICAL_TURN`
builds the bounded plan and delegates only to preparation. It selects the
reviewed hook-store and installed source filenames for the observed version.
`--host-source` and `--hooks` allow selecting the actual reviewed paths.
Attach its returned prepare pointer to the record. Then explicit
`run --authorize-live --from SENDER --worktree WORKTREE` drives the fixed three
actors sequentially through the existing checked launcher, bind, close and
settle CLIs. `launch --actor ACTOR` uses the same bounded observation for just
that actor. Neither path adds a provider engine, execution retry or fallback.

The turn observation deadline is **120 seconds including launch**, within the
600-second run limit; the checked launcher still has a 60-second acceptance
wait. Deadline/error persists a permanent `halt`, then issues only
`orca orchestration worker-stop --dispatch EXACT_ACCEPTED_DISPATCH --json` after
runtime/task/run/process readback and DB correspondence. This discovered host
command fences the Dispatch and stops its owned supervised process, not unrelated
terminals. Stop intent, receipt, and `worker-show` readback are retained. Only a
`stopped` receipt plus stopped worker and exited observation is reported stopped.
On 1.4.268 the command can also stop helpers owned by the target. The canary
checks for helper Dispatches before invoking it and leaves a stop unconfirmed
if the full receipt includes helpers or a helper stop error.
`closed_agent_terminal` alone is **not** proof. Unknown acceptance cannot supply
a safe dispatch target: preserve it, report unknown, never guess or relaunch.
Stopped/unknown/cancelled attempts prevent every further start. Existing exact
sources are captured as complete or partial when possible; unbound remains null.
A halted canary cannot pass success-only settlement/completion. It can finalize
non-success accounting only when the entire frozen roster has complete evidence.

**No hard provider deadline or spend cap is claimed.** Stop requests/readbacks
have finite transport waits and may complete after 120 seconds or remain unknown;
a killed Python/CLI process does not cancel provider computation. If a strict
120-second cap is required, this host is unsupported: it needs a pre-accepted,
durable dispatch-scoped provider deadline/cancellation contract, including a
recoverable mutation identity and authoritative native-turn cancellation/exit
readback even if launch acceptance is lost. Do not start under a hard-cap claim.

Current host capability/access can be probed without any new worker. Live binding,
usage and stop effectiveness remain to be observed under separate authority. No
live model calls are part of offline tests. Outer Hermes coordination lacks the
strict response adapter and must stay outside this separately frozen experiment;
whole-Hermes-run measurement remains unavailable.

## Offline verification

`test_measurement_lifecycle.py` executes real Python CLIs against an explicitly
synthetic executable, SQLite DB, hooks and provider traces. It does not patch the
routing checker or introduce an allow flag. It exercises prepare with unknown
future IDs, checked launch, identity binding, final settlement, exact record
usage and completion retention, plus replay/race/unknown/missing-ID/tamper/partial
and cumulative append controls. Zero-active preparation, unsupported source/config,
intentional v2 retry retaining failed usage, deterministic three-actor driving,
scoped stop/exit readback and unknown-stop holds are exercised. Existing provider
parser and v1 regression suites
remain authoritative for their established source and compatibility invariants.
