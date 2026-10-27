# Test Strategy

- Reference ID: `task-pack:qa-release:test-strategy`
- Role: `qa-release`
- Required kernel: `role-kernel:qa-release`
- Task type: `test-strategy`
- Decision: which smallest risk-based set of independent checks can falsify the
  acceptance claims for the exact candidate, and what remains unverified?

Turn acceptance criteria and change risk into the smallest independent
falsification strategy; a green suite does not prove an unobserved surface.

## Decision-First Verification Ledgers

Use separate plan, observation, evidence-fact, risk/boundary, blocker, and
decision ledgers. Supporting facts retain supplied IDs and claim scope but do
not set criterion status. Add explicit closure for every named dimension; do
not use catch-all coverage or add criteria that were not supplied.

## Exact Triggers And Non-Triggers

Use this pack when:

- a change or release candidate needs a proportional test plan before or during
  verification;
- risk must be allocated across invariant, boundary, integration, regression,
  and matching-surface checks;
- an existing suite may share fixtures, mocks, implementations, or assumptions
  with the code under test and test independence must be assessed;
- a regression needs a durable oracle, negative control, and adjacent-invariant
  coverage;
- time or surface availability requires explicit prioritization and residual
  risk rather than an unsupported all-clear.

Do not use it when:

- product intent or the acceptance oracle is materially ambiguous; return to
  the authorized decision owner or Planning;
- the main question is how to observe Simulator, physical-device, permission,
  StoreKit, deep-link, or external iOS behavior; use
  `task-pack:qa-release:ios-matching-surfaces`;
- the main question is archive, signing, App Store Connect, review, rollout, or
  go/no-go evidence; use `task-pack:qa-release:release-readiness`;
- the request is to implement a feature or repair a defect rather than
  independently verify it;
- the proposed check would mutate protected production data, submit or release
  a build, accept an agreement, or widen scope without approval.

## Required Inputs And Verification Evidence

Require:

1. acceptance criteria, non-goals, severity of failure, affected users and data,
   and an observable pass/fail oracle;
2. exact candidate identity: `app_id`, `version`, `build`, full `git_commit`,
   `source_state_sha256` covering tracked changes, untracked content, and
   deletions, and `configuration`;
3. changed behavior, diff and dependency boundaries, callers, state owners,
   persistence and external seams, and known adjacent invariants;
4. supported environments, fixtures, feature flags, account or data states,
   concurrency and lifecycle conditions, and the matching surface for each
   criterion;
5. existing tests, recent failures, flaky-test history, production or incident
   evidence with provenance, rationale, freshness, supersession state, and known
   coverage gaps;
6. approved read/write scope, destructive-action limits, test-data policy,
   cleanup requirement, time budget, stop condition, and independent verifier;
7. a resolver-materialized Current Source Set when the oracle depends on
   current SDK, OS, toolchain, service, policy, or dependency behavior.

Retain candidate-bound evidence for each check: criterion and risk IDs, test
layer, initial state, action or exact command, observed result, evidence ref,
cleanup, stop condition, timestamp or run identity, and status of `passed`,
`failed`, `blocked`, or `unverified`. A planned check is not an observed result.

## Evidence Priority

Rank evidence from strongest to weakest:

1. repeatable observation on the exact candidate at the matching surface with
   an independent oracle and controlled initial state;
2. integration or contract checks across the actual changed boundary, including
   persistence, lifecycle, failure, and recovery effects;
3. regression checks that fail for the intended reason before the repair and
   pass after it, with negative controls and adjacent invariants;
4. focused invariant and boundary tests with realistic inputs and deterministic
   state;
5. broader suite, static analysis, type checking, build, and packaging results,
   limited to what their assertions directly prove;
6. historical coverage, code coverage percentage, prior-candidate results,
   worker receipts, screenshots without an oracle, and completion summaries.

Prefer evidence that can falsify a high-impact claim. Coverage volume and test
count do not compensate for a missing boundary or matching surface.

## Risk Model And Test Layers

For each criterion, record failure impact, likelihood, detectability before
release, blast radius, reversibility, and evidence confidence. Use the ranking
to choose depth; do not hide judgment behind an unexplained numeric score.

- **Invariant/unit:** pure rules, normalization, state transitions, and error
  mapping. Fast and diagnostic, but weak for wiring and environment behavior.
- **Boundary/contract:** serialization, repositories, adapters, permissions,
  clocks, files, network contracts, and typed failures. Include malformed,
  empty, maximum, stale, duplicate, unauthorized, cancelled, and partial input
  where applicable.
- **Integration:** real owned components across persistence, process, lifecycle,
  retry, concurrency, migration, restore, and failure seams. Verify side effects
  and atomicity, not only the returned value.
- **Matching surface/end to end:** the actual user-visible or external surface
  named by the criterion. It proves only the observed path, environment, and
  state. A manually assisted step, harness-only invocation, or direct component
  call must be labeled and cannot stand in for an unobserved product path.
- **Regression:** the smallest durable reproduction of the prior failure plus
  controls showing the detector is meaningful and unrelated behavior remains
  stable.

Test independence means the oracle does not merely repeat the implementation.
Prefer a second observation path, fixture created independently of the
production encoder, before/after state inspection, externally visible effects,
or an independent evaluator. Reset shared state and control time, randomness,
ordering, network responses, and retries. Record when perfect independence is
impossible and how correlated failure risk is bounded.

## Current Source Set Recheck Conditions

Refresh a stale, conflicting, or inapplicable platform, toolchain, service, or
policy source before it sets the oracle; it never proves candidate behavior.

## Step-By-Step Method

1. **Bind scope and candidate.** Record the complete candidate identity,
   acceptance criteria, non-goals, authority, cleanup, and stop condition.
   Reject mixed-candidate or stale evidence.
2. **Build the risk ledger.** For each criterion list failure mode, impact,
   likelihood, detectability, blast radius, reversibility, and evidence gap.
3. **Map the impact surface.** Trace changed code and configuration through
   callers, boundaries, persistence, lifecycle, external dependencies, and
   user-visible effects. Mark assumptions and unowned seams.
4. **Choose the oracle.** Define observable success and failure before choosing
   a tool. Prefer state or behavior outside the implementation under test.
5. **Select the cheapest falsifier.** Start at the lowest layer that can directly
   falsify the claim, then add integration or matching-surface checks where a
   lower layer cannot represent the material risk.
6. **Design boundaries and controls.** Cover valid, invalid, empty, maximum,
   duplicate, unauthorized, interrupted, retry, cancellation, and recovery
   states that are material. Add one negative control for the detector.
7. **Secure regression value.** For a repaired defect, establish that the
   regression fails for the intended reason on the pre-fix state or a faithful
   reproduction, then passes on the exact candidate.
8. **Assess independence.** Identify shared fixtures, encoders, mocks, schemas,
   clocks, caches, and implementation-derived expectations. Add an independent
   construction or observation path where correlated error would matter.
9. **Order execution by information value.** Run deterministic focused checks
   first, then boundary and integration checks, then expensive matching
   surfaces. Stop early only when the recorded stop condition is met.
   The smaller set must preserve the requested quality and acceptance bar.
10. **Capture observations.** Preserve commands, environment, initial state,
    actual outcomes, candidate binding, sanitized artifacts, cleanup, failures,
    flake repetitions, and skipped surfaces.
11. **Classify without averaging.** Keep each criterion `passed`, `failed`,
    `blocked`, or `unverified`. One high-severity missing surface is not offset
    by many low-risk passes.
12. **Handoff independently.** Report partial success, residual risk, smallest
    next check, and `next_recommended_surface: company-lead`; do not score your
    own work as final verification.

## Options And Tradeoffs

Choose focused, integration, contract-double, generative, or golden checks by
their material falsification power; document isolation, source, and oracle
limits rather than treating their output as universal proof.

Read [optional methods](../optional-methods.md) only when they could change a material unresolved choice; skip them for settled work.

## Common Failure Patterns

- treating build success, coverage percentage, or suite size as product proof;
- testing implementation details with the same algorithm or fixture generator
  as production and calling the result independent;
- omitting failure, retry, cancellation, partial-write, restore, or boundary
  states because the happy path is green;
- writing a regression that passes before the fix or fails for an unrelated
  setup reason;
- replacing an unavailable device, account, permission, purchase, or external
  surface with a mock while retaining the original claim;
- rerunning flakes until green without reporting frequency, seed, or failure;
- combining results from different commits, dirty worktrees, builds, flags, or
  configurations;
- erasing passed evidence when one check fails, or averaging a blocker into a
  readiness percentage;
- leaving fixtures, accounts, screenshots, files, permissions, or Simulator
  state dirty;
- claiming no regressions, release readiness, product success, or final
  verification from the strategy or its executor.

## Output Contract

Return candidate-bound plans and observations separately, one criterion/risk
closure per named dimension, all terminal statuses, residual risk, cleanup,
independent verifier, `next_recommended_surface`, and `forbidden_claims`.

## Stop Or Escalate

Stop and escalate when candidate identity cannot be bound, the acceptance oracle
is disputed, a material matching surface is unavailable, safe isolation or
cleanup cannot be guaranteed, required evidence would expose secrets or
personal data, current-source drift can change the oracle, or continuing would
require unauthorized implementation, production mutation, submission, release,
or account action. Route intent and acceptable-risk questions to the authorized decision owner, missing
facts to bounded research, contested tradeoffs to bounded evidence debate, and execution plus
final verification to the assigning lead. A bounded `blocked` or `unverified` result
with preserved partial success is valid.

## Compression Examples

**Good:** "Candidate `com.example.notes` 2.4.0 (81), commit `4a21bd0…`,
source-state digest `9f2c…`, Release-Staging, changes archive decoding and one
transactional import seam. Data loss makes malformed, duplicate, oversized,
interrupted, and rollback cases highest risk. Parser invariants are necessary
but insufficient: independently authored fixtures cross the decoder boundary,
and a local-store integration check must prove no partial write after failure
and identical state after reload. The prior corrupt-archive regression must
fail on the faithful pre-fix candidate and pass here; a valid-archive negative
control must still import once. Device UI import remains unverified and cannot
be inferred from the green local suite. Preserve the passed parser and store
evidence, then send the candidate-bound gap to the assigning lead."

**Bad:** "Unit tests and the build pass with 92% coverage, so the change is
fully regression-safe and ready to ship."
