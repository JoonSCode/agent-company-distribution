# Model, execution route and context policy

Resolve [configuration](configuration.md) before a material assignment. The common
rules, selected preset, private user override and explicit current task apply in
that order, within higher-priority authority and safety. The resolver explains
which document supplied every setting. Private choices do not become public
blanket defaults. A missing user document means single connection, no selected
service and updater OFF; existing installed files and registrations stay intact.
Do not infer legacy owner preferences from a username or machine path.

## Choose a complete execution candidate

Compare service + actual provider/model + supported effort + tools/permissions +
billing route + relevant context. Model and effort IDs are opaque strings. Neither
a preset, plan, price nor role maps automatically to a model. Codex, Claude Code
direct, Antigravity (including its Claude path), Grok and Cursor are separate
services. A Claude-only Company needs no Codex or Astra orchestration model. The
packaged native TOML/hook adapter currently targets Codex; other paths require the
actual Orca host's supported launch and an explicit skill/role brief. See the
configuration guide for the manual, provider-neutral entry path and its limits.

Only selected services are eligible. Before execution, verify actual host support,
authentication, model/effort selection, tools, authority and billing. Selection is
intent, not authentication. A CLI missing or an expired login is not proof the user
has no subscription. Inspect the documented launcher and native read-only state,
then repair within existing permission or report the exact gap. Never sign in,
change global defaults or pay merely to make a configuration check pass.

## Compare by task evidence

First satisfy explicit current-task pins, quality, authority, tools and billing.
Apply resolved service preferences and exclusions. Compare model × native effort
for the current work, not CEO/head, lead or worker title. Among task-fit candidates,
prefer the lower whole-work API-price proxy within the deadline; time and actual
subscription charges/credits are separate. Include instructions/context, feedback,
failed attempts, retries, independent review and integration across all participants.
Unknown usage or cost stays unknown; raw token count alone is not the objective.
Do not count shared requests twice or present a published price as a subscription bill.

The LLM assesses semantic capability, complexity, coupling, decomposability and
source-backed quality fit. The deterministic selector applies the supported
candidate table, resolved configuration and declared comparison basis. Task-fit
logical reasoning and applicable benchmark priors can justify an initial
model/effort assignment without mandatory local measurement or A/B. Bind the
reason to the task's ambiguity, coupling, failure risk and observable checks;
for benchmark priors, retain model × effort, harness, date and transfer limits.
Benchmark $/task is a directional prior, never an estimate of arbitrary
work or proof of savings. Complete estimates for every eligible workflow take
precedence over a requested benchmark basis; do not quietly replace missing usage
with zero. The receipt retains requested and applied comparison bases. See [dated evidence](model-evidence.md).

Do not use all Terra or a universal cheap-first ladder. Complex coupled execution
can need Sol/Astra as the executor. These general capability priors are not family
bans: a source-supported assessment bound to the exact task and candidate can
supersede them; a bare adequate flag cannot. For separable complex outcomes, isolate hard
design/contracts/judgment from bounded implementation and classify those actual
work units separately. Consult a strong model on genuine ambiguity, conflict or
repeated failure, not on every settled step. Small work needs neither every model
nor every organizational tier; responsibilities and independent acceptance remain
unchanged. Stronger/lower-effort and cheaper/higher-effort are separate candidates.

A strong navigator with an economical executor is an optional task-fit pattern
when difficult decisions separate cleanly from bounded execution. The navigator
sets design/contracts, constraints and checkpoints; one executor owns the edits,
tools and checks, and reports artifacts and unresolved decisions through the
[shared work note](session-continuity.md#compact-direction-and-report). Consult
the navigator on genuine ambiguity, a contract change, a meaningful milestone or
repeated failure, not each edit. Compare strong-alone, economical-alone with
review, checkpoint pairing and continuous pairing by expected accepted quality
and whole-work burden, including briefing, waiting, feedback, rework, review and
integration. Tightly coupled or hard-to-check work may favor a strong executor;
tiny exact work may favor direct tools. Pairing does not supply independent QA.
Choose by reasoned task fit now; a frozen comparison is optional validation, not
an assignment gate. Claim measured savings only from comparable observed usage.

Apply the same task-fit reasoning to provider-native helpers inside an existing
Orca assignment. A bounded source extraction with clear checks can use a different
supported model/effort from its parent; a coupled judgment may stay with the parent.
Compare briefing, original-result review and integration burden before delegating.
Keep the reason, requested/observed settings or unknowns and lifecycle evidence in
the existing work note; do not fabricate an Orca routing receipt or a Task/Dispatch
bridge for a native helper. Follow the [bounded native-helper workflow](orca-contract.md#bounded-native-helper-workflow).

API-paid routes require api_paid: true from an explicit user or current-task
document and current scope permission. This is permission to consider the route,
never an automatic fallback or permission to buy capacity. Unknown billing blocks
execution. Do not silently change subscription, add paid overage or use a provider
API. The resolver/checker is not a launch interceptor or authentication verifier.

## Overall Company head execution boundary

The accountable overall head of each goal owns user intent, decomposition,
assignment, dependencies, conflict resolution, integration, evidence judgment and
acceptance. It does not mechanically forward workers' conclusions. Workers own
leaf research, design, production, tests and fixes. The head may read originals,
diffs and evidence for spot checks and make tiny deterministic coordination calls.
It must not duplicate assigned implementation or routinely take over failures.
Direct execution is a narrow exception for small isolated work whose delegation
overhead exceeds the work, with no active owner conflict and a short reason.
Preserve independent verification. Specialist leads are not automatically overall
heads. No head or child model/effort pin is imposed by this boundary.

## Checked assignments and failure recovery

For the packaged model table, run `record_check.py routing-select decision.json
--json` using the LLM's `price_selection` input, then place its selected identity
in the existing version-1 decision with `selected_reason: price_informed`.
`routing-check` rejects a dominated candidate or incomplete decomposition and
requires the supplied candidate inventory for a fresh unpinned assignment. It
allows a nondominated choice other than the advice's cheapest choice. The selector is local, pure advice: it makes no API
or Orca calls. Unknown/malformed capabilities, runtime support or billing do not
trigger an inferred model, effort or paid fallback. For an unlisted provider/model,
include the known Codex inventory and candidate comparison, bind actual route,
host, support, authentication, tools, billing and exact task fit to current pinned
evidence, and use an ordinary evidence-based reason rather than `price_informed`.
Its price, benchmark comparison and tokens remain unknown; do not substitute a
table alias or rank it by an invented value. Another route offering the same
model ID needs independent evidence and does not inherit the Codex price. The
checker verifies supplied files and bindings, not the truth of an operator's
interpretation or live execution.
See [record fields and limits](record-contract.md#price-informed-selection).

Use a version-1 routing decision and record_check.py routing-check before a
material Orca assignment, retaining its receipt. Existing Task/Dispatch binding,
source evidence, selected/alternative consistency, resource/lifecycle, causal
failure classification and independent-verification requirements remain in force.
The checker consumes the same resolved document as invocation and native-role
generation. Real decisions need a selected service; synthetic checks prove only
structure. Explicit bound task pins can override user model choices, never safety.

A capacity failure is not evidence of a quality failure. Retain failed attempts;
choose a discriminating check or supported alternative on causal evidence. A
complex diagnosis must name a narrower scope, next boundary and no blanket
inheritance. There is no hardcoded family/effort fallback mapping. A worker_done
is not overall acceptance. No receipt grants a second authoritative writer.

## Verify settings, context and usage

Record requested model/effort separately from actual host/provider readback and
its provenance, including any fallback (or unknown fallback). Orca launch support
for `--model` and `--effort` does not prove the effective setting: an unsupported
effort can fall back. Check host capabilities, not an assumed minimum version. Do not infer settings from role names, terminal titles or launch
arguments. Reassess model/effort, context relevance/contamination, tools,
permissions, review independence and lifecycle at meaningful task boundaries.
Reuse healthy relevant sessions only when the whole-work burden favors reuse.
If a supported setting change is unavailable, settle the current work and use a
supported successor with concise source-bound handoff. Do not change global app
configuration as a session-only workaround. Retain ownership and cleanup duty.

Observe input/output once per non-overlapping request or interval. Do not add
cached or reasoning tokens already included in provider totals. Preserve provider
and tokenizer differences and missing coverage. A policy edit does not switch
running sessions, certify live auth or establish savings. For thin evidence use
[evidence acquisition](evidence-acquisition.md), and keep the smallest check that
can change the decision. User-specific historical choices in dated evidence are
history; only an explicit private migration or current choice makes them active.
