# Orca execution contract

Use this reference before supervised Company execution. Company owns goal,
staffing, model/context and acceptance policy. Orca owns the current Task/Dispatch,
message, process and resource facts. This is an operator workflow, not a new
queue, scheduler, automatic adapter or permission layer.

## Resolve and observe once

Use the session's `ORCA_CLI_COMMAND` when provided; a declared development checkout
uses `orca-dev`. Otherwise use `orca` on macOS/Windows and the supported `orca-ide`
on Linux outside Orca (bare `orca` can be the GNOME screen reader). Keep that exact
executable throughout the run. `ORCA` below is a placeholder, not a shell variable.
Do not silently switch executables, hosts or billing paths after an error.

At the first actual coordination action, check the package and observe the
current runtime through [update policy](update-policy.md). The read-only tool
loads the current version-matched guide and selected references, checks their
identity against the accepted baseline and exposes differences. Reuse matching
evidence within the run while host/build/capabilities remain applicable. Review
changed relevant contracts before affected commands; do not let a stale snapshot
override the host. For a new conditional operation, retrieve just its named
reference from `ORCA skills get orchestration --reference references/<name>.md`.
If unsupported, use documented `--full` or read-only command `--help`; never guess
new flags. Keep unsupported affected operations pending and continue unrelated work.

The worker's live injected preamble overrides copied lifecycle examples. Keep
its exact executable, handle, capability, Task and Dispatch values. Do not
reconstruct a capability or reuse settled IDs. An ordinary terminal without a
live worker preamble must not impersonate a dispatched worker.

## Create one authoritative attempt

A Run is a durable namespace/inbox, not a scheduler. A Task is work; a Dispatch
is one authoritative attempt. Do not also use the legacy Core TeamExecutor or
Company job dispatcher for the same work. For a full unsupervised handoff, use
the supported Orca worktree/terminal handoff path without Run/Task tracking; do
not replace requested supervision with a mere accepted terminal prompt.

After the [model policy](model-routing.md) decision, write the routing decision
and run this before `worker-start` on a fresh Company run:

```text
python3 /path/to/company-orchestration/scripts/record_check.py routing-check decision.json --record record.json --json
```

Use the current supplementary record when available. This rejects a mismatched
goal scope/revision before dispatch; a new planned task need not already be in
the record. Existing tasks must match their current dispatch and known requested
model/effort. Standalone `routing-check decision.json --json` remains supported
but checks only the decision itself. Keep the receipt in the run record.
The command does not launch, block, or
replace Orca. Completion of a fresh retention manifest later rejects a missing
decision; it does not stop a launch that already happened. See
[routing decisions](record-contract.md#routing-decisions). Then create bounded
ready tasks:

```text
ORCA orchestration run-create --objective "<approved objective>" --json
ORCA orchestration worker-start --spec "<self-contained brief>" --worktree <exact-selector> --agent <supported-agent> --model <supported-id> --effort <supported-effort> --json
```

Pass model/effort only when supported and authorized. Standing user authorization
can permit per-task selection without the user naming a model each time; the
baseline guide's default-inheritance advice does not negate that authorization.
Omit unsupported flags. `--effort` requires `--model`; neither combines with
`--terminal`. Some agent paths select models through their own supported config.
Record requested and effective settings separately. A ready/input-accepted
receipt alone does not establish model quality or goal completion.

At creation or reuse, name every worker by its actual role and bounded task. Pass a concise
`--task-title` (for example, `Development lead · handoff policy`) rather than a
generic worker label. Give the terminal/chat the same useful visible name through
the host's supported naming path, and verify its readback separately: a Task title
receipt alone does not prove the visible surface changed. Preserve the actual
role and do not rename unrelated tabs or treat naming as ownership evidence.
A process auto-title can differ from the custom tab name; verify the actual
surface rather than substituting that process-title field.

If the execution host has observed shell-startup questions or command loss before
`agent_readiness`, do not send another fresh agent command through that startup
path. Before the next Task attempt, use the conditional
[prepared-shell workflow](launch-readiness.md): create an owned blank terminal
without a command, inspect startup, verify a fresh harmless nonce round trip,
then start one agent in that same terminal and verify its actual readiness before
`worker-start --terminal`. Questions/unknown proof block command delivery; the
checker never answers prompts or launches anything. This is a Company operator
guard for an observed host risk, not an Orca startup fix or a new requirement for
unrelated healthy launches. Preserve the failed attempt and exact recovery rules.

Do not change a running assignment by writing canonical model or effort defaults.
Use a per-process flag the launch route supports, or keep the current setting
and record why the checkpoint continues. Read back the observed setting and
compare default config before and after a selector. A menu or slash command that
saves defaults is not session-only. Do not use a global write followed by
restore as the normal path. Unsupported routes hand off at a boundary.

Existing workspaces are valid, including folders without Git. Prefer exact
placement. New/remote placement requires the host's `placement-and-remote`
reference and relevant capabilities. Remote process/filesystem/cleanup facts
belong to the execution host; never fall back to a local writer on uncertainty.

Start the independent ready wave before waiting. Use `task-create` with genuine
dependencies when ordering is needed; avoid unnecessary deep chains. Nested
workers keep parent ownership and host depth limits; a new Run cannot bypass
them. A failed `worker-start` is not permission to start again: inspect its
failed stage, residual resources and exact recovery receipt first.

## Task lineage and internal provider helpers

A dispatched worker starts a useful nested leaf through its live preamble's
`worker-start --spec`, inheriting the current Run without creating another one.
When supported, set `--parent` to its actual Task id. Verify the resulting Task's
`parent_id` separately from the Dispatch's `creatorDispatchId`, depth and creator
inbox route. They describe work ancestry and attempt/message ownership respectively;
neither a role name nor a tab placed beside another proves both. Preserve original
Task/Dispatch receipts and the child's reply before claiming a working hierarchy.
Use current host guidance for routing; an explicit Run selector is not authority
to impersonate its coordinator. Company policy cannot change Orca's UI grouping.

### Bounded native-helper workflow

Consider provider-native helpers alongside direct tools and Orca workers for a
useful separable contribution. Use the actual exposed native tools only when the
current task policy, permissions, selected service, billing and aggregate resource
budget permit them. Availability alone is not a reason to delegate; tiny or tightly
coupled work can stay with one owner. This workflow adds no enable switch, generic
adapter, scheduler or required Orca Task for each internal helper.

1. The owning Orca worker gives a self-contained direction through the actual
   native tool: goal, exact input/source revision, read-only or exclusive file
   ownership, constraints, expected artifact/checks and stop/report conditions.
   Use the [compact direction/report](session-continuity.md#compact-direction-and-report)
   in one existing work note; do not create a second tracker. Name the native
   helper by role and bounded task through supported naming, and read back its
   actual name/identifier. No terminal tab is implied by a native helper name.
2. Select model and effort by the same task-fit reasoning as other contributions.
   Record requested settings separately from actual native readback or unknowns;
   do not infer them from a role, catalog or requested flag. Count native helpers
   against the combined resource limit, including nested work. No paid API or
   global defaults change is authorized by native tool availability.
3. Preserve the original helper result and actual identifier with the owning Orca
   Dispatch. Its report names artifacts/checks, failures or unresolved decisions,
   settings or unknowns, usage coverage and resource state. The parent reads the
   originals, resolves conflicts and records what it integrated or rejected and
   why. A tool call or an availability probe is not a useful completed contribution.
4. Before the parent's completion, settle helpers through the actual native
   lifecycle: retain the completed result, reuse for a named next contribution or
   release when supported. Record completed versus released separately; unavailable
   lifecycle controls or uncertain execution remain explicit gaps. Do not leave a
   live or uncertain helper unaccounted for or stop unrelated workers.

Native helpers do not replace requested Orca Task/Dispatch provenance, accepted
ownership or independent QA. Keep native identifiers separate from real Orca
Task/Dispatch IDs. There is no automatic Task/Dispatch bridge. A native role
definition, catalog or available tool is not evidence of a live helper run or an
Orca bridge. Never invent such a bridge or duplicate a writer to obtain one.

## Process messages and verify results

```text
ORCA orchestration check --wait --types "worker_done,escalation,question" --timeout-ms 30000 --json
ORCA orchestration reply --id <question-id> --body "<answer>" --json
ORCA orchestration send --to dispatch:<dispatch-id> --subject "Follow-up" --body "<scoped guidance>" --json
```

Use `check --terminal <handle>` when the caller is not inferable; never `--from`
for check. A consuming check delivers the oldest FIFO batch and replays it until
acknowledged. Process every row, including ones outside a wake filter: answer
questions, validate completions against the expected active Dispatch, read
artifacts and decide settled terminal ownership before acknowledging. A successful
send proves enqueue, not reading, acceptance or turn start.

The accepted team lead launches or reuses its members, reads their evidence and
integrates the team result before reporting milestones, blockers or material
decisions to the overall head. Do not routinely relay unchanged status through
each level. Preserve direct urgent escalation, blocking questions and required
heartbeats. Distinguish active tool waits from status-only model turns; use
supported arrival notifications or bounded event waits within host limits and
required user updates. Yield only when the host supports resumption without
losing supervision; otherwise keep the required supervised wait. Do not create
cache-maintenance turns. The scoped inspection after three empty waits and all
settlement obligations below still apply.

Workers use preamble `ask` for blocking questions, resume its same message after
timeout, send heartbeats only at the prescribed cadence, and check follow-ups
at natural checkpoints and immediately before completion. Send `worker_done`
exactly once with actual Task/Dispatch, explicit succeeded/failed outcome, concise
result and real artifact paths. Then end the dispatched turn. Do not hide failure
only in prose or continue using settled IDs for a later request.

Valid `worker_done` settles Task and Dispatch automatically; do not manually
complete the Task again. Settlement is separate from parent integration and
independent technical/outcome acceptance. Reject stale candidate evidence and
record the failure/next check without laundering it into a current success.

## Preserve uncertainty and settle resources

An empty wait, unchanged output, heartbeat, idle pane or contact loss is not
completion or exit. After three empty waits enumerate the scoped fleet and
follow its observed attention and literal next action; page when necessary:

```text
ORCA orchestration worker-list --run <run-id> --include-remote --json
ORCA orchestration worker-show --dispatch <dispatch-id> --json
ORCA orchestration worker-read --dispatch <dispatch-id> --limit 50 --json
```

Fleet liveness describes the agent; PTY liveness may only describe its shell.
When a fleet result names a client observation gap, execution-host positive
evidence can be more informative. Neither absent source establishes exit. Preserve
live/unverifiable/exited distinctions. After positive exit or an explicit failed
attempt, use the current `recovery-and-cleanup` contract and exact receipt before
stop, abandon or retry. A replacement names the same Task, failed Dispatch and
explicit placement. Do not evade circuit/depth limits with a fresh Run.

After accepted success/failure immediately choose exactly one: reuse a proven
terminal for an actual next Task, user-requested retain, or release. Reuse
transfers cleanup ownership and must still meet model/context/independence needs.

```text
ORCA orchestration worker-release --dispatch <settled-dispatch-id> --json
ORCA orchestration check --ack <delivery-id> --json
ORCA orchestration worker-list --run <run-id> --terminal-state reclaimable --json
```

End supervision only after expected attempts have outcomes and the reclaimable
set is empty. Uncertain release follows its exact recovery receipt, not terminal
close or broad process killing. For a lost mutation response, inspect its request
identity and replay only the same supported `--retry-request`; never duplicate a
writer on silence. Destructive reset needs explicit abandonment authorization.

`runtime_access_denied` is an access problem, not an app-not-running signal. Do
not open/restart Orca for it. Use only permission recovery allowed by the host;
the source skill's escalation wording cannot grant unavailable permission.

Original kernel and the three selected conditional references are kept under
`upstream/` only for source comparison. Read them when relevant to a discrepancy;
do not inject all of them into every worker. New remote/legacy/topology behavior
requires its current host-provided conditional reference and matching evidence.
