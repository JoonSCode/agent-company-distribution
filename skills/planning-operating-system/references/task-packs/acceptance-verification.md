# Acceptance And Verification

- Reference ID: `task-pack:planning:acceptance-verification`
- Role: `planning`
- Required kernel: `role-kernel:planning`
- Task type: `acceptance-verification`
- Decision: what observable evidence, on which matching surface, would let an
  independent verifier accept or falsify each approved success criterion?

This pack designs the verification contract before execution. It does not alter
product intent, run the checks, accept a gate, certify a release, or turn an
executor's receipt into final proof.

## Decision Core

Apply `planning-contract.json#/decision_output_policy`. Lead with the current
verification readiness, the first criterion that cannot yet be accepted, its
matching proof surface, the decisive falsifier, and the independent verifier.
Split only claims that can fail independently. Use the smallest proof stack
that directly covers each claim and state what supplied evidence proves and
does not prove. Do not build rows for hypothetical surfaces merely to make the
matrix look complete.

For promotion work, apply
`planning-contract.json#/promotion_experiment_guidance`. Bind the selected
direction, expression and concept version to their separate proof targets.
File generation, technical QA and policy compliance can establish production
readiness; actual posting or exposure needs external-state evidence, and
interest, app acquisition and payment contribution need their own observed
signals. Preserve the approved early learning objective when downstream
outcomes are still unknown. Reference or page quotas cannot stand in for it.

## Exact Triggers And Non-Triggers

Use this pack when:

- success criteria contain vague terms such as "works," "safe," "fast,"
  "responsive," or "complete";
- a criterion spans static contracts, automated behavior, integrated runtime,
  user-visible states, external accounts, or business outcomes;
- an execution handoff needs explicit evidence targets and falsification
  signals;
- partial evidence must be classified without claiming completion;
- verifier independence, candidate identity, environment, or evidence
  provenance is unclear.

Do not use it when:

- the desired behavior, non-goal, or acceptable verification bar is a product
  decision still awaiting the authorized decision owner;
- the request is to implement the behavior, execute tests, perform manual QA,
  approve release, or report a final verdict;
- milestones and executable leaves are the main gap; use the execution-plan
  pack;
- dependency or rollback topology is the main gap; use the dependency-risk pack;
- a metric definition requires a bounded analytics specialist before the
  criterion can be made observable.

## Required Inputs

Require:

1. the approved objective, each success criterion, non-goals, must-preserve
   behavior, acceptable tradeoffs, and the owner of the verification bar;
2. named actors, preconditions, action or event, expected state transition,
   boundary conditions, failure behavior, and prohibited outcomes;
3. the exact candidate identity or a contract for how it will be captured;
4. available proof surfaces, target environments, fixtures, accounts, devices,
   viewports, cohorts, windows, and data-quality constraints;
5. existing baseline evidence, known defects, instrumentation, and evidence
   retention requirements;
6. executor, independent verifier, gate owner, and any external-action
   authority.

Do not invent thresholds, cohorts, devices, environments, or release states.
If a material oracle is absent, mark the criterion blocked and name the decision
owner.

## Evidence Priority

Apply two rules in order: evidence must match the criterion's surface, then
stronger provenance wins within that surface.

1. approved outcome, policy, and must-preserve contracts define what must be
   proved;
2. direct, auditable observation of the exact candidate on the matching surface
   is strongest for that criterion;
3. integrated runtime evidence supports end-to-end state and interaction claims;
4. focused automated evidence supports the behavior and boundaries it actually
   exercises;
5. static schema, type, lint, and build evidence supports static claims only;
6. fixture screenshots, mocks, worker receipts, and narrative claims are
   preparatory evidence, not substitutes for a different surface.

For an external account or release-state claim, inspect the authoritative
external state. For a product or business outcome, use the defined cohort,
window, denominator, exclusions, and data-quality rules. No amount of lower
surface evidence proves a higher or different surface.

## Step-By-Step Method

1. **Freeze the verification bar.** Record the approved criterion, source,
   owner, non-goals, and must-preserve behavior. A proposed change to any of
   these is material-decision re-entry, not test-plan refinement.
2. **Close each criterion.** Express one observable claim per row as criterion
   → delivery leaf → proof target → verifier, with actor and precondition,
   event, expected state transition, bounds supplied by the owner, prohibited
   outcome, and persistence requirement. Split claims that can fail separately.
3. **Choose the matching proof surface.** Classify each atomic claim as:
   - schema or static contract;
   - focused automated behavior;
   - integrated runtime behavior;
   - user-visible or device observation;
   - external account or release state;
   - product or business outcome.
4. **Define the oracle.** Name what the verifier observes, the expected value or
   state, allowed variance, evidence target, and a falsification signal. Avoid
   judgments such as "looks correct" when a state or comparison can be named.
5. **Bind applicability and lineage.** Mark each surface `applicable` or
   evidence-backed `not_applicable`. For an applicable surface, bind source,
   artifact, configuration, environment, and relevant runtime topology. For a
   non-applicable surface, retain only its reason, evidence reference, and
   decision owner; do not create irrelevant checklist cells. Evidence without
   enough identity to reproduce or attribute remains limited.
6. **Cover positive, negative, boundary, and recovery states.** Include denied
   roles, invalid input, empty and maximum supplied bounds, interruption,
   retry, rollback, persistence, must-preserve regression, and—for a mutation—
   no-action and abort transitions. For every material non-goal, define the
   prohibited effect and a direct absence proof. Do not generate irrelevant
   cases merely to increase count.
7. **Specify the evidence procedure.** Give the verifier a start state, action,
   observation point, evidence capture, cleanup or containment, and stop rule.
   Distinguish executor-produced diagnostics from verifier-produced evidence.
8. **Enforce independence.** The executor may provide candidate identity,
   commands, fixtures, logs, and a self-check. A different accountable verifier
   must independently reproduce or directly inspect the decisive evidence.
   For only an exact, low-impact local replacement, the existing
   [Company direct-work exception](../../../company-orchestration/SKILL.md#choose-the-organization-for-the-goal)
   permits the assignee's deterministic diff check instead. Label its narrow
   proof honestly, not independent QA; material technical/outcome claims and
   emitted executable-leaf runtime invariants retain independent verification.
   The gate owner remains separate from both when the governing contract
   requires it.
9. **Classify evidence per criterion.** Use `pass`, `fail`, `blocked`, or
   `unverified`. `Pass` requires matching evidence from the independent
   verifier, or only the narrow direct-work diff check allowed above. Do not
   average criteria, convert a blocked row to pass, or let a
   low-surface pass mask a runtime failure.
10. **Make partial evidence explicit.** Record what a build, unit test, mock,
    screenshot, or receipt does prove and the exact claims it leaves unverified.
11. **Define completion and re-entry separately.** Completion requires every
    required criterion to meet its bar and residual areas to be dispositioned
    by the authorized verifier or gate owner. A changed bar, accepted exception,
    or removed criterion returns to the authorized decision owner.
12. **Hand off without judging.** Send the evidence plan to the assigning lead and
    the independent verifier. Planning proposes the bar and coverage; it does
    not execute or approve the verdict.

## Options And Tradeoffs

- **Static contract checks:** fast and deterministic for schema, type, or policy
  shape, but say nothing about runtime integration unless that is the claim.
- **Focused automated checks:** repeatable and precise for state transitions and
  boundaries, but can miss environment, wiring, and user-visible defects.
- **Integrated runtime checks:** exercise real component interaction, but cost
  more to prepare and can be harder to diagnose.
- **Manual device or viewport observation:** captures visual and interaction
  reality, but needs exact scenarios and durable evidence to be reproducible.
- **External-state inspection:** is required for account, submission, serving,
  or release claims, but may be approval-gated and temporally unstable.
- **Product or business outcome measurement:** proves the outcome at the defined
  cohort and window, but arrives later and depends on trustworthy
  instrumentation.

Use the smallest proof stack that directly covers the claim. More checks are not
better when they inspect the wrong surface.

## Common Failure Patterns

- using "works as expected" or "looks good" as an acceptance oracle;
- declaring the whole objective complete because a build or focused test passes;
- treating mocks, fixtures, screenshots, or worker receipts as integrated
  runtime or external-state proof;
- letting the executor be the sole verifier outside the narrow direct-work
  diff-check exception, or presenting that self-check as independent QA;
- failing to identify the exact candidate, environment, account role, or data;
- omitting denied, failure, boundary, persistence, or must-preserve states;
- changing a threshold, cohort, viewport, or criterion after observing results;
- collapsing `blocked` or `unverified` into pass;
- reporting a plan or evidence inventory as final QA or gate approval;
- collecting sensitive or external evidence without authority or containment.

## Output Contract

Return the Decision Core first. Expand only atomic criteria and proof surfaces
needed for an independent accept-or-falsify decision:

- `objective_binding`, verification-bar owner, `known`, `inferred`, `unknown`,
  and planning readiness;
- an atomic acceptance matrix with criterion ID, delivery leaf, proof target,
  verifier, actor and precondition, event, expected transition, bounds,
  prohibited outcome, non-goal, and must-preserve link;
- for each criterion: proof surface applicability, source/artifact/config/
  environment/runtime-topology lineage where applicable, procedure, oracle,
  evidence target, falsification signal, executor artifact, independent
  verifier, and status vocabulary;
- positive, negative, boundary, recovery, regression, no-action, and abort
  coverage where applicable, plus non-goal absence proofs;
- a proof-surface coverage summary that names substitutions that are not
  allowed;
- partial evidence classified by what it proves and what remains unverified;
- evidence retention, external-action gates, stop rules, residual gaps, the authorized decision owner
  re-entry triggers, `next_recommended_surface`, and `forbidden_claims`.

When a role handoff is requested, also preserve every required field of
`agent_company_bounded_handoff.v0.1`.

## Stop Or Escalate

Stop once every approved criterion has a reproducible oracle, matching surface,
falsification signal, and independent verification owner, or is explicitly
blocked. Escalate missing factual evidence to bounded research, contested
interpretation to bounded evidence debate, metric-definition needs to the bounded analytics
specialist, and any changed criterion, exception, risk tolerance, or
verification bar to the authorized decision owner. Route execution and final independent verification
to the assigning lead. Stop before running external actions, approving a gate,
certifying a release, or claiming completion.

## Compression Examples

**Good:** "AC-2 requires a non-owner to receive denial and create no audit-side
effect on the integrated candidate. The executor's mocked unit test supports
the authorization branch only; its fixture screenshot proves neither runtime
denial nor persistence. QA-Release, independent of the implementer, must test
the exact candidate as owner and non-owner, inspect the resulting audit state,
and capture both observations. Until candidate identity and integrated evidence
exist, AC-2 is unverified—not failed or passed."

**Bad:** "The developer says tests pass and attached a screenshot, so acceptance
is complete. QA can approve it later if needed."
