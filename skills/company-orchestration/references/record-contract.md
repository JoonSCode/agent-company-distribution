# Portable orchestration supplement, version 1

This record is a **claim ledger**, referencing the existing accepted plan and
Orca receipts. It is not a Company schema replacement, scheduler, authority store,
or runtime adapter. Checks detect recorded contradictions; they cannot authenticate
self-authored receipts, verify acceptance happened, establish independent judgment,
authorize retries/writers, or prove actual user success. No English sentence is
interpreted as a semantic proof. Preserve the original receipts and their provenance.

Run with Python 3.9+ and its standard library, from any folder (no installation):

```sh
python3 /path/to/company-orchestration/scripts/record_check.py check record.json --json
python3 /path/to/company-orchestration/scripts/record_check.py check record.json --require-routing --json
python3 /path/to/company-orchestration/scripts/record_check.py cases /path/to/company-orchestration/assets/record-cases.json --json
python3 /path/to/company-orchestration/scripts/record_check.py routing-check decision.json --json
python3 /path/to/company-orchestration/scripts/record_check.py routing-check decision.json --record record.json --json
python3 /path/to/company-orchestration/scripts/record_check.py routing-cases /path/to/company-orchestration/assets/routing-cases.json --json
```

`--json` can precede the command too. Exit 0: recorded checks pass (for `cases`,
all expected error-code sets match). Exit 1: inconsistent/malformed record or failed
case suite. Exit 2: unreadable/invalid JSON or invalid CLI arguments (argparse usage
errors use stderr). JSON input errors return structured `{ok:false, errors:[...]}`;
record errors have `path`, `code`, and `message`. JSON duplicate fields and non-JSON
NaN/Infinity are rejected. Human output is brief; JSON includes usage subtotals.

## Historical integrity versus current readiness

`check` also emits fresh `historical_integrity` and `current_readiness` diagnostics.
Both are scoped to **recorded host-catalog inputs**, not the validity or success of
an entire historical Run. Historical `valid` means supplied pinned catalog/raw
response and checked-prelaunch receipt bytes agree on selection, specification,
configuration hash, runtime and worktree. It reuses the catalog validator at its
recorded capture time without consulting today's configuration, observed external
files or semantic settings DB. Missing files, bare references/pins, absent receipts
or unsupported legacy history remain `unknown`; malformed bytes, hash or binding
mismatches are `invalid`. No missing history is manufactured or upgraded.

Current `ready` means only the bounded local catalog inputs pass the existing
current resolver/observations/freshness checks and legacy record checks. It does
not authenticate a provider or host, prove tools/billing, or replace the final
checked launcher. No recorded catalog gives `unknown`; a current/legacy denial
is `blocked`. Current time expiry can block readiness even while old record
consistency still passes. Every diagnostic says `launch_authorized:false`.
Historical effective configuration/authentication and provenance remain unproven.
These are sequential observations, not an atomic snapshot against writers.

Existing `ok`, error codes, token totals and exit behavior are unchanged. In
particular, an unchanged T0 record can still fail the legacy check after a T1
configuration or auth-policy edit. This change explains that safe refusal rather
than accepting history automatically. Status JSON/HTML shows both fresh reports;
success badges still use the old consistency/acceptance checks. Completion retains
all its existing gates and adds optional `record_validation` diagnostics to new
receipts only after record acceptance. Old completion receipts without that field
remain readable; cached or forged reports never bypass acceptance. Supply trusted
explicit evidence paths; this is not an archive importer or a launch/retry command.

## Shape

`assets/record-cases.json` supplies full **synthetic** examples, positive and
negative. Extract a case's `record` object for `check`. No example is live evidence.
A case suite has `version:1`, `label:"synthetic"`, and `cases` of `{name, record,
expected_errors:[error_code,...]}`. Cases match exact sets of error codes, including
an empty set for valid unknown/pending records.

A record has these required fields. Additional fields are annotations only; the
checker ignores them and they cannot supply missing checked facts.

| Field | Required expression |
|---|---|
| `version`, `label` | integer `1`; `synthetic` or `real` (real means intended real-world claims, not authenticated) |
| `evidence` | ID-to-object map; each object has `ref` (stable nonempty reference), `sha256` (lowercase 64-digit hash or null), `kind` (`synthetic`, `human`, `independent`, `host`, `source`, `provider`) |
| `goal` | `id`, `revision`, `scope`, `plan` evidence ID, `status` (`pending`, `active`, `failed`, `succeeded`), boolean `known_failure`, `assessment` or null, `current_owner` string or null, `owner_acceptance` (`pending`, `accepted`) |
| `ownership` | ordered events `{revision, scope, from, to, status, accepted_by, evidence}` |
| `tasks` | current-scope task records described below; empty is valid |
| `usage` | `{coverage, expected, entries}` described below |

Synthetic records require every evidence object's kind to be `synthetic`.
Evidence references resolve to IDs in the map. `file` is optional on an evidence
object: if supplied, the checker reads it relative to the **input JSON's directory**
(absolute paths also work), requires `sha256`, and verifies actual bytes. Missing,
unreadable, or mismatched files fail. Without `file`, a hash is just a recorded pin,
not content verification. This explicit file access is read-only; supply trusted
paths. No network reference is fetched. Plans, host receipts and model observations
remain external records; do not copy a second execution database here.

## Goal and ownership

An assessment is `{revision, scope, verdict, basis, actor, evidence}` bound to
the current revision/scope: verdict is `pending`, `failed`, or
`succeeded`; basis is `human`, `independent`, or `team_checks`. Overall success
requires a recorded human/independent success assessment; an independent assessor
must differ from the goal owner. Known overall failure
or a failed overall assessment cannot become success because task/team checks
passed. A passed checker means these *claims* are consistent, not that the
assessment, meaning, or user outcome has been independently observed.

Ownership status is `proposed` or `accepted`. `from` is null only for the very
first acceptance of the overall goal; `to` identifies the owner. Each accepted
event requires an evidence ID and `accepted_by == to`, and must transition from
the **last accepted owner across all revisions/scopes**. Invalid events do not
advance the chain. Proposals do not transfer responsibility: A→B accepted on
revision 2 and B→C proposed on revision 3 leaves B responsible for continuity.

`current_owner` expresses that continuing responsibility and must equal the last
accepted owner, even when a material revision is pending. `owner_acceptance`
separately says whether the latest valid acceptance is bound to the goal's exact
current revision/scope. It is `pending` for an unaccepted material revision and
`accepted` only after the successor (including the same owner) explicitly accepts
that revision/scope. Continuing responsibility does not grant authority over
expanded scope: pending acceptance cannot accompany an `active` or `succeeded`
new-revision goal. Before any initial acceptance, owner is null and acceptance is
pending. An accepted revision-3 event from null cannot reset revision-2 owner B;
the transfer must be from B and bind to revision 3's scope.

Initial/successor acceptance cannot be inferred from enqueue, role, title or
presence. Routine tactics inside the same accepted scope keep the same revision,
owner and acceptance; they require no new event. Determining whether scope changed
materially, and actual authority over that scope, remain the user's/source
contract's judgments. This claim ledger does not create that authority.

## Attempt, review and parent integration

Each task requires `id`, `goal_revision`, `goal_scope`, `parent`, `current_dispatch`,
`candidate`, `execution`, `technical`, `parent_integration`, `model`, and boolean
`retry_claimed`/`another_writer_claimed`. IDs/parent/candidate are nonempty strings;
goal revision/scope match the record's current goal. Task IDs are unique. Historical
attempt receipts can be referenced in evidence; do not place them in current results.

- `execution`: `{state, actor, result}`. State is `live`, `unknown`, `exited`, or
  `settled`. Result is null until settled, then `{task, dispatch, candidate,
  evidence, outcome}` with outcome `succeeded` or `failed` and exact current bindings.
- `technical`: null or `{task, dispatch, candidate, evidence, verdict, actor}`.
  Verdict is `pending`, `passed`, or `failed`. A passed technical review must name
  an actor distinct from the executor. Use distinct stable staff identities, not
  model labels; strings cannot prove that two people/sessions are independent.
- `parent_integration`: null or the same review shape; actor must equal `parent`.
  Parent integration and independent technical acceptance are separate claims,
  and neither automatically establishes overall user success.
- `model`: `{requested, observed, effort_requested, effort_observed}`, each a
  nonempty string or null. Null means unknown; no hardcoded model/effort enum.

Unknown/live exit plus a retry/another-writer claim fails. Exited/settled state is
only a necessary recorded condition, not authorization: actual Orca process proof,
accepted settlement and host recovery rules still govern every action. The CLI
neither calls Orca nor enforces its lifecycle. It does not infer execution success
from technical acceptance or require a known model merely to validate a receipt.

## Usage without invented totals

`coverage` is `unknown`, `partial`, or `complete`. `expected` lists the complete
intended accounting universe's provenance keys: `provider/request/id` or
`provider/session/id`. The provider namespace cannot contain `/`; the ID may.
Missing/incomplete expected inventory cannot be inferred from entries alone.

Each entry requires `provider`, `tokenizer`, `kind` (`request` or `session`), `id`,
`session` (reported session provenance), `input`, `output`, `cached_input`,
`reasoning`, boolean `cached_in_input`/`reasoning_in_output`, and `evidence` ID.
Counts are nonnegative integers or null; zero is an observed zero. Session kind
requires `id == session`. Same-provider request IDs cannot repeat, and session
summaries cannot overlap request entries for that session. Multiple distinct
requests in one session are allowed. Providers/tokenizers retain separate groups.

Normalize provider reports to inclusive input/output totals before entry. Positive
cached/reasoning subcounts require their inclusion boolean and cannot exceed the
reported total. Sum input + output **once**; never add cached/reasoning again.
Unknown subcounts are allowed when inclusive totals are observed. This record does
not infer token counts from credits, prices, quotas, or subscriptions.

The CLI returns `observed_subtotals` by provider/tokenizer; null subtotal fields
mean no observed count in that dimension. Partial sums contain only supplied
observations and are not coverage estimates. `total_raw_tokens` is null unless
coverage is complete, every expected unit is represented exactly once, all
input/output counts are known, and the record has no errors. An empty inventory
does not earn a zero total. A complete cross-provider raw-token sum retains the
note that different tokenizers are not an identical measurement unit. The
expected inventory must include lead, worker, retries, context, verification and
integration usage where applicable; quality is assessed before efficiency.

## Integration boundary

Link this contract and the CLI/case invocation from the portable skill; no Core,
global SKILL.md, ultrawork install or live backend dependency is required. These
checks are deterministic preparation evidence only. Important acceptance needs
an independent reviewer and actual user-path evidence; a green synthetic suite
cannot claim worker behavior, runtime health, quality, token savings or deployment.

For optional operations only—without adding any default or always-read requirement—use
[receipt projection](record-projection.md) when projecting pinned Orca launch/done
observations into a non-accepted supplementary draft, and [saved outcome evaluation](outcome-evaluation.md)
when freezing inputs and grading saved trial outcomes for an approved study.

## Resource accounting

Fresh Company Runs require root `resource_accounting: "required"`; invoke
`record_check.py check record.json --require-resources` to catch omission.
Historical version-1 records remain readable without claiming this coverage.
Each Task then needs `resource_preflight` with nonempty `host`, `cpu`, `ram`,
`disk` observations and an `evidence` ID. An unavailable measurement must state
unknown and the failed probe; a string is recorded evidence, not a capacity proof.

`resources` is an array (empty is valid for tasks allocating no resources).
Each item records exact `host`, `key`, `kind`, `owner`, `allocation` (`reuse` or
`new`), nullable `reason`, `retention` (`durable`, `evidence`, `reusable`,
`temporary`) and `closeout`. New allocation needs a task-specific reason.
Resource host/key pairs must be unique within the Task. Cross-Task exclusive
ownership is coordinated through Orca and the resource policy, not this checker.

`closeout` is null during live work, then `{disposition, evidence, next_use}`.
Disposition is `released`, `preserved`, `deferred` or `removed`; evidence resolves
to a receipt. Preserved/deferred resources require a next consumer or recheck
condition in `next_use`. Exited/settled Tasks and final goal records need closeout.
Live/unknown execution cannot establish release/removal. Durable source and required evidence resources cannot
be marked removed: promote required contents to their durable owner first.
This consistency check grants no deletion authority, verifies no process exit by
itself, and does not implement an automatic scheduler or host launch hook.

## Routing decisions

Fresh runs get routing accountability from `run_completion.py init`, which writes
`routing_accounting: "required"` on the retention manifest. Completion then
requires a structurally valid `routing_decision` on every current task even if
the record omits `routing_accounting`. Legacy manifests without that field stay
readable and do not gain this coverage. Setting the record field, or invoking
`check --require-routing`, applies the same decision rule. A plain `check` of a
historical version-1 record without the field or a decision stays valid.
A present decision is checked either way, so omitting the record flag does not
silence a decision that was written. These checks do not intercept Orca.

Before `worker-start`, run `routing-check` and keep its JSON receipt. The
command does not launch, block, or prove it was used. A receipt evidence id is
a reference. Byte verification happens only when that evidence supplies `file`
through the existing hash pin. The embedded decision is rechecked. Do not treat
an earlier launch as if this checker had already run.

When a current supplementary record is available, pass `--record record.json`
before dispatch. The existing record validator must pass, including its evidence
file pins resolved relative to the record file. The decision's scope and revision
must exactly match the current goal. A new task absent from the record may pass
with a valid planned binding; no task membership or record mutation is required.
For a task already present, the decision must match its current dispatch and its
known requested model/effort using the embedded-decision rules. A planned token
cannot replace that current dispatch. A nonplanned task absent from the record
fails. Errors in the record appear under `$.record`; unreadable or invalid JSON
returns an input error. The receipt adds `record_sha256` for this optional input.
Decision evidence files remain relative to the decision file. Standalone calls
without `--record` keep their existing behavior and do not check current goal
binding. These checks read the supplied snapshot; they do not prove it is the
latest record at launch, grant acceptance, or change goals, tasks or dispatches.

A decision is integer version 1. `binding` has nonempty `task`, `scope`,
`revision`, `attempt`, and boolean `planned`. A planned attempt must equal
`planned:<task>`. A recorded attempt cannot still use that token. Inside a
task, the binding must match the task id, goal scope, goal revision, and
current dispatch. Null requested model or effort stays unknown and is not a
mismatch. Standalone decisions require `label`; embedded decisions may omit it.

`trigger` is `initial` or `reassignment`. `failure_class` is null or `capacity`,
`auth`, `tools`, or `quality`. Initial decisions have no prior and no failure.
Reassignment binds one prior candidate and one failure class.

Candidates use `route` (`agy`, `antigravity`, `claude-code`, `claude`, `grok`, `codex`, `cursor`, `other`) and `family`
(`flash`, `claude`, `grok`, `luna`, `terra`, `sol`, `astra`, `other`, `excluded_pro`).
Model ids are opaque strings. `effort` is null when that route has no effort
knob, or a nonempty provider label preserved as written. The checker does not
translate labels and does not certify that a label was observed as a supported
setting. `selected.supported: true` is the record's claim, not catalog proof.
The same resolved Markdown configuration used by invocation and the installer
supplies selected services, optional exclusions and head model/effort choices.
No public model-family effort floor or personal provider order is imposed.
Model and effort IDs are opaque; live route support still requires evidence.
A `user_pin` must have exact `reason_evidence.binds` for route, family, model and
effort before overriding a private model choice. This checks identity, not whether
a user actually wrote the pin. It never overrides safety or host permissions.

`selected_reason` is `ordinary_assignment`, `bounded_codex_fallback`,
`user_pin`, `tool_incompatibility`, `quality_incompatibility`, `complex_scope`,
`not_required`, `excluded_model`, or `price_informed`. Exactly one alternative has disposition
`selected` and must match the selected route, family, model, effort, evidence,
and reason. Other dispositions are `compared`, `incompatible`, `not_required`,
and `excluded`. `not_required` may use null evidence. Every other candidate
needs an evidence id.

`bounded_codex_fallback` retains its historical receipt enum. It now requires
a recorded prior capacity/auth failure, Codex as selected route and at least one
evidence-backed task-fit comparison. It has no hardcoded plan/family/model/effort
mapping. `tool_incompatibility` requires tool `unsupported` and failure `tools` or
`capacity`. Capacity cannot be relabeled as `quality_incompatibility`; quality
incompatibility requires actual quality failure and quality `unmet`.

`complex_scope` requires task class `complex_diagnosis`, `inherits: false`, a
`boundary.scope` id different from the bound task scope, and a `boundary.next`
id for the remaining simple work. `next` cannot be `none`, the bound scope, or
the narrow scope. Those are id bindings, not a reading of an explanation.

`selected.reason_evidence` must resolve. It is stale when it reuses the prior
candidate's evidence id after the route, family, model, or effort changed, or
when that evidence has `binds` whose route, family, model, and effort differ
from the selection. `binds` must be an object with those four fields. A string
is rejected and is not read as a reason. Missing `binds` does not prove the
note is current.

Constraints are `task` (`bounded_simple`, `complex_diagnosis`,
`head_orchestration`, `other`), `quality` (`met`, `unmet`, `unknown`), `tool`
(`supported`, `unsupported`, `unknown`), `billing` (`subscription`, `paid_api`,
`unknown`), and `context` (`reusable`, `contaminated`, `fresh`, `unknown`).
`paid_api` requires explicit resolved opt-in and current task authority; it is
never an automatic fallback. Unknown billing blocks execution. Head model and
effort choices come from private configuration or a bound explicit current-task
pin; no public Codex/Astra orchestration model is required.
Boundary `review` is `independent`, `parent`, `deterministic`, or `pending`.
`reconsider` is `failure_class_change`, `quality_evidence`, `tool_change`,
`user_pin_change`, `scope_boundary`, or `none`.

Optional `tokens` has `input`, `output`, and `basis` `observed` or `unknown`.
Basis `quota` fails. Unknown basis cannot carry counts. Observed basis needs a
count. Omitted tokens stay unknown. No count is derived from quota, credit, or
price.

The receipt format is `company-routing-decision/v1`. It repeats the binding,
selected route/family/model/effort, configuration_sha256 over ordered document
bytes, the decision file hash when `routing-check`
read a file, and the limit that these are enum and binding checks only.
Synthetic cases are in [routing cases](../assets/routing-cases.json). No case is
live evidence. A pass does not prove quality, savings, provider behavior, or
launch enforcement.

## Accepted completion retention extension

`record_check.py` does not interpret annotation `artifact_retention`. The separate
[completion checker](completion-retention.md) verifies its exact Run ID, manifest
hash, quiescence assertion and all declared consumer settlements before the
installed callback can delete declared temporary files. It additionally requires
real resource accounting, actual hash-bound acceptance evidence, overall accepted
success, successful settled tasks and independent/parent acceptance. These guards
do not authenticate a self-authored ledger or establish actual independent review.


### Price-informed selection

For the packaged current model table, add `price_selection` to the existing
version-1 routing decision; historical record checks remain readable.
`routing-select decision.json --json` returns advice, not a launch receipt.
`routing-check` is the fresh prelaunch check. It requires a candidate comparison
for unpinned decisions and checks the selected identity and quality/tool/billing
constraints. A nondominated choice may differ from the advice's cheapest choice.
The receipt includes the table hash and comparison basis. See the
[prelaunch contract and limits](routing-prelaunch.md). Existing
Task/Dispatch, source hashes and optional `--record` binding still apply.

`price_selection` contains integer `version: 1`, `task`, `cost_basis`
(`benchmark_prior` or `whole_work_estimate`), boolean `scope_api_authorized`, and
nonempty `candidates`. The LLM supplies `task` with `actor` (`company_head`,
`team_lead`, `worker`; CEO/goal heads use `company_head`), `capability` (`focused`,
`visual_writing`, `coding`, `judgment`), `complexity` (`bounded`, `complex`),
`coupling` (`local`, `coupled`), boolean `decomposable`, `stage` (`outcome`,
`execution`, `consultation`), `uncertainty` (`none`, `ambiguity`, `conflict`,
`repeated_failure`) and an `evidence` id. A separable complex outcome returns
`decompose`, not an executable choice; classify its real work units next.

Each candidate has exact `route`, `family`, `model`, `effort`, boolean `supported`
and `authenticated`, `tools` (`supported`, `unsupported`, `unknown`), `billing`
(`subscription`, `paid_api`, `unknown`), `runtime_evidence`, `quality` (`adequate`,
`insufficient`, `unknown`), `quality_evidence` and nullable `usage_estimate`.
Supply only current-pin-compatible candidates. Runtime evidence must be host-kind
(or synthetic in labeled tests), not merely an owner availability report. This
checks supplied provenance, not its truth or freshness. Quality evidence must
assess the actual task/model/effort; it may use applicable benchmark priors without
new local trials. To supersede a conflicting general capability prior, the quality
evidence entry needs `task_fit`: `task_evidence` matching this task's evidence id,
`candidate` with the exact route/family/model/effort, a separate valid `support`
evidence id, and a nonempty task-specific `rationale`. Unknown/insufficient quality
cannot override a prior. These bindings reject empty, stale or self-supporting
assertions; they do not authenticate the supplied assessment's substantive truth.
Unknown/malformed runtime or semantic input fails closed;
known-ineligible pairs are excluded. No automatic paid or unsupported fallback.

For a model on a non-Codex route, use the same `price_selection`
candidate inventory, including every available non-excluded Codex model/effort
with a table prior. Its `usage_estimate` is null; its `comparison_value`, actual
usage and subscription charge remain null. The selected reason cannot be
`price_informed`. The checker does not compare unknown price or quality against
the table. For a Codex selection it still checks known omissions and dominance;
an explicit bound pin keeps its existing authority. The same model ID on another
route is a separate candidate: verify that route independently and do not copy
the Codex price or benchmark. Unknown Codex aliases do not acquire table values.

The unlisted candidate's host `runtime_evidence` adds `unlisted_runtime` with
exact `candidate` identity (`route`, `family`, `model`, `effort`), canonical
`agent`, `host`, `supported`, `authenticated`, `tools`, `billing`, time-zone
aware `observed_at`/`valid_until`, and evidence IDs `model_evidence`,
`support_evidence`, `auth_evidence`, `tools_evidence`, and `billing_evidence`.
Values must match the candidate. Each referenced real host entry has `file`,
SHA-256, matching `host`, and its own current `observed_at`/`valid_until`.
The unlisted runtime host must also match the `host` on the pinned Codex
inventory; at prelaunch that inventory is the current canonical host file.
These host labels are supplied evidence, not authenticated host identity.

The pinned model file must match one of these limited catalog shapes:

- A JSON object with a `models` array. The exact `id` row must contain
  `supported_reasoning_levels` with an explicit matching `effort`. A nonempty
  `error`, or `ok` or `success` set to false, invalidates the catalog. A model
  name appearing only in an error or another field does not count.
- For Antigravity, the captured tab-separated model ID and display-name rows,
  with a recognized effort suffix on each ID matching the display-name suffix;
  the exact model and requested effort must occur together.
- For Grok, the captured login/default header and `Available models:` list of
  starred or hyphenated model rows. This shape carries no effort setting, so it
  is usable only when the requested effort is null; it does not prove support
  for any named effort.

Unknown formats, a bare model name, an unsupported effort, malformed lists and
the declared JSON error/status fields above fail closed. These parsers check recognizable structure and
supplied bindings; they do not establish that a file came from a successful
command, authenticate its origin or interpret the truth of its statements.
Quality evidence needs the `task_fit` binding described above.
For a real unlisted candidate, both the task-fit entry and its separate support
entry must be non-synthetic and bind SHA-256-pinned files.
Synthetic cases label all entries synthetic and cannot prove real availability.

For support, authentication, tools, and billing, each referenced host evidence
file is a JSON observation with `format: company-runtime-observation/v1`, the
same `candidate`, `agent` and `host`, one `claim` (`supported`, `authenticated`,
`tools`, or `billing`), its corresponding `value`, and `source_evidence` naming
a separate, current, same-host, SHA-256-pinned host file. Preserve the raw source
and the operator's rationale. The checker reads the observation and pins and
checks the declared time windows; it does not authenticate a file's origin or
interpret the raw source as proof of that claim. The operator and independent
reviewer must inspect those sources, actual provider support and billing before
using the supported Orca route. The checker neither launches nor intercepts it.

A nonnull `usage_estimate` has `basis: estimate`, `evidence` and `stages` with all
seven keys: `instructions`, `execution`, `feedback`, `failures`, `retries`,
`review`, `integration`. Each is null (unknown) or a list of estimated full
requests (`[]` explicitly means no separate requests). Each request has unique
`id`, exact `model`, nonnegative integer `uncached_input`, `cached_input`,
`cache_write_30m`, `output`, nonnegative `tools_usd`, `tier: standard`, and
`region: global`. Input categories are disjoint; output includes reasoning already
in the provider total. Assign each request to one stage only: instruction tokens
inside an execution request are included there, not added again. Mixed-model
review/retry requests use their own published model rate. Other price contexts
are unsupported, not silently priced as Standard/global. All eligible workflows
need complete estimates for an estimate comparison. When all eligible workflows
have complete supplied estimates, they take precedence even if `benchmark_prior`
was requested: the result records `requested_comparison_basis` separately from
`comparison_basis`. Do not provide inapplicable estimates as comparable workflow
inputs. Otherwise retain unknowns
and explicitly use an applicable benchmark prior or obtain the missing evidence.

Price advice leaves actual usage, subscription charges/credits and effective
model/effort unknown. Keep requested versus observed settings in the existing
Task model fields, with fallback/readback provenance in the associated evidence.
A launch flag or a passed synthetic check is not effective-setting proof, permission
to spend, a model call, a session switch or evidence of actual savings.

## Measurement-required comparisons

This section describes the original version 1 observed-preflight contract.
Explicit `measurement.version: 2` instead uses the separate
[prepare, bind and settle contract](measurement-lifecycle.md). Old final evidence
is not rewritten. Unsettled v2 usage cannot produce a raw total or final success.

For a comparison or efficiency evaluation that needs end-to-end measurement,
set `measurement.mode` to `required` in the current record before preflight.
Do not add it to ordinary maintenance. Existing failed records remain readable;
adding a mode later does not retroactively make a failed preflight pass.

`measurement.goal_binding` contains the current goal's exact `id`, `revision`,
`scope`, and `plan` reference. `objective` and `criteria` are evidence IDs for
the original user objective and frozen evaluation criteria. The plan, objective,
and criteria each need a readable, SHA-256-pinned file in `evidence`. The checker
binds these bytes; an independent reviewer still determines whether the criteria
answer the original objective. A successful ledger check or notification is not
itself an efficiency result.

`boundary` contains nonempty `start`, `end`, and `shared_costs` descriptions.
`expected_actors` lists all participating actors, including the goal owner,
workers, verification, integration, failed attempts and retries where applicable.
`participants` must contain exactly one binding per expected actor; recorded Task
executors, technical reviewers, parent integrators and any independent overall
assessor must also be in that list. A human overall assessment does not require
a provider session. Each binding has `actor`, `provider: "codex"`,
`session`, `source`, `turns`, `prefix_bytes`, and `prefix_sha256`. Supply the
actual local JSONL path and observed session and turn IDs, not a date-derived
path, worker metadata, or planned resolver. The prefix must end at a newline and
contain an observed turn start, real response usage, and matching cumulative
mirrors for every listed turn. A live turn may be missing its completion marker.
A preflight must also observe at least one selected turn per participant still
open in the current source; a prefix cut before an already recorded completion
cannot turn a post-hoc check into readiness. Earlier selected turns may be closed.
An absent completion marker alone does not prove that the process is still live
or that this actor owns the session; check the host evidence separately.
A later append is allowed; a changed or truncated pinned prefix is rejected.
Turn and response scopes must not overlap. Other providers are unsupported.

For example, the following fragment names two expected actors. Replace every
placeholder with observed values; this fragment alone is not a ready record.

```json
{
  "mode": "required",
  "goal_binding": {"id": "GOAL", "revision": "REV", "scope": "SCOPE", "plan": "plan"},
  "objective": "original-objective",
  "criteria": "frozen-criteria",
  "boundary": {"start": "user request", "end": "integrated result", "shared_costs": "lead and worker, including review"},
  "expected_actors": ["lead", "worker"],
  "participants": [
    {"actor": "lead", "provider": "codex", "session": "OBSERVED-SESSION", "source": "/private/lead.jsonl", "turns": ["OBSERVED-TURN"], "prefix_bytes": 123, "prefix_sha256": "OBSERVED-SHA256"},
    {"actor": "worker", "provider": "codex", "session": "OBSERVED-SESSION-2", "source": "/private/worker.jsonl", "turns": ["OBSERVED-TURN-2"], "prefix_bytes": 456, "prefix_sha256": "OBSERVED-SHA256-2"}
  ]
}
```

For an active goal, run `record_check.py check RECORD --measurement-preflight
--json`, preserving its successful output as a new private file. The output's
`measurement_preflight` binds the exact goal, evidence hashes, boundaries,
participants and source prefixes. In the final record, set `measurement.preflight`
to the corresponding hash-pinned `evidence` ID, and add `final_bytes` and
`final_sha256` to each participant. The final snapshot must extend the original
prefix and contain complete selected turns. `usage.expected` and `usage.entries`
must account for every selected Codex response exactly once, with matching
session, input, output, cached input and reasoning counts. Partial, missing or
mismatched usage prevents `goal.status: "succeeded"` and leaves the total null.
Counts are provider-reported and cached/reasoning values are inclusive subsets.

The receipt is a byte-bound consistency check, not an authenticated timestamp,
proof of source origin, evidence that someone understood or approved a goal, or
proof of comprehensive participant discovery. Preserve launch/done evidence and
obtain independent review of chronology, participant completeness, original goal,
and outcome. Do not treat a post-hoc preflight as evidence it happened before a
launch. Actual quality, hidden answers and cross-candidate exposure, matched
inputs, caches and environment, a numeric budget and its supported controls,
failure, stopping, concurrency, retry and cleanup conditions remain decisions
and observations outside this checker. A receipt is neither a hard token cap nor
an operating-system or server-wide launch control.

### Optional goal dependency evidence (v1)

A record can require this check by adding `"goal_evidence": {"mode":"required", "path":"goal-evidence.json"}`. Paths are relative to the record directory; only bounded (1 MiB), regular, non-symlink files beneath that directory are read, with duplicate JSON keys rejected. `check --goal-evidence PATH` also explicitly requires the sidecar for that invocation; it must agree with any record declaration. Absent opt-in is `not_evaluated`, not verified. The declaration is needed for completion and the status CLI to enforce the same check without an extra flag.

The exact sidecar object has `format` (`company-goal-evidence/v1`), `run_id` (the nonempty `record.run`, not goal ID), `goal` (`id`, `revision`, `scope` matching the record), and `tasks`. Each task object has exactly `task`, `dispatch`, `candidate`, `result_evidence`, `technical_evidence`, `integration_evidence`, and `predecessors`. It must cover every current record task exactly once, match the current dispatch/candidate and the evidence IDs in its result, technical review, and parent integration. Each predecessor is exactly `{"task":"TASK_ID", "handoff_evidence":"EVIDENCE_ID"}`. Every edge must have exactly one matching record `handoffs` entry containing `evidence`, `from_task`, `from_dispatch`, `from_candidate`, `to_task`, `to_dispatch`, `to_candidate`, matching both current task nodes; its evidence must exist, be unique to the edge, and differ from all result/review/integration IDs. Every declared record handoff must appear in the sidecar. Duplicate edges, missing handoffs, dangling references and cycles fail. The DAG is an explicit declaration; the checker cannot infer omitted real-world dependencies. `structurally_valid` means these bindings are consistent, not that issuers, independent review, handoff contents, host execution, or goal success are authenticated. Existing record validation and completion criteria remain in force.

Optional routing decision `profile_binding` is the exact object emitted by `record_check.py profile-prepare`; see [routing prelaunch](routing-prelaunch.md). Its snapshots and digests are recomputed and checked against the selected identity and task. It does not replace the existing decision checks.
