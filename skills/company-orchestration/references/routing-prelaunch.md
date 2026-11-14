# Routing prelaunch prototype

`record_check.py routing-check` applies the fresh prelaunch check. Historical
records remain readable through `check` and the historical case suite; their
successful validation does not certify a past prelaunch check.

An unpinned fresh decision, and an unlisted non-Codex selection even if pinned,
supplies `price_selection.inventory_evidence`. The
referenced host evidence includes `candidate_inventory`, a list of route,
family, model and effort objects. Legacy real evidence pins the current host's
canonical Codex home's `models_cache.json`. The explicit
[host-catalog opt-in](host-model-catalog.md) instead pins fresh exact-worktree
metadata and semantic settings observations for local Orca 1.4.245, through the
same checker and checked launcher; it does not depend on that shared cache. For an unpinned Codex selection, the checker
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

For an unlisted non-Codex selection, the inventory must include all available,
non-excluded Codex model/effort pairs with table priors; those pairs retain the
same quality and runtime-exclusion rules. The unlisted candidate requires the
separate current host, model, support, authentication, tool, billing and exact
task-fit bindings in [the record contract](record-contract.md#price-informed-selection).
The pinned inventory and the unlisted runtime must declare the same host; model
and effort must appear together in one of the contract's supported catalog
shapes. Unknown shapes do not establish support. These checks do not authenticate
the host labels or raw source origin.
Its price and benchmark comparison are unknown, so selecting it is a reasoned
operator decision rather than a price or dominance result. The existing checked
launcher remains Codex-only; use an actually supported Orca path for other agents.

`routing_launch.py` supports new Codex workers and evidence-bound reuse. It requires the current
record, a decision whose binding contains the SHA-256 of the exact UTF-8
`--spec`, and unused prelaunch and host-result receipt paths. It checks before writing the receipt and
invoking `orca orchestration worker-start`, using only the checked model and
effort. An optional `--parent` must match `binding.parent_task` in the decision.
The host result retains the original stdout, stderr and exit status,
bound to the prelaunch receipt; actual Task and Dispatch IDs are host output.
Missing IDs or effective settings leave the readback unverified, and different
effective settings fail it even if the host exits zero. Preserve the host result
and inspect its resource effects before any recovery; never retry automatically.
For reuse, supply the original launch receipt, its dispatch and terminal. The
decision binds the original hash and a pinned host observation that settings
were unchanged, including `observed_at` and `valid_until` UTC timestamps. The
launcher checks those supplied bounds; it cannot independently prove that the
settings stayed unchanged. It compares the original `launch.effective` model
and effort with the selected pair, plus a current `worker-show`, live agent
projection and the same terminal incarnation. This is not a fresh provider
model/effort readback.
Unknown or changed evidence denies reuse without starting a replacement. Orca
still owns Task and Dispatch lifecycle and recovery.

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

The exclusive result path serializes only callers sharing that path. Before the
worker-start subprocess the launcher flushes an `invocation_pending` state;
any pending, damaged or unknown result requires reconciliation and must not be
retried merely because no success was recorded. An observed result records
bound host readback, not provider verification. No authoritative absence query,
idempotency contract or host-wide reservation is established by this local file.
Using a different result path or an unchecked host entrypoint is not protected.

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
authorization: complete the normal decision, price, host, task, authority and
prelaunch checks; disagreement denies launch, without automatic runtime fallback. Older decisions
without profile_binding retain their existing path.

### Local backups and shared final default (table v2)

Each row has one primary and **at most two backups** (one to three local
candidates). Sort by ascending `priority`, then `(route, model, effort)`;
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
Decisions without profile_binding retain their existing path.

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
