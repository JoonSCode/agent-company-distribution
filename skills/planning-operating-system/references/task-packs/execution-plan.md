# Execution Plan

- Reference ID: `task-pack:planning:execution-plan`
- Role: `planning`
- Required kernel: `role-kernel:planning`
- Task type: `execution-planning`
- Decision: how should an approved objective become the smallest dependency-safe
  set of executable leaves without changing its intent?

This pack produces a milestone DAG and handoff-ready leaves. It does not approve
the material decision gate, choose a different product direction, execute the plan, or claim
that any leaf or outcome is verified.

## Decision Core

Apply `planning-contract.json#/decision_output_policy` before expanding the
plan. Lead with the two readiness states, the smallest criterion-complete
topology, the controlling unknown or blocked edge, and the next safe action.
Then include only leaves and dataflow edges that deliver a criterion, preserve
a must-preserve behavior, contain a named risk, or produce decisive proof.
Do not make the answer look more executable by inventing assignees, dates,
paths, thresholds, or approval state. A short blocked plan with a precise
falsifier is stronger than a complete-looking fictional schedule.

## Exact Triggers And Non-Triggers

Use this pack when:

- an approved objective needs milestones, work boundaries, owners, or ordering;
- another role cannot start because the first action, inputs, done criteria, or
  handoff output are not concrete;
- a broad plan must be converted into independently assignable leaves;
- scope, non-goals, authority, and success criteria are stable enough to test
  planning readiness;
- an existing plan needs decomposition without changing the approved outcome.

Do not use it when:

- the goal, success criterion, non-goal, must-preserve behavior, or authority
  that can change a tradeoff or irreversible boundary is materially ambiguous;
  do not reject the intake or demand a finished brief. Return to the authorized decision owner with
  inspected context, grounded options and reasons, focused decision questions
  that allow a free response, and draft completion criteria. Missing final
  execution authority alone does not block a
  source-backed advisory artifact; it blocks execution startability;
- the question is which company opportunity deserves resources; route that to
  Founder;
- only dependency integrity or risk ordering needs review; use
  `task-pack:planning:dependency-risk`;
- only acceptance criteria and proof surfaces need design; use
  `task-pack:planning:acceptance-verification`;
- implementation, incident diagnosis, final QA, release approval, or an
  external action is requested.

## Required Inputs

Require:

1. the approved objective, source reference, current approval state, and an
   authorized artifact owner; bind final execution authority only when known;
2. observable success criteria, explicit non-goals, must-preserve behavior, and
   acceptable tradeoffs;
3. current-state evidence for the affected system, workflow, or operating
   process, including interfaces and already satisfied prerequisites;
4. authority boundaries, allowed read and write scope, external-action gates,
   and irreversible or safety-sensitive boundaries;
5. available role owners, independent verification owner, resource constraints,
   and any fixed horizon that is actually evidenced;
6. known inputs and outputs, assumptions, unresolved facts, failure paths, and
   required downstream handoff shape.

If an input is unavailable, record it as `unknown`; do not fabricate an owner,
duration, interface, approval, or success threshold to make the plan appear
complete.

## Evidence Priority

Rank planning evidence from strongest to weakest:

1. approved objective, outcome contract, non-goals, policy, and authority
   boundaries from their named owners;
2. current direct inspection of the in-scope system, repository, runtime, or
   operating state;
3. verified interface contracts and accepted outputs from prerequisite work;
4. measured capacity, prior execution data on materially comparable work, and
   focused technical evidence;
5. estimates with an owner, basis, range, and recheck trigger;
6. unsupported dates, generic templates, analogy, preference, and opinion.

Higher-ranked evidence constrains lower-ranked planning assumptions. A stale
contract, unmatched prior estimate, or worker report is not current-state proof.
For reused evidence, retain its original source, rationale, counterevidence,
scope, freshness, and supersession state; a past topology is not a default.
Keep `known`, `inferred`, and `unknown` separate throughout the plan.

## Step-By-Step Method

1. **Bind the objective.** Copy the objective, source reference, decision owner,
   success criteria, non-goals, and must-preserve behavior without paraphrasing
   them into a broader or easier target.
2. **Set the two gates independently.** Use the canonical
   `plan_artifact_readiness` and `execution_startability` definitions in the
   Planning contract; do not restate or override them in this pack. A complete
   plan does not make execution startable. A reversible, source-backed
   recommendation may be ready under its authorized artifact owner while final
   execution authority is unknown; label execution blocked and never imply
   approval. Apply the blocked-state rule before mutation.
3. **Build a provisional topology.** Map every criterion to a delivery and proof
   target; mark uncovered criteria and blocked or unknown edges. This topology
   is not a handoff until readiness permits executable leaves.
4. **Define milestones as state changes.** Each milestone must name an
   observable transition, required incoming artifacts, exit evidence, and the
   next consumer. Calendar labels, team names, and aspirations are not
   milestones.
5. **Decompose proposed leaves.** Each proposed leaf
   records:
   - `id`, stable `criterion_id`, objective contribution, why it exists, and concrete first action;
   - required inputs and satisfied prerequisites;
   - read, write, responsibility, and external-action scope;
   - before/action/after state transition, observable done criteria, and
     no-action and abort paths for a mutation;
   - dependency inputs and produced handoff output;
   - verification method, evidence target, and falsification signal;
   - a binary completion observable that a verifier can answer true or false;
   - the contract-defined assignment tuple, independent verifier, risks, stop
     condition, and escalation trigger. Keep candidate facts out of the runtime
     invariant schema.
6. **Stop decomposition at the handoff boundary.** A leaf is small enough when
   one functional owner role with one named-assignee state can start it without
   another planning decision and its evidence can be judged on the matching
   surface. Split for distinct ownership, authority, or independently deliverable
   outcomes. Several failure paths within one coherent outcome belong in that
   leaf's checks and containment, not automatically in separate leaves.
   Material claims need a different accountable verifier. The existing
   [Company direct-work exception](../../../company-orchestration/SKILL.md#choose-the-organization-for-the-goal)
   permits only an exact, low-impact local replacement with the assignee's
   deterministic diff check. It is not independent QA. Keep emitted executable
   leaves' runtime verifier invariant intact; do not invent a verifier to fit it.
7. **Close only necessary dataflow edges.** Add `A -> write artifact -> B read
   artifact -> observation -> assignment tuple` only
   when B consumes A's output. Record coordination preferences separately and
   identify parallel, contract-first, and intentionally serial work.
8. **Check feasibility and containment.** Test the graph against scope,
   capacity, authority, irreversible actions, shared resources, rollback needs,
   and unresolved assumptions. Do not turn an unavailable assignee or unknown
   duration into an optimistic date.
9. **Choose the smallest complete topology.** Remove leaves that do not cover a
   success criterion, preserve a must-preserve behavior, reduce a named risk,
   produce a required handoff, or prove a material non-goal absent. Scope
   reduction may simplify delivery but may not redefine success or lower the
   requested final quality.
10. **Compile role handoffs.** Only when execution startability is `allowed`,
    give each functional owner role and named assignee the inputs, scopes, done
    criteria, output contract, stop conditions, and proof obligations it needs.
    Keep execution ownership and independent verification ownership distinct,
    and preserve the current runtime invariant schema rather than copying
    candidate assignment facts into it.
11. **Run a startability review.** Independently ask whether the artifact is
    complete enough to hand back for decision and whether every first leaf may
    start from existing evidence. Review each later producer, criterion proof,
    material non-goal absence proof, assignment fact, and failure stop or
    escalation path. Set execution startability to `blocked` rather than
    converting a plan-completeness result into execution authorization.
12. **Route without approving.** Return the plan to the authorized decision owner when intent or the
    verification bar must change; otherwise hand executable leaves to
    the assigning lead while preserving Planning's forbidden claims.

## Options And Tradeoffs

- **Thin vertical slice:** proves an end-to-end path early and exposes
  integration risk, but may defer reusable foundations and support fewer cases.
- **Contract-first parallel plan:** lets multiple roles proceed against frozen
  interfaces, but requires interface ownership and creates rework if the
  contract is still an assumption.
- **Foundation-first sequence:** reduces repeated infrastructure work, but
  delays outcome evidence and can overbuild beyond the approved criterion.
- **Bounded spike before commitment:** resolves one high-value execution
  unknown cheaply, but produces evidence rather than a shippable outcome and
  must have a stop condition.
- **Serial containment:** lowers collision, migration, or irreversible-action
  risk, but lengthens the critical path.
- **Parallel execution:** shortens elapsed time when outputs are independent,
  but increases coordination and shared-resource risk.

Select by criterion coverage, reversal risk, and evidence—not by a preferred
delivery style. Preserve at least one serious topology alternative when its
tradeoff could change the sequence.

Read [optional methods](../optional-methods.md) only when they could change a material unresolved choice; skip them for settled work.

## Common Failure Patterns

- converting an unapproved idea into an execution plan;
- calling phases such as "backend," "frontend," or "polish" milestones without
  state transitions or handoff artifacts;
- writing leaves such as "implement feature" with no first action, scope, done
  criteria, or failure path;
- creating dependency edges because work is related rather than because an
  output is consumed;
- assigning the same actor to implement and independently verify the leaf;
- treating a build, mock, fixture, or worker receipt as proof of another
  verification surface;
- inventing estimates, owners, paths, thresholds, or approvals;
- hiding a target, scope, policy, or verification-bar change inside
  "implementation detail";
- listing every possible task instead of the smallest set that covers the
  approved outcome;
- reporting a completed plan as execution success or final verification.

## Output Contract

Return the Decision Core first. Expand the following only to the depth needed
to make the selected topology startable or falsifiable:

- `objective_binding`, `decision_owner`, `plan_artifact_readiness`,
  `execution_startability`, `known`, `inferred`, and `unknown`;
- `in_scope`, `non_goals`, `must_preserve`, authority boundaries, and external
  actions requiring approval;
- a provisional criterion-coverage topology linking each success criterion to
  delivery and matching proof, including blocked or unknown edges;
- a milestone DAG with closed write/read/observability/assignment dataflow edges,
  parallel groups, and critical-path uncertainty;
- proposed leaves and failure design even when execution startability is
  blocked; executable handoff leaves only when it permits, with mutation,
  no-action, abort transitions where applicable, and binary completion observables;
- absence proof for every material non-goal;
- the selected topology, serious alternative, and evidence-backed tradeoff;
- assumption and risk registers, stop criteria, replan triggers, and the authorized decision owner
  re-entry triggers;
- the contract-defined candidate assignment tuple for each assignment, kept
  separate from runtime invariant fields; independent-verifier split, handoff
  order, confidence, residual unverified areas,
  `next_recommended_surface`, and `forbidden_claims`.

When a role handoff is requested, also preserve every required field of
`agent_company_bounded_handoff.v0.1`.

## Stop Or Escalate

Stop and return a bounded plan once plan-artifact readiness and execution
startability are both explicit. Escalate a changed objective, non-goal, must-preserve
behavior, acceptable risk, or verification bar to the authorized decision owner; missing factual state
to bounded research or a bounded domain specialist; materially contested topology to
bounded evidence debate; and execution plus independent verification to the assigning lead.
Stop before implementation, gate approval, final verification, or any
unapproved external action.
