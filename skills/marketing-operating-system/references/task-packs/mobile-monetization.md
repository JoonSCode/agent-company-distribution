# Mobile Monetization

- Reference ID: `task-pack:marketing:mobile-monetization`
- Role: `marketing`
- Required kernel: `role-kernel:marketing`
- Experiment contract: marketing-contract.json#/experiment_contract
- Task type: `mobile-monetization`
- Decision: which mobile monetization model, paywall, offer, price, package, or
  cohort test should be run next, if any?

This pack applies the mobile monetization priors without turning them into
promises. It does not set a universal price, copy a benchmark into a target,
authorize paid acquisition, implement billing, certify store compliance, or
claim repeatable economics from first revenue.

## Decision Core

Apply `marketing-contract.json#/decision_output_policy`. Lead with separate
artifact, execution, and scale readiness; the strongest evidence for each; the
single blocking fact; and the next reversible decision. Never let first
revenue, a sandbox purchase, a fresh policy source, or a local conversion win
upgrade another slice. Keep view, trial, settled payment, renewal, refund,
retention, contribution, and marginal acquisition evidence separate. Expand
only the slice requested; preserve the other two as short status boundaries.

## Exact Triggers And Non-Triggers

Use this pack when:

- an iOS or mobile app needs a paywall timing, hard or soft gate, offer, trial,
  package, or price hypothesis;
- subscription, one-time purchase, metered credits, ads, affiliate,
  marketplace, or hybrid models must be compared;
- store, country, category, channel, paywall, trial, or price cohorts need a
  monetization decision;
- first settled revenue must be distinguished from repeatable economics and
  scale readiness;
- paid acquisition is proposed as a monetization learning test or scale input.

Do not use it when:

- the paying problem, reachable payer, or behavioral demand could reverse the
  model; use `task-pack:marketing:demand-positioning`, `problem-discovery`, or
  `commercial-fit`;
- only paywall copy remains after offer and evidence are settled; use
  `copywriting-operating-system`;
- billing implementation, receipt validation, store submission, legal advice,
  live price changes, campaign mutation, or final release verification is the
  request;
- platform policy, eligibility, price tiers, fees, or benchmark methodology is
  material but no fresh Current Source Set is available. Stop for refresh.

## Required Inputs

Require:

1. the `paying_problem`, reachable payer, separate user and beneficiary,
   customer progress, urgency, current alternative, and payment evidence;
2. the value event, natural cadence, payment trigger, variable cost, and why
   the proposed model fits them;
3. current platform, country, category, product stage, monetization model,
   products, packages, prices, offers, trials, paywall type, and relevant
   eligibility constraints;
4. real-device evidence for onboarding, paywall display, purchase, settlement,
   restore, cancellation or refund state, billing failure or retry, and
   analytics;
5. raw cohort counts, acquisition denominator, identity and deduplication,
   paid or organic source, attribution, country, store, channel, paywall,
   price, trial length, entry dates, and maturity rule;
6. activation, retention, renewal, cancellation, refund, billing failure, net
   revenue, contribution, CAC, LTV, payback, cash window, and channel capacity
   when the decision requires them;
7. the resolver-materialized Current Source Set with source authority, URL or
   immutable reference, access date, methodology or denominator, freshness,
   allowed use, and recheck trigger for every policy or benchmark claim.

Record unavailable evidence as `unknown`. Sandbox purchase success is not
settled revenue, and a store download denominator is not an install cohort.

## Evidence Priority

Apply evidence in this order:

1. mature product-specific cohorts with verified purchase, settlement,
   attribution, retention, renewal, refund, and contribution evidence;
2. like-for-like country, store, category, channel, paywall, price, trial, and
   offer evidence from the product;
3. current official platform policy and operational guidance materialized in
   the Current Source Set;
4. current sourced market benchmarks with compatible definitions and
   methodology;
5. internal operating bands and documented practitioner options from
   `mobile-app-monetization-priors.md`;
6. anecdotes, unsourced decks, category folklore, and stale vendor claims.

Higher-ranked evidence overrides lower-ranked priors. Record the override and
next review condition. Vendor evidence is interested evidence; platform
recommendations are not permission to spend.

## Current Source Set Recheck Conditions

Refresh and re-materialize the Current Source Set before a material decision
when any of these is true:

- the decision depends on current store policy, offer or trial eligibility,
  cancellation disclosure, review rules, privacy or attribution behavior,
  price tiers, taxes, commissions, fees, or campaign requirements;
- the source is past its manifest review condition, lacks an access date or
  methodology, or the vendor or platform changed its product or definitions;
- the target country, store, category, channel, paywall, price, trial, or cohort
  denominator differs from the cited source;
- a benchmark, budget multiple, trial duration, conversion band, or named
  service would materially change price, packaging, spend, or scale;
- an official source conflicts with a vendor benchmark or product cohort;
- a policy or benchmark claim will be shown to a user, evaluator, or approver.

Preserve the older source and decision record. Never silently rewrite a past
cohort judgment, invent a current numeric policy, or quote an unmaterialized
benchmark from memory.

## Step-By-Step Method

Start one `agent-company.marketing-decision/v0.1` record using the
decision-scope and decision-slice rules in `marketing-contract.json`. A passed
slice does not imply another one passed.

### Model, Offer, And Price Artifact

1. Bind the paying problem, reachable payer, value event and cadence, current
   alternative, variable cost, product stage, and evidence level.
2. Compare subscription, one-time, credits, ads, or hybrid fit against that
   value mechanism. Use product willingness-to-pay behavior and compatible
   cohorts; sourced priors never become product truth.
3. For a presentation experiment, test one named presentation variable while
holding audience, eligibility, offer, price, timing, channel, product
experience, and measurement fixed where applicable. This is a fixed-variable
invariant for the presentation test, not authorization to reopen a frozen
product offer; an external result may motivate the hypothesis but cannot be
transferred as the product outcome.
4. A blocked model or price slice returns only `none` or `evidence_action` and
   forbids `experiment`. `bounded_blueprint` requires the complete canonical
   experiment, including win, loss, inconclusive, quality, trust, and rollback
   rules through the relevant maturity state.

### Execution And Policy

1. Materialize the Current Source Set for the exact store, country, product,
   offer, and eligibility question. Record freshness, conflicts, and recheck
   conditions without recalling policy from memory.
2. Independently observe the exact candidate's paywall, purchase, settlement,
   entitlement, restore, cancellation or refund state, billing failure, and
   analytics path before traffic or live mutation.
3. Stale policy, broken instrumentation, or an unverified transaction path
   blocks only this slice. `execution_handoff` is allowed only when the slice
   is `ready`; Marketing still does not authorize execution.

### Economics And Scale

1. Declare revenue basis (`gross`, `settled`, or `net`), currency, included and
   excluded adjustments, economic denominator, acquisition-cost treatment and
   allocation, cohort maturity, and marginal scale rule.
2. Keep store, country, source, paywall, offer, price, and entry cohorts
   comparable. Do not mix downloads with installs, average with marginal CAC,
   or immature with mature revenue.
3. Diagnose the limiting step across exposure, settled payment, activation,
   renewal, cancellation, refund, billing failure, retention, contribution,
   and payback. Do not optimize a visible local rate at downstream expense.
4. First revenue permits only another bounded test. Scale stays blocked until
   mature comparable cohorts, marginal response as spend changes, contribution
   and payback, cash fit, channel capacity, stable quality, and explicit
   scale/hold/reduce/stop rules are all decision-grade.

## Options And Tradeoffs

- **Subscription:** fits recurring value and supports ongoing delivery, but
  raises renewal, cancellation, expectation, and long-horizon quality duties.
- **One-time unlock:** is simple for a durable outcome, but may not fund
  recurring service cost or future value.
- **Metered credits:** can align price with variable usage, but users must
  understand the unit and avoid surprise charges.
- **Ads:** lowers the payment barrier, but needs inventory and advertiser demand
  and may damage attention, privacy, or retention.
- **Hybrid:** diversifies revenue, but creates cannibalization and conflicting
  incentives that must be measured.
- **Trial or introductory offer:** may reduce initial uncertainty, but can
  attract low-intent cohorts and requires mature settlement, cancellation, and
  renewal observation.
- **Hard versus soft paywall:** creates a clearer paid boundary versus more
  value demonstration; either can be coercive when timing or disclosure is
  poor.

Select by value mechanism, payer, variable cost, reversibility, evidence level,
and trust—not by category habit.

## Common Failure Patterns

- treating first payment as product-market fit, profitability, ROAS, or scale
  permission;
- copying a benchmark, trial length, budget multiple, or platform prior as a
  product target;
- mixing downloads with installs or immature with mature cohorts;
- comparing stores, countries, channels, prices, trials, or paywalls without
  controlling cohort mix;
- counting trial start as settled revenue or ignoring grace, retry, refunds,
  cancellations, and billing failures;
- changing paywall timing, price, package, copy, and acquisition source at once;
- raising conversion while retention, renewal, trust, refund, or contribution
  quality falls;
- assuming iOS or Android behavior without like-for-like product evidence;
- using stale or unmaterialized policy and benchmark claims;
- hiding recurring terms, blocking restore, or creating coercive continuity.

## Output Contract

Return the Decision Core and the strict
`agent-company.marketing-decision/v0.1` shape defined by the Marketing
Operating System. Add only payer and value evidence, model or offer
tradeoffs, Current Source Set and purchase-path status, declared monetization
economics, and the applicable independently gated decision slices. A bounded
artifact blueprint contains the complete canonical experiment. A blocked
artifact contains none.

The executor cannot independently validate its own paywall, cohort, or outcome
claim. Preserve `agent_company_bounded_handoff.v0.1` for a role handoff and
leave gate scoring to an independent evaluator.

## Stop Or Escalate

Block the affected slice for missing payer or demand evidence, a broken
purchase path, incompatible or immature cohorts, absent Current Source Set,
unknown policy applicability, or missing scale economics. Route evidence
refresh to bounded research, commercial fit to `commercial-fit`, contested
interpretation to bounded evidence debate, copy craft to
`copywriting-operating-system`, material plan or risk-bar changes to the authorized decision owner, and
approved implementation plus independent verification to the assigning lead. Stop
before live price, product, store, campaign, spend, gate, or release action.

## Compression Examples

**Good:** "Readiness is blocked for price and scale. The supplied cohort shows
first settled revenue, but its denominator is store downloads, the newest offer
has not completed billing-retry and refund observation, and renewal,
contribution, marginal CAC, and payback are unknown. Do not copy the old vendor
benchmark into a target. First refresh the Current Source Set for the target
store and country, verify purchase and restore on a real device, then compare
one offer within a single eligible mature cohort. A win still requires retained
quality and refund guardrails; it would authorize only the next bounded test."

**Bad:** "The industry average proves the annual plan should be the default.
Raise the price, add a countdown, hide the monthly option, and scale ads as soon
as trial conversion improves."
