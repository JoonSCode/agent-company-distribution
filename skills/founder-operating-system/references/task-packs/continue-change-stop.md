# Continue, Change, Or Stop

- Reference ID: `task-pack:founder:continue-change-stop`
- Role: `founder`
- Required kernel: `role-kernel:founder`
- Decision: should an existing initiative continue unchanged, change one
  material hypothesis, pause, or stop?

This pack makes continuation falsifiable. It does not move thresholds after the
fact, authorize a pivot, or claim that execution or causality is verified.

## Exact Triggers

Use this pack when:

- a predefined experiment, milestone, spend stage, or review horizon has ended;
- success, failure, kill, safety, runway, or capacity evidence has materially
  changed;
- the CEO requests a continue, change, pause, harvest, or stop recommendation;
- new disconfirming evidence may reverse an active commitment.

Do not use it when:

- an experiment is still inside its valid window and no safety, cash, or kill
  boundary was crossed;
- the request is incident diagnosis, implementation status, or release
  verification;
- unrelated opportunities need selection; use the portfolio-decision pack;
- there was no prior hypothesis or criterion and the real need is discovery or
  Uigwe clarification.

## Required Inputs And Evidence Hierarchy

Require:

1. the original hypothesis, segment, wedge, owner, time window, and
   decision-authorized scope;
2. precommitted success, failure, kill, safety, and revisit criteria;
3. actual numerator, denominator, cohort, source, date, spend, time, and missing
   data;
4. interventions, outages, scope changes, subsidies, or contamination during the
   test;
5. attributable customer or buyer behavior and matched qualitative evidence;
6. remaining runway or capacity, obligations, exit cost, recoverable assets,
   and the best use of released resources.

Rank evidence from strongest to weakest:

1. precommitted criteria matched to auditable outcome data on the named cohort;
2. transactions, retention, repeated use, switching, and other costly behavior;
3. matched field observation or buyer evidence that explains, but does not
   overwrite, the outcome;
4. credible evidence for a distinct alternative hypothesis or segment;
5. post-hoc stories, opinions, sunk cost, anecdotes, and optional frameworks.

Preserve `known`, `inferred`, and `unknown`. A plausible explanation is not a
verified cause.

## Decision Method

1. **Freeze the original contract.** Quote the original hypothesis, window, and
   criteria before inspecting the preferred story.
2. **Validate comparability.** Check cohort, denominator, instrumentation,
   intervention, sample, and missingness. Mark the result `valid`, `partially
   valid`, or `invalid`.
3. **Classify the outcome.** Record which thresholds were met, missed, crossed,
   or remain unobserved. Do not average away a kill or safety breach.
4. **Separate failure types.** Distinguish evidence for hypothesis failure,
   execution failure, measurement failure, and an inconclusive test. Preserve
   alternative explanations.
5. **Recalculate opportunity cost.** Compare the next unit of effort with pause,
   stop, harvest, and the best serious alternative; exclude sunk cost from the
   forward case.
6. **Evaluate four real actions.**
   - Continue only when success criteria hold and disconfirmation is bounded.
   - Change only when one material bottleneck has evidence and a cheaper
     discriminating test.
   - Pause when evidence is invalid or temporarily unavailable and preserving
     the option is cheaper than forcing a conclusion.
   - Stop when a kill or safety criterion is crossed, the core hypothesis is
     disconfirmed, or no cheaper decision-grade test remains.
7. **Guard target changes.** A new user, problem, promise, business model, or
   verification bar is a new hypothesis requiring Uigwe re-entry, not a renamed
   continuation.
8. **Bind the next boundary.** For continue, change, or pause, define one owner,
   time box, resource cap, success, failure, kill, and revisit trigger. For stop,
   define obligations, asset preservation, customer handling, and released
   capacity without authorizing external action.
9. **Route the recommendation.** Return evidence and the required next surface;
   do not execute or self-verify it.

## Serious Alternatives And Tradeoffs

- **Continue unchanged:** preserves momentum and clean learning continuity, but
  compounds exposure if evidence no longer supports the hypothesis.
- **Change one variable:** can isolate a plausible bottleneck, but resets part of
  the evidence base and can hide a target change.
- **Pause and repair evidence:** protects against false conclusions, but incurs
  delay and holding cost.
- **Stop or harvest:** releases capacity and caps downside, but creates exit
  costs and may forfeit option value or customer trust.

An alternative is serious only if it is feasible under current constraints and
has a named condition under which it beats the recommendation.

## Common Failure Patterns

- citing time, effort, ownership, or embarrassment as a reason to continue;
- moving success criteria or narrowing the denominator after seeing results;
- calling a failed test "execution failure" without causal evidence;
- changing segment, offer, price, and channel together and calling it iteration;
- treating early noise as a stop signal before the valid window closes;
- ignoring safety, runway, contractual, customer, or exit obligations;
- reporting a new target segment as the same initiative to avoid Uigwe re-entry;
- equating worker completion with verified outcome.

## Output Contract

Return:

- `original_hypothesis`, `original_criteria`, `observed_results`, and
  `evidence_validity`;
- a threshold-by-threshold comparison with `known`, `inferred`, and `unknown`;
- `recommended_action` as `continue`, `change`, `pause`, or `stop`, plus
  `strongest_support`, `strongest_disconfirmation`, and `serious_alternative`;
- `failure_type_evidence`, `assumptions`, `opportunity_cost`, `released_or_used_capacity`,
  `residual_risk`, and exit obligations;
- the `next_reversible_commitment` or bounded stop sequence, with owner, horizon,
  resource cap, success, failure, kill, and revisit criteria;
- `decision_readiness`, `confidence`, `next_recommended_surface`, and
  `forbidden_claims`.

When a role handoff is requested, also preserve every required field of
`agent_company_bounded_handoff.v0.1`.

## Stop Or Escalate

Stop and return to the Sejong lead once the recommendation is bounded. Escalate
invalid or missing outcome evidence to JangYeongsil or the appropriate analytics
specialist; contested causal interpretation to Jiphyeonjeon; any goal, target,
scope, risk, or verification-bar change to Uigwe; and verification readiness to
Seungjeongwon. Stop immediately at a safety or kill boundary, or before any
unapproved external action. Do not approve closure or completion.

## Compact Example

**Good:** "Stop the original segment: its precommitted kill rule was fewer than
one payment after 15 qualified calls and five activated trials; observed results
were zero after 22 and seven. The comments suggest suite overlap, but causality
is inferred. Two requests from a new segment justify only a separate one-week
buyer test through Uigwe, capped at 12 hours. The prior 96 hours are sunk."

**Bad:** "We already spent five weeks, and a different customer type sounded
interested. Continue the same initiative with a new segment, price, and channel
until revenue appears."
