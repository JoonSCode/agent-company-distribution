---
name: agent-company
description: Explicit Agent Company whole-studio front door through bounded role workers and King Sejong. Use only when the user explicitly invokes Agent Company, $agent-company, or asks to operate the company as a whole. Do not auto-trigger merely because a request concerns a new app, improvement, planning, marketing, release, incident, or portfolio; those individual methods remain separately discoverable.
---

# Agent Company

Treat the user as CEO and King Sejong as the Chief of Staff and lead synthesis
authority. Create actual temporary role workers for assigned slices; do not
simulate a company by writing role-labelled prose in one voice.

The company's standing purpose is a profitable app portfolio. Work includes
marketing, redesigning, extending, repairing, and maintaining existing apps as
well as discovering needs and developing new apps.

Distribution is separate from invocation: root `install.sh` clones the fixed
public `v0.1.0` runtime projection, installs and verifies the exact pinned King
Sejong Core, then installs and verifies Agent Company. This pointer does not
change the explicit front-door trigger below.

## Invocation and Route Binding

Use the full Company front door only when the user explicitly invokes Agent
Company or asks to operate the company as a whole. Individual methods remain
implicitly available: role operating systems, problem discovery, commercial
fit, evidence debate, uigwe, and Seungjeongwon may still route normally without
creating a Company job.

After explicit invocation, start or resume a continuous company session and
remain in it until the CEO explicitly exits. A concrete CEO thesis starts
`ceo-directed` work. A request such as `continue`, `just do it`, or an
equivalent no-thesis instruction starts a `company-initiated` tick from
portfolio evidence; do not invent an improvement target merely because the
queue is empty.

Before staffing, consume one accepted `agent-company.route-decision/v0.2`
projection from the King Sejong Core decision. Verify its Core authority hash,
immutable ordinary-role list and staffing hash. Never select or rewrite the Core
route, backend, hard gates, capability evidence, or reentry target.

- **Direct** creates no v0.1 Company job, company meeting, squad, or company plan. It
  retains material-ambiguity, external-action, host-permission, and selected-
  surface verification gates.
- **Role** creates exactly one ordinary role assignment. The role remains
  evidence-only and Seungjeongwon or the selected surface owns independent
  verification; the assigned role never self-verifies.
- **Squad** binds the immutable staffing projection to the existing v0.1 job
  lifecycle below. Auxiliary specialists remain separate dependencies and never
  count as ordinary lane roles.

## Resolve Policy

Resolve the active Agent Company snapshot under
`${CODEX_HOME:-~/.codex}/agent-company/snapshots/<active snapshot>/repo`, or use
the current Agent Company checkout during development. Read:

- `policies/job-catalog.json` for classification and company budget defaults;
- `policies/company-charter.json` for purpose, authority, initiation, staffing,
  and cycle limits;
- `policies/company-state.schema.json` for portfolio, initiative, observation,
  active-cycle, history, revision, and fencing invariants;
- `policies/squad-recipes.json` for the smallest valid squad and conditional roles;
- `workflows/<job-type>.json` for company-specific stage order;
- `policies/specialist-request.schema.json` for executable specialist inputs;
- `policies/expertise-registry.json`, `policies/reference-manifest.json`, and
  `policies/expertise-routing.json` for one Role OS, one Task Pack, and
  zero-to-two decision-changing specialists;
- `policies/runtime-reference-set.schema.json` and
  `policies/reference-read-ledger.schema.json` for fresh Current Sources, Job
  Evidence, hash-cache use, and used or unused read traceability;
- `policies/uigwe-decision.schema.json` for decision-specific job resumption;
- `policies/external-action-policy.json` before any non-local action;
- `policies/ceo-report.schema.json` and `policies/compact-ceo-report.schema.json`
  when reporting to the CEO.

Treat these as company policy inputs. Let King Sejong Core own worker
registration, concurrency enforcement, execution waves, fan-in, receipts,
approval mechanics, idempotency, retries, leases, locks, and worktrees.

## Company Operating Cycle

Run one deterministic transition at a time and persist enough state to resume
after interruption. Permit at most one active cycle. Use expected revision and
fencing-token checks on every mutation, and treat a repeated tick key as an
idempotent replay.

When there is queued CEO work, prioritize it within the charter and current
guardrails. Otherwise create a bounded portfolio-discovery initiative. Register
existing apps and new opportunities explicitly, record commercial observations
only from hash-matched evidence, and preserve missing attribution, stale data,
or incomplete formulas as unknown.

Bind every executable initiative to the charter digest, origin, target,
commercial hypothesis, success and failure metrics, guardrails, and CEO
approval boundary. Load an approved company plan and its role plans before
plan-backed delegation. Role IDs describe capabilities, not seats: distinct
assignment IDs may use the same role, and disjoint write scopes may run in the
same Core wave. Overlapping scopes must be rejected or dependency-serialized.

The checked-in scheduler wrapper performs one safe tick and exits. Never install
or activate the launchd template without an explicit CEO request. Never move
worker lifecycle, worktree, lease, retry, receipt, or final-verification
authority out of Core and Seungjeongwon.

## Job Lifecycle

1. **Intake.** Capture the source request, objective, constraints, repo or product refs,
   desired outcome, and allowed external actions.
2. **Kickoff.** For a Squad route, classify exactly one primary job type: `new-app`, `improvement`, `planning`,
   `promotion`, `release`, `incident`, or `portfolio`. Split truly independent
   outcomes into separate jobs instead of widening one job. Record a bounded
   company-meeting artifact in the job with status `recorded`, participants,
   agenda, intake decision, selected squad and recipe, budget, and workflow.
   Select the recipe's required roles. Add a conditional role only when its
   named condition is present; selected roles must receive an assignment or the
   projection must reject the job explicitly within the Core budget.
3. **Uigwe.** Detect material ambiguity before irreversible design or execution. A
   question is material when its answer can change the target user, core
   problem, product scope, architecture, release boundary, public claim,
   spending, or accepted risk. Route it through Uigwe, ask the CEO only for the
   blocking decision, and resume the same job only from a loaded
   `agent-company.uigwe-decision/v0.1` artifact whose job, user or CEO authority,
   referenced Uigwe packet, and exact material-question resolutions match.
4. **Execution.** Give each role a bounded objective, read and write scope, evidence refs,
   expected output, stop condition, and forbidden claims. Require the actual
   host-native worker identifier in the Core execution record. Set every
   assignment's action authority to `evidence_only`. Resolve the role and task
   deterministically, materialize only its Role Kernel and selected Task Pack,
   and record each specialist's decision question and expected marginal value.
   Never expose Evaluation Sets to the executor.
5. Use selective parallelism only when the selected squad recipe records the
   same role slices and predecessor plus a nonempty independence condition.
   Carry that evidence in the projected wave; adjacency or workflow hints alone
   do not authorize parallel work. Let Core open the wave and fan in every
   required terminal receipt.
6. Accept validated specialist request objects only for a named evidence gap or
   decision. Bind the job, requester, and Sejong decision owner; charge worker,
   spawn-depth, and round costs to the job budget; and project the specialist
   dependency wave before downstream decision work. Reject invalid or
   over-budget requests. Specialists never gain worker-lifecycle, planning,
   synthesis, or verification authority.
7. Execute local reversible work after Uigwe readiness. Stop before any denied
   or approval-required external action until Core carries a valid explicit CEO
   approval reference and external-action receipt. Agent Company records only
   the deterministic action requirement, never the receipt lifecycle.
8. Send implementation and QA evidence through Seungjeongwon. Role outputs are
   evidence, not final truth; a completed worker is not a verified outcome.
   Current handoffs and logical role-session checkpoints must bind the exact
   knowledge context, usage receipt, reference-read ledger, and local handoff.
   Role sessions remain serial identity records, never persistent workers.
9. **Report.** Report to the CEO from referenced job, worker, action, and verification
   evidence. Keep executed, verified, failed, blocked, and unverified claims
   separate. Use `mixed` when the report contains more than one material state.
   Report initiative origin and commercial evidence state; technical
   verification must not upgrade an unobserved revenue claim.

## Model Value and Continuation Evidence

Treat model labels such as `exploration-high`, `execution-medium`, and
`verification-high` as semantic requests, never as backend authority. Core
still selects the route and backend; record the observed effective model. A
lower-cost execution profile is eligible only after Uigwe has removed material
ambiguity and the plan has explicit pass criteria. Escalate when execution
uncovers new judgment, contract drift, or failed verification.

Keep three mechanisms distinct: provider-reported cached input, deliberate
session continuation, and local artifact reuse. Record an optional
`attempt_receipt` inside the private metric event with requested profile,
effective model, reasoning effort, service tier, provider token/cache
breakdown, local artifact reuse, rework, verified quality, critical
regressions, verifier identity, verification time, evidence digest, and opaque
evidence refs. Bind the prior attempt plus source, decision, capsule, rules,
plugin set, tool schemas, and stable prefix by SHA-256. `cache_strategy`
records intent; a numeric cache field records provider evidence, while null
means unavailable.

Model routing remains `shadow`: it cannot change a Core route, backend, or
model. Receipt digests and counters are producer observations, not authenticated
authority. This contract does not implement a promotion consumer; an approved
future consumer must rehash referenced evidence before comparing task-class
repeats on cost, rework, and verified quality. Never optimize cache-hit ratio
alone. Resume a session only for adjacent work with a reusable stable prefix,
healthy context, a bound prior attempt identity, no model change, no
independent-verification boundary, no inherited-context risk, and no
invalidation reason. Otherwise start a new session and preserve the receipt.

## Work Lifecycle Learning

Consume only a validated
`sejong.lesson-candidate/v0.1-draft` artifact from King Sejong Core. Rehash the
candidate before use and require the company learning policy's independent-run
threshold. Never copy raw transcripts, prompts, messages, secrets, connector
payloads, or private absolute paths into Company policy.

The learning consumer may create only an
`agent-company.automation-proposal/v0.1` artifact with `status: proposed`,
`activation_authority: none`, and explicit CEO approval requested. It must not
install a skill, activate a hook, mutate a capability registry, or infer root
cause from one event.

Managed capabilities remain Agent Company scoped and budgeted. Reject global
ownership, duplicate capability IDs, overlapping active triggers, unmanaged
deletion fields, or anything broader than hash-matched Agent Company-managed
removal. Promotion remains shadow-first and requires a separate approved
consumer; these learning artifacts do not widen `memory-record` or staffing
`lane-promotion` authority.

## Role Boundaries

For mobile-app monetization or paid-acquisition work, Planning and Marketing
must both read the shared
[mobile-app monetization experiment priors](../marketing-operating-system/references/mobile-app-monetization-priors.md).
Marketing owns the demand, channel, funnel experiment, and downstream-quality
evidence. Planning consumes that evidence for milestones, dependencies,
acceptance criteria, spend stages, and stop conditions. Neither role may copy
the numeric priors into fixed company policy or let them override mature
product-specific cohorts.

- `founder`: frame portfolio direction, founder fit, commercial wedge, and
  opportunity cost.
- `planning`: own company-plan coordination, milestones, dependencies, success
  criteria, sequencing, and Uigwe-ready handoff. Consume problem-discovery and
  commercial-fit outputs from Founder, Marketing, or bounded specialist
  dependencies; do not execute those loops directly.
- `design`: own experience flows, interaction decisions, visual direction, and
  design QA evidence.
- `development`: own architecture evidence, implementation, tests, and
  technical risk.
- `marketing`: own demand evidence, positioning, channel hypotheses,
  experiments, and draft communications.
- `qa-release`: own verification plans, observed results, release risk, and
  matching-surface manual QA.

Each role must return `known`, `inferred`, `unknown`, actions, artifact refs,
risks, and the next recommended Sejong surface. No role may approve Uigwe,
claim final synthesis, self-verify its work, or widen scope.

## Stop Conditions

Stop and return control to the Sejong lead when the assigned slice is complete,
a material ambiguity needs Uigwe, the Core budget is exhausted, an external
action lacks approval, required evidence is unavailable, or verification fails.
Never hide these states behind a positive CEO summary.
