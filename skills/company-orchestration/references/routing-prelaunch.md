# Routing prelaunch prototype

`record_check.py routing-check` applies the fresh prelaunch check. Historical
records remain readable through `check` and the historical case suite; their
successful validation does not certify a past prelaunch check.

A fresh ordinary decision supplies `binding.inventory_evidence` and a
`selected_runtime` row. Explicit comparison also supplies `price_selection`;
its legacy inventory reference may be retained and must agree with the common
reference when both are present. Comparison inventory evidence includes
`candidate_inventory`, a list of route, family, model and effort objects.
Legacy real evidence pins the current host's
canonical Codex home's `models_cache.json`. The explicit
[host-catalog opt-in](host-model-catalog.md) instead pins fresh exact-worktree
metadata for local Orca 1.4.245, 1.4.261, 1.4.263 or 1.4.268 through the
same checker and checked launcher. It uses the host catalog independently of the
shared cache. On 1.4.268 it requires the verified saved worktree catalog and
matching semantic settings observations. For an explicit comparison of an unpinned Codex selection, the checker
independently intersects its models and supported efforts with the packaged
table and requires each non-excluded known model at the selected effort and
every known pair that dominates the selection on the benchmark prior in the
candidate list. It does not infer that those models are authenticated, have the
necessary tools or are adequate. The file's freshness and provenance are
supplied evidence, not independently certified by this check. The evidence must
provide timezone-aware `observed_at` and `valid_until`; expired bounds fail.
A quality exclusion requires a task- and
candidate-bound `task_failure` with a separate support reference; unknown
quality does not justify exclusion. An unavailable runtime candidate needs a
candidate entry in its host evidence's `unavailable_candidates` list.
Benchmark scores and prices are directional priors, not actual task outcomes or
charges. A candidate dominated on score and cost is rejected; a nondominated
choice is allowed. A fresh user pin binds task, scope, revision, attempt and
the selected pair. A real pin requires human evidence and host support evidence.

For an explicit comparison with an unlisted non-Codex selection, the inventory must include all available,
non-excluded Codex model/effort pairs with table priors; those pairs retain the
same quality and runtime-exclusion rules. The unlisted candidate requires the
separate current host, model, support, authentication, tool, billing and exact
task-fit bindings in [the record contract](record-contract.md#price-informed-selection).
The pinned inventory and the unlisted runtime must declare the same host; model
and effort must appear together in one of the contract's supported catalog
shapes. Unknown shapes do not establish support. These checks do not authenticate
the host labels or raw source origin.
Its price and benchmark comparison are unknown, so selecting it is a reasoned
operator decision. Checked launch supports Codex and the subscription AGY path below.

`routing_launch.py` supports new Codex and subscription AGY workers and evidence-bound Codex reuse. All new
checked launches also require an exact [storage enrollment](storage-lifecycle.md)
request pin before result lock/state, reprepare/catalog/measurement allocations.
Use `--enrollment-request PATH --expect-enrollment-sha256 SHA`; missing or changed
Run/owner/record/session bindings stop before host probes or writes. This is a
Company checked entry, not server-wide raw Orca interception. It requires the current
record, a decision whose binding contains the SHA-256 of the exact UTF-8
`--spec`, and unused prelaunch and host-result receipt paths. It checks before writing the receipt and
invoking `orca orchestration worker-start`, using only the checked model and
effort. An optional `--parent` must match `binding.parent_task` in the decision.
The host result retains the original stdout, stderr and exit status,
bound to the prelaunch receipt; actual Task and Dispatch IDs are host output.
Missing IDs or effective settings leave the readback unverified, and different
effective settings fail it even if the host exits zero. Preserve the host result
and inspect its resource effects before any recovery; never retry automatically.
When a concise response lacks effective settings, the launcher may read the same
Dispatch with `worker-show --full`; it requires matching Run, Task, Dispatch and
effective settings. Original start and full-readback output are retained together.
Missing, failed or conflicting readback does not authorize another start.
For reuse, supply the original launch receipt, its dispatch and terminal. The
decision binds the original hash and a pinned host observation that settings
were unchanged, including `observed_at` and `valid_until` UTC timestamps. The
launcher verifies those bounds as part of the supplied historical evidence. It
compares the original `launch.effective` pair with the selection and checks the
origin Run, Task, Dispatch, runtime, terminal, PTY and incarnation against the
live worker. A contradictory stored setting or an uncertain origin blocks the
start. The launcher retains a failed origin probe in the `not_started` result.

After the start, the launcher checks the new Task and Dispatch against the same
Run and process in a fresh `worker-show --full` response with a reused terminal
effect. On the supported Orca terminal path, this response projects stored
`startOptions.launch` alongside live process evidence. It provides no current
model or effort observation for the reused process. The receipt records the
original pair as `prior_launch_effective` and the result records both current
values as null in `reuse_settings`. An echoed model or effort without a current
observation contract leaves the start unresolved, including when it matches the
selected pair. A conflicting value fails readback. The preserved result gives
the owner the evidence for reconciliation. The launcher never starts a
replacement automatically. Orca owns Task and Dispatch lifecycle and recovery.

For a precreated Task, use `--task <id> --run <id>` instead of `--spec`.
The record's `run` and decision's `binding.run` must equal that Run, and
`binding.task`, `binding.parent_task` and `binding.spec_sha256` must match the
current host Task and its exact UTF-8 specification. A first dispatch uses a
planned binding and a current record attempt `planned:<id>`. A retry additionally
uses `--retry-of <dispatch>`; the record must bind that settled failed attempt,
and the current host Task, latest Dispatch and worker observation must agree.
Read-only host checks precede the single worker-start call. Pass placement again. The launcher selects one executable using
`--orca`, then `ORCA_CLI_COMMAND`, then the existing development/platform
default; the value is a single executable, not shell syntax. All probes and the
launch use that same selection. This does not authenticate the host.

The checked launcher holds the enrolled Run lifecycle lock through host start
and readback. For the same bound Task and attempt, a prior pending, unknown or
observed result, or an existing launch receipt, blocks a start even with new
result and receipt paths. Preserve the original artifacts and reconcile
unavailable or damaged state before deciding how to proceed. Another Run and
unchecked host entrypoints fall outside this local guard. Orca's original-request
lookup describes a single recorded mutation. Host reservations, global duplicate
prevention, provider completion and definitive absence of a start each require
their own evidence.

An explicit Run on a new-spec launch also requires the record and decision Run
binding; it does not change the coordinator's session binding. The resulting
host receipt must identify that Run and, for an existing Task, the same Task
and a different retry Dispatch. Missing identities are unverified; mismatches
fail. All host output and effects remain in the result receipt.

For a recorded decision with inventory evidence, record checking uses the
archived, hash-pinned inventory and prelaunch receipt to recheck the selected
pair and its comparison. It verifies the receipt's scope, revision, exact
specification hash, selected pair, table and comparison. It does not require
the old inventory still to be fresh, or claim a new launch is authorized.
Historical records without inventory evidence retain their previous check.

`routing_hook.py` is an opt-in Codex PreToolUse adapter. Its
`bind --session ... --decision ... --record ... --receipt-dir ...` creates
exclusive session metadata under the Company state directory. The optional
`COMPANY_ROUTING_SCOPE` environment variable can point to equivalent JSON.
Each contains the session ID, decision and record paths, and receipt directory.
An existing binding can be replaced only with its exact prior SHA-256 via
`--expected-sha256`. Unrelated
sessions and unrecognized tools are unchanged. For recognized raw Orca
worker-start commands it checks the decision and denies the direct command,
requiring the checked launcher. It checks recognized native `spawn_agent`
calls against an existing current parent Task and Dispatch, the selected model,
effort and exact message hash and writes a
receipt keyed by the tool-use ID; that ID is not an Orca Task ID.
If a recognized action has no routing binding, an independently registered
Company completion session is denied rather than silently treated as unrelated.
Run success or failure does not end the Company session. On explicit user exit,
run `routing_hook.py exit --session <exact-host-session-id>`; if a routing binding
already exists, supply its exact current SHA-256 with `--expected-sha256`. The
exit marker is session-bound and does not alter the completion registration or
erase its evidence. A later Company entry replaces it through `bind` with the
marker hash. Missing completion registration cannot prove that a session is not
Company. A recognized targeted worker `send` is denied within this scope because
a settled target can create a new Task without an atomic active-state condition;
coordinator Run messages and the distinct ask/reply/worker_done paths remain.
On the supported local host, a targeted send can reuse a live terminal, reopen
a conversation or start with saved requested preferences after settlement.
Those preferences cannot supply current model or effort evidence.
For an authorized new contribution after worker completion, use a checked
`--spec` launch in the same Run with the retained evidence and explicit parent.
If the contribution requires a confirmed new launch setting, select a supported
fresh worker and verify its actual launch readback.
Preserve failed or unknown attempts; a new Task is not a substitute for an
unverified retry. The hook does not intercept unsupported shell or host paths.

The source installer has a separately owned registration and rollback entry;
source definition and tests do not prove installed registration, trusted load
or actual coverage.
Hooks do not intercept `write_stdin` again, hidden scripts, unsupported tool
paths, unloaded hooks or other providers. Shell recognition is intentionally
limited to recognized shell command segments and literal JSON-style `cmd`
strings in `functions.exec`; it is not an OS or server enforcement boundary.
Do not activate the
adapter before independent review and verified transactional installation.
The installer registers the canonical home. Each separate execution home needs
its own verified supported hook registration and fresh trust/load observation;
canonical registration alone does not prove that runtime home is protected.
The existing `scripts/repair_runtime_hook.py --runtime-home <path>` plans the
shared-home registration and preserves unrelated hooks. Its `--apply` mode uses
the transaction and verifies the fresh target hook list; it requires the
canonical commands to be enabled and trusted first. It does not prove that a
previously running Codex session loaded the new hook.

## Explicit one-time inventory reprepare

Raw inventory SHA-256 remains mandatory. A byte change alone never proves that
selection evidence is equivalent. Default launch still denies any hash drift.
For a **new, non-measurement `--spec` launch only**, the operator may explicitly
supply `--reprepare-inventory /private/preparation-inventory.json`. At preparation,
copy the complete canonical cache bytes into that private snapshot and bind the
decision's inventory SHA-256 to those exact bytes. Do not rebuild a snapshot from
model names or candidate projections. Keep the original decision and failed
attempts unchanged. Missing old bytes means the historical semantic delta is
unknown, not harmless; this option cannot repair such an old decision.

This opt-in is deliberately narrower than arbitrary cache refresh:

- An exclusive, unused result/receipt pair is required. The current launcher must
  own its result lock and prove `not_started` before any host call. Existing
  results (including a previous `not_started` denial), pending/unknown outcomes,
  Task retries, terminal reuse and measurement lifecycles are not accepted by
  this path. A new filename does not establish absence of an earlier host start;
  reconcile any earlier attempt authoritatively before preparing new work.
- Only the precise inventory-hash denial is eligible. The saved full snapshot
  must match the original pin. Apart from `fetched_at`, **every JSON value** must
  remain identical, including complete model objects, unknown fields, efforts,
  capability, pricing and availability metadata, etag, client version and
  identity. Changed candidates or unknown shapes require review; there is no
  model/effort-only semantic hash or discarded-field allowlist.
- `fetched_at` is not ignored: both timestamps must be timezone-aware, the new
  timestamp cannot regress or be future-dated, and it must lie within the
  original evidence observation/validity bounds. Current time must still be
  within those bounds. Reprepare never extends freshness or fabricates a new
  observation window. The local clock and supplied source are not authenticated.
- The launcher makes a new decision bound to the current raw bytes, recomputes
  profile binding and the complete existing price/routing checks, and rejects
  changed selection or any other denial. All ordinary spec, resource, permission
  and host readback gates remain. Immediately before the sole host start, it
  revalidates again; a second drift stops, never loops or falls back.
- `<result>.reprepare/` retains the complete old/current inventory bytes, original
  and refreshed decision objects, original/effective hashes, rejected check and
  current check. The prelaunch receipt binds that provenance. No old approval,
  decision, cache or denied result is rewritten. After a timeout, pending or
  unknown outcome, preserve this evidence and reconcile; never repeat under a
  fresh filename to escape the guard.

For a previously denied attempt, first retain its exact result and authoritative
host readback proving no dispatch/start. Prepare a separately authorized fresh
attempt from current evidence, with new paths and a full preparation snapshot;
compare its complete candidate set, selection and profile binding for review.
If selection or any material condition changed, stop for that review. Invoke the
**reviewed candidate source** `scripts/routing_launch.py` with the ordinary
checked-launch arguments plus the opt-in above; do not install or call raw
`worker-start` as a workaround. Preserve the snapshot and all refreshed receipts
for independent acceptance. Source/fake-host tests are not a real worker launch.

## Measurement-required launches

The checked launcher validates the explicit `measurement.mode: "required"`
record using the [measurement contract](record-contract.md#measurement-required-comparisons).
Version 1 rejects these launches with `measurement_future_unbound`, even
when existing participants' samples pass: a newly launched or reused worker's
future turn and its actual usage cannot yet be observed and bound before
`worker-start`. A planned resolver is not an observation. Keep the comparison
blocked until a supported way to bind that future turn is independently
verified; do not infer success from an earlier turn in the same session.
The rejection happens before worker-start, receipt creation, or host probes.
Direct raw Orca launches and other routes are outside this checked launcher;
this is not server-wide enforcement and does not implement a hard token cap.

Explicit version 2 uses the [prepared lifecycle](measurement-lifecycle.md):
proven capture readiness, a frozen attempt roster, durable pending before launch,
then exact host/source binding and separate final settlement. This is conditional
local-terminal support, not an unconditional allow. Unsupported/missing host
identity, Hermes/structured/resumed sources, unknown starts and v1 launches stay
blocked. Add `--measurement-attempt` to the ordinary checked launcher; no existing
pin/resource/model/permission gate is bypassed.

### Optional resource declaration and capacity requirement

`routing_launch.py --require-resource-manifest --resource-manifest PATH` requires
`--declared-host HOST`, one or more `--declared-tool TOOL`, and
`--declared-billing subscription|paid_api`; paid API also requires a finite
`--declared-spend` within the declared ceiling. Model, effort and service come
from the checked decision, not these flags. The local gate runs before any host
probe or start. Without a manifest the ordinary route retains `unknown`; a
supplied invalid declaration denies. A matching declaration is `declared_ready`,
not authenticated host identity, actual account status, quota, approval, tools,
billing or spend enforcement. The local clock is not trusted time. Future usage
cannot be established before invocation.

`--require-trusted-capacity` denies before host probes: no trusted issuer,
authenticated clock, or reservation contract exists. Ordinary routes are not
changed by that opt-in. `scripts/agent_company_plan_delegation.py` calls
`route_model` through `_routed_decisions` to produce plan projections; its
capacity input is structural, not an authenticated reservation and is not a
host launch authorization. Direct host calls are outside this checked launcher.

## Profile preparation and decision binding

### Read-only reviewed DAG preview

`scripts/routing_prepare.py preview --request REQUEST.json
--expect-request-sha256 SHA256` projects an already reviewed full profile DAG
into sorted per-unit `ready`/`blocked` rows. It writes nothing, reserves no
storage/capacity, performs no host/provider calls, and always returns
`launch_authorized=false`. Existing `prepare`/`check` bundle formats and native
reasoning callers are unchanged. A blocked unit does not erase independent
ready rows; exit 1 means at least one unit or global input is blocked, exit 0
means every row is ready. Malformed/global stale inputs return missing-field
diagnostics without a partial readiness claim.

The strict request has these fields, with each file reference shaped exactly
as `{"path":"/physical/path/file", "sha256":"<lowercase-byte-hash>"}`:

```json
{
  "schema": "company-routing-preview-request/v1",
  "record": {"path": "/physical/run/record.json", "sha256": "<hash>"},
  "profile": {"path": "/physical/profile.json", "sha256": "<hash>"},
  "enrollment": {"path": "/physical/enrollment.json", "sha256": "<hash>"},
  "context": {"path": "/physical/context.json", "sha256": "<hash>"},
  "worktree": "id:repo-id::/physical/workspace",
  "units": [
    {"id": "one", "decision": {"path": "/physical/decision.json", "sha256": "<hash>"},
     "spec_file": {"path": "/physical/spec.txt", "sha256": "<hash>"}, "writers": ["source-area"]}
  ]
}
```

The record must be the existing enrolled canonical path for an active goal with
accepted owner/scope/revision. The profile uses the existing strict version 1
schema and contains the entire DAG; duplicate/cyclic/dangling or uncertain
profiles deny. Supply exactly one input row per profile unit. Each original
decision must already contain its full profile binding, selected identity,
authority, authentication, tools, billing, current local catalog and semantic
observations. It must be planned, bound to that unit and enrollment Run, and
use the Codex subscription path. Preview never fills those fields or selects a replacement. Every
row repeats the existing current prelaunch checker. Inadequate context/table
capabilities or missing provenance remain blocked.

The strict context has `schema=company-routing-preview-context/v1`, `binding`,
`observed_at`, `valid_until`, `units`, `writers`, `capacity`, `evidence`.
`binding` must equal the current `run`, `scope`, `revision`, `owner`, `worktree`,
`record_sha256` and exact profile file's `profile_sha256`. Both timestamps must
be timezone-aware ISO values bracketing the current check. `evidence` uses the
existing checker evidence map; every entry requires kind `host`, a file and its
exact hash. Every observation below requires an existing evidence key:

```json
{
  "units": {"one": {"task": null, "evidence": "current-task-observation"}},
  "writers": {"source-area": {"task": null, "evidence": "current-writer-observation"}},
  "capacity": {"available": 1, "evidence": "current-capacity-observation"}
}
```

These are caller-supplied review assertions with pinned original provenance;
hashes and `kind=host` do not authenticate origin, resource freedom or host
completeness. `task=null` explicitly asserts an observed unstarted unit/free
writer; absence of evidence is never a free slot. Preserve pending/unknown
attempts with a non-null task marker and reconcile the originals. Preview does
not infer readiness from an absent row or retry an unknown attempt.

For dependencies, `units` maps the predecessor to an existing canonical Task.
It must be the same ID as the profile unit or have the existing validated
historical profile/Task mapping. Settled successful execution, independent
technical acceptance and parent integration must all pass. A ready predecessor
alone never releases its child. Writers are explicit shared resource keys; all
otherwise-ready units with overlapping keys block, without choosing a winner.
Missing/busy writer evidence blocks. Insufficient evidenced capacity blocks the
ready wave rather than assigning an arbitrary order. An empty writer list is an
explicit assertion that this unit takes no mutable shared resource.

Output retains the exact spec text, byte count and original path/hash (including
leading spaces, CR/LF and every terminal LF), rebased decision/patch, existing
checker result, original checked-input references, and observed accepted host
dependency IDs. UTF-8 must be valid, nonempty and NUL-free. All source/input,
configuration, enrollment and context validity pins are rechecked at the end.
Keep stdout as private review evidence using the caller's existing enrolled
artifact procedure if retaining it; preview creates no second persistent state.

Pass reviewed rows through existing enrolled `prepare`/`check`, then current
checked launch. Orca task-create supports `--deps` and `--spec-file`, but planned
unit IDs are not actual Orca Task IDs; the preview only exposes observed IDs.
Use checked launch `--spec-file PATH` to read those bytes without shell
substitution. The launcher submits the same decoded text after its ordinary spec
hash and authority checks. Recheck actual state and all launch gates immediately
before each start. A preview does not reserve capacity or authorize a start.

Use the existing Company conversation to propose the versioned unit DAG and profiles.
Validate unknowns rather than guessing. From the skill directory run:

```sh
python3 -B scripts/record_check.py profile-validate assets/worker-profile-example.json
python3 -B scripts/record_check.py profile-prepare profile.json --unit one --table external-table.json
```

The first emits `{"ok": true, "status": "valid"}`. The second emits an
`ok` flag, `profile_binding`, and `limits`; copy exactly the emitted
`profile_binding` into the existing routing decision under that name. The unit
id must equal the decision binding task. The binding embeds validated profile,
table and pins snapshots, selected route/model/effort, and canonical JSON SHA256
digests for profile, table, priors and pins. External table snapshots are
supported. Changes to the original external file after preparation do not alter
the embedded snapshot; prepare again to incorporate them. For an explicit
current-task pin, pass `--pins pins.json`, a map from that unit id to its exact
route/model/effort; the existing evidence-bound user-pin checks still apply.

The packaged default table now has all ten families at three difficulties; the
general example returns MATCH. See [routing evidence](worker-routing-evidence.md)
for every policy order, successor alias, capability assertion and pilot limit.
Media-generation rows are disabled. Named tools and positive context requirements
remain unasserted and return NO_MATCH without a suitable external table. Table
evidence is an editorial assertion plus narrow smoke observations, not host or
universal quality proof. A proposal is not an
authorization: complete the normal decision, selected runtime, host, task, authority and
prelaunch checks (plus price checks when comparison is requested); disagreement denies launch, without automatic runtime fallback.
Fresh execution checks require a valid `profile_binding`; historical record reads
remain readable without retroactively certifying the old execution. External tables
may represent supported non-Codex routes and an observed native effort or null
when there is no effort knob. A table is an untrusted proposal, not evidence of
host support or launch authority; the existing unlisted route checks still apply.

### Starting an ordinary AGY selection

For visual/hard, tool_use/medium and tool_use/hard the packaged primary is
respectively `gemini-4-neon-high`, `gemini-4-hydrogen-medium` and
`gemini-4-hydrogen-high`. Keep the full catalog model ID, including its effort
suffix, in the profile, decision and evidence. Supply the matching separate
effort. Use `ordinary_assignment` for an ordinary proposal. No user pin or
price comparison is needed.

Use the normal checked launch with an enabled Antigravity service and a
`selected_runtime` row with subscription billing. Supply the canonical local
inventory plus the AGY model catalog and the pinned, fresh support, authentication,
tools and billing observations required by the unlisted-runtime contract. Use
the local Orca runtime ID from `orca status --json` as their common host. A
supplied resource manifest names the service `antigravity` and the same host.
The launcher verifies the runtime before sending `worker-start --agent antigravity
--model <exact-id> --effort <effort> --full --json`. It checks the returned runtime,
Task, Dispatch and effective agent/model/effort. Unknown or conflicting readback
requires reconciliation. Codex-specific catalog refresh, inventory reprepare,
terminal reuse and measurement bridges remain unavailable for AGY.

On a Codex-only host, inspect the profile's `eligible_chain`. The first Codex
alternatives for those three rows are respectively Sol/high, Terra/medium and
Sol/high. For a standing Codex-only policy, retain the full source table, create
a separate table with unavailable routes disabled, and configure its absolute
path and byte hash using [worker table configuration](configuration.md#configured-worker-routing-table).
Run `record_check.py profile-prepare PROFILE --unit UNIT` under that configuration.
Alternatively, a genuine current-task user pin can explicitly select an eligible
identity via `--pins PINS`. Prepare a fresh decision, runtime and inventory
for the proposed Codex identity and pass the normal prelaunch checks. An old
AGY pin, exhausted chain or missing replacement evidence blocks execution.

### In-flight decisions across the routing table update

Keep each original decision, table, priors, configuration, prelaunch and host
receipt with the package revision that produced it. For historical replay use
that retained revision and evidence. The current checker recomputes the profile
and priors digest and can reject a valid older binding after a policy change.
For a confirmed unstarted unit, prepare a separate decision against the current
configured table and bind the exact selected identity and current evidence.
For a live Dispatch, finish and reconcile it under its original bindings. For
a pending invocation or unknown host result, reconcile the original Task and
Dispatch before considering another launch. Preserve earlier receipts byte for
byte, including refusals. A new preparation cannot certify or relabel earlier work.

A fresh spec launch can have a planned profile unit different from the actual
host-issued Task ID. Keep the original profile binding unchanged. A later record
must reference a pinned original prelaunch receipt and observed original launch
result with exact profile digest/unit, scope, revision, spec, selected identity,
Run, actual Task and Dispatch bindings. Missing or mismatched evidence refuses
the mapping. Historical validation never infers a successful start from an
operator-written mapping, and a pinned file does not authenticate its origin.

### Local backups and shared final default (table v2)

Each row has one primary and **at most two backups** (one to three local
candidates). Sort by ascending `priority`, preserving listed order on ties;
indices 0, 1 and 2 never renumber after filtering. Empty rows, three backups
and duplicate model names (even at different efforts) are rejected.
The separate required top-level `common_default` is codex/gpt-6.1-terra with
explicit effort, enabled state, modalities, capabilities, tools, context,
constraints and evidence. It is not a row candidate or fallback index 3.

Preparation checks local candidates first. Only when an existing row has no
eligible local candidate does it consult the common default. Missing rows stay
NO_MATCH. If the default's route/model already occurred locally, skip it even
if its effort or capability assertions differ: an ineligible Terra is not
revived through the shared entry. Otherwise apply exactly the same enabled,
input AND output modality, capability, tool, constraint, context and exact-pin
filters. An incompatible default is NO_MATCH; unsupported media generation
cannot escape through it. The packaged default uses medium effort explicitly;
it does not silently inherit a row's effort. Original general primaries remain.

`worker_route.py prepare` emits proposal version 2. `eligible_chain` contains
only eligible **local** entries. `selected_source` is `local`, `common_default`,
or null; a default selection has null `fallback_index`, not index 3.
`selection_reasons` contains earlier local rejections (all local rejections for
a default selection). `default_provenance` always exposes configured identity,
evidence, `consulted`, `selected` and reasons. Consulted means the last-resort
branch was reached, including a duplicate skip; it never means a model call.
No local match plus no acceptable default yields NO_MATCH and null selection.
Exact pins still forbid substitution, including changing effort.

`record_check.py profile-prepare` emits binding version 3 with this provenance
and chain. The checker recomputes all fields and hashes from embedded snapshots;
changing consultation, selection, evidence, source or ordering denies launch.
Compatibility is intentionally fail-closed: table v1 and profile bindings v1/v2
must be explicitly migrated/reprepared; the old four-local-candidate shape is
not silently truncated or interpreted as the new shared-default contract.
An execution check without `profile_binding` fails; historical record reads do
not add that requirement retroactively.

This is **prelaunch eligibility selection, not runtime retry/failover**.
`routing_launch.py` starts only the one checked selected identity, once. It
persists invocation_pending before the subprocess and unknown after timeout or
unverified readback; an existing pending/unknown result refuses another start
until reconciliation. It neither traverses this chain nor consults Terra on a
runtime error. A separately requested `--retry-of` requires a settled failed
record and matching failed/latest host Dispatch evidence plus a new checked
decision; this change adds no retry authority or provider failover.
Price, host support, human pin, task and launch gates remain unchanged. The
measurement-required I05 gate stays closed; no future usage, entitlement or
model quality is established by this contract.

## Execution table authority

`profile-prepare` without `--table` uses the independently resolved configured
worker table. An explicit `--table` prepares a proposal only; it grants no fresh
execution authority. At prelaunch the embedded profile table must match the
current configured table. The default is the packaged canonical table; a pinned
external table must be explicitly configured under the normal configuration
precedence described in [configuration](configuration.md#configured-worker-routing-table).
The table is rechecked immediately before worker start; changed bytes, a missing
source, or a configuration mismatch denies that start. Historical read does not
substitute today's table for the original, while current readiness is checked
against current configuration. External-table authorization does not authenticate
its author or prove provider capability.
