# Experiment And Growth

- Reference ID: `task-pack:marketing:experiment-growth`
- Role: `marketing`
- Required kernel: `role-kernel:marketing`
- Experiment contract: marketing-contract.json#/experiment_contract
- Task type: `experiment-growth`
- Decision: which diagnosed funnel, retention, channel, or growth-system
  assumption should one bounded experiment resolve next?

This pack turns an approved early hypothesis or observed performance into a
decision-grade learning loop. It
does not convert attribution into causality, call every funnel a loop, approve
spend, mutate a live account, or claim that an executor's result is verified.
When an external post, thread, deck, newsletter, case study, or practitioner
recipe motivates the work, load
[../channel-evidence-intake.md](../channel-evidence-intake.md) before treating
any claim as operational. For Apple Ads search results, Search Match,
search-term mining, exact promotion, negative-keyword fencing, or ASO feedback,
also load
[../apple-ads-search-intent-playbook.md](../apple-ads-search-intent-playbook.md).

## Decision Core

Apply `marketing-contract.json#/decision_output_policy`. Lead with the observed
metric fact, the denominator and cohort that make it interpretable, the
selected constraint, the strongest rival explanation, and the one experiment
that can distinguish them. Audit measurement before explaining movement.
Change one reversal assumption, keep other decision inputs fixed, and
precommit win, loss, and inconclusive actions. Do not turn every available
metric into a dashboard or every possible intervention into an experiment.

For an approved first promotion experiment with no baseline, lead with the
selected learning question and label the missing baseline. Unknown eventual
revenue is not evidence that the approved early test is unstartable. Keep
scale and causal claims conditional on their own evidence and authority.

## Promotion Exploration Before Test Selection

Use `marketing-contract.json#/creative_exploration_contract` when the requested
deliverable is creative exploration. Keep its linked layers in job evidence;
do not add fields to the existing runtime experiment blueprint.

First compare distinct hypotheses about who, in what situation, and with what
emotion or desire would notice, share, and become curious about the problem or
app. Then propose expression options within each direction, and concrete
scene sequences beneath the expressions. A template family or an image type
is an expression choice, not an audience-interest direction. One bounded
exploration artifact can contain this comparison before one test is selected.

Carry the CEO's chosen first expression into that comparison and execution
plan. For example, reinterpreting a TikTok trend's narrative sequence can be an
explicit experiment choice based on user-provided indirect experience. Keep
that provenance and uncertainty; it is neither an observed result nor a
standing requirement for every campaign. Reinterpret the mechanism using
original or authorized assets, without assuming permission to repost a video
or copy its assets. Label unobserved references instead of inventing them.

Hand Design the direction, relevant product truth, reference mechanism and
transfer limits. Design specifies image type, app-screen share and appearance
timing, composition, narrative progression and the intended action per scene.
Select that expression for its marketing reason before fitting a renderer;
existing card roles and page counts must not determine the campaign thesis.
Use only product facts that support the message; keep internal correctness
checks available to QA without turning them into mandatory copy.

Record actual references collected and selected, including incomplete viewing,
using the channel intake. Counts describe coverage and must not replace the
first experiment's objective. Once selected, bind the tested concept/version
to the canonical experiment contract. Record actual posting or exposure,
leading reach/sharing, problem or app interest, app acquisition, and payment
contribution only where observed. Keep denominators, windows and gaps explicit.
Technical QA, policy checks and generated files prove only their own surfaces.

## Exact Triggers And Non-Triggers

Use this pack when:

- approved early promotion hypotheses need direction, expression and concept
  exploration before an actual posting experiment;
- a funnel, acquisition, activation, retention, referral, or revenue metric
  changed and the next decision is unclear;
- a channel needs a precise job and a bounded test rather than a generic growth
  plan;
- several causal explanations compete for one observed bottleneck;
- a proposed growth loop needs proof that its output replenishes an input;
- a campaign, product, or lifecycle intervention needs success, failure,
  downstream-quality, trust, and next-decision rules.
- Apple Ads discovery terms need a source-bounded `observe`, `promote_exact`,
  `exclude`, or `continue_observing` decision.

Do not use it when:

- audience, problem, alternatives, or position could reverse the strategy; use
  `task-pack:marketing:demand-positioning`, unless those uncertainties are the
  explicitly approved learning target of this bounded early experiment;
- only copy craft remains after strategy is settled; use
  `copywriting-operating-system`;
- paywall, price, package, offer, or mobile monetization economics is the
  primary decision; use `task-pack:marketing:mobile-monetization`;
- the request is only metric implementation, data-pipeline repair, final QA,
  release approval, or a live channel action;
- a fixed allocation is requested without baseline spend, marginal response,
  retained or paid-user quality, payback or LTV, cash constraints, channel
  capacity, and a cohort-maturity horizon. That allocation is `blocked`.

## Required Inputs

Require:

1. the decision question, product stage, business outcome, primary objective,
   non-goals, and decision owner;
2. an event and metric dictionary with numerator, denominator, unit, source,
   timestamp, exclusions, identity and deduplication rule;
3. raw counts and comparable cohorts by relevant date, segment, country,
   channel, product version, paid or organic source, and maturity;
4. the current journey, core value action, natural cadence, activation and
   retention definitions, and known failure states;
5. baseline or comparison evidence, intervention history, assignment or
   exposure mechanism, sample limits, and conversion lag;
6. channel spend and capacity, marginal performance, CAC, LTV or payback, and
   cash limits when allocation or scale is in scope;
7. qualitative evidence, tracking defects, simultaneous changes, privacy,
   consent, trust, brand, and downstream-quality constraints.

Missing definitions stay `unknown`. Never infer a causal mechanism or invent a
threshold, duration, sample size, budget, or cohort maturity.

## Evidence Priority

Rank evidence from strongest to weakest:

1. valid randomized or controlled lift with known exposure, comparable
   assignment, sufficient observation, and matching downstream outcomes;
2. mature product cohorts and verified transaction, activation, retention, and
   renewal behavior with stable definitions;
3. reproducible funnel diagnostics, user-level event inspection, and controlled
   surface tests;
4. bounded channel tests with known source and downstream quality;
5. calibrated observational cohorts and qualitative behavior evidence;
6. platform attribution, blended averages, clicks, views, rankings, anecdotes,
   and practitioner heuristics.

Operational platform data may describe credited touchpoints. It does not by
itself establish incrementality.

## Step-By-Step Method

1. **Bind the decision.** Name the outcome, stage, next allocation or product
   choice, non-goals, and the observation that triggered review.
2. **Set readiness.** Apply the decision-slice-local readiness rule in
   `marketing-contract.json`; name the reversal link for this growth slice.
3. **Audit the measurement contract.** Recompute rates from raw counts; verify
   numerator, denominator, identity, deduplication, attribution, exclusions,
   event version, cohort entry, maturity, and lag. Isolate broken or changed
   instrumentation before interpreting movement.
4. **Map the system.** Assign each selected channel one job: create demand,
   capture demand, activate, retain, monetize, or enable referral. Use a funnel
   for journey loss and call a mechanism a `growth_loop` only when an observed
   output measurably creates the next input.
5. **Locate the constraint.** Compare absolute loss, trend, segment difference,
   business value, downstream quality, and reversibility. The largest
   percentage drop is not automatically the best intervention point.
6. **Build a hypothesis ledger.** For the focal observation record a causal
   hypothesis, evidence for and against it, rival explanations, and the next
   observation that would distinguish them.
7. **Choose one reversal assumption.** Hold audience, offer, channel,
   measurement, and product state fixed where possible. Reject a multi-variable
   test that cannot support the next decision.
8. **Design the experiment.** Fill the canonical experiment contract, including
   the complete blueprint required for a conditional request.
9. **Precommit interpretation.** A win requires the primary criterion and every
   hard guardrail. A loss is evidence against the tested assumption under the
   observed conditions. An underpowered, contaminated, immature, or conflicting
   result is inconclusive, not a convenient win or loss.
10. **Handle allocation safely.** For missing allocation prerequisites,
    preserve the viable baseline and order learning as baseline audit, smallest
    reversible test, then qualitative scale/hold/stop rules. Name a
    `prospective_observation_horizon` by cohort maturity, not an invented date.
11. **Measure downstream consequences.** Pair the business outcome with a
    leading behavior, activation or retention quality, and a longer-horizon
    signal when relevant. Check adverse segments and consent or trust effects.
12. **Update the decision ledger.** Move only supported findings among `known`,
    `inferred`, and `unknown`; state the next decision and route execution and
    evaluation to separate owners.

## Options And Tradeoffs

- **Randomized holdout or lift test:** strongest causal evidence, but may need
  more traffic, instrumentation, and operational discipline.
- **Product-surface A/B test:** isolates a local intervention when assignment is
  valid, but does not prove channel incrementality or long-horizon value.
- **Comparable cohort analysis:** useful for retention and lagged quality, but
  remains vulnerable to mix and time confounding.
- **Small channel smoke test:** tests access and operational fit cheaply, but
  low volume is often inconclusive and cannot justify scale.
- **Qualitative friction study:** explains where and why users fail, but does
  not estimate lift.
- **Loop validation:** measures replenishment directly, but may reveal that the
  system is only a funnel; that is a valid conclusion.

Select the design that can change the named decision while containing cost,
user harm, contamination, and opportunity cost.

## Common Failure Patterns

- reporting a rate without raw counts, denominator, cohort, or maturity;
- comparing paid and organic, countries, product versions, or acquisition
  periods as though only the intervention differed;
- treating last-click attribution, a pre/post chart, or correlation as causal
  lift;
- optimizing clicks, installs, or local conversion while activation, retention,
  refunds, revenue quality, or trust deteriorates;
- changing targeting, creative, offer, product, and measurement together;
- peeking, stopping early, excluding adverse segments, or relabeling an
  inconclusive result;
- calling referral intent or sharing a growth loop without measured
  replenishment;
- copying a fixed budget formula without marginal economics and capacity;
- using synthetic forward tests as real campaign effectiveness.

## Output Contract

Return the Decision Core, then add only the metric definitions, data-quality
findings, comparable cohorts,
diagnosed constraint, channel jobs, funnel or loop boundary, causal hypothesis,
rival explanation, and allocation prerequisites. A conditional experiment
request must include the complete canonical experiment contract.

The executor may report evidence but may not score its own result. Name an
independent evaluation owner and preserve `agent_company_bounded_handoff.v0.1`
when a role handoff is requested.

## Stop Or Escalate

Stop after one decision-grade experiment or a blocked evidence action is
defined, or after the requested direction/expression exploration is handed
off for selection. An approved outcome request continues through its selected
execution and verification surface. Route missing factual state or analytics evidence to bounded research or
`data-analytics:metric-diagnostics`, material causal disagreement to
bounded evidence debate, changed product intent or risk bars to the authorized decision owner, settled copy to
`copywriting-operating-system`, and approved execution plus independent
verification to the assigning lead. Stop before spend, publication, live account
changes, gate approval, or final performance claims.

## Compression Examples

**Good:** "Readiness is conditional. Search-acquired users show stronger
week-one return than social-acquired users, but country mix and a simultaneous
onboarding change prevent a channel-causality claim. Keep the viable baseline;
do not issue the requested fixed split because marginal response, payback,
capacity, and mature paid-user quality are missing. First repair the duplicate
value event, then randomize one onboarding intervention within comparable
source-country cohorts. Pre-register the material effect and maturity rule;
win only if activation improves without weaker retention or consent."

**Bad:** "Social has the cheapest installs, so move most of the budget there.
The funnel chart proves onboarding is the problem; run several new creatives,
offers, and notifications and scale whichever gets the most clicks."
