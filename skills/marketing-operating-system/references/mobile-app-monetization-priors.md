# Mobile App Monetization Experiment Priors

Use this reference when Planning or Marketing evaluates a mobile-app paywall,
subscription funnel, ad-supported model, or paid-acquisition experiment. It is
an operating baseline for early learning, not a company-wide performance
promise or permission to spend.

## Authority And Override Rules

Apply evidence in this order:

1. mature, product-specific cohorts with verified purchase and attribution data;
2. category-, country-, store-, channel-, and paywall-specific evidence;
3. the sourced market benchmarks below;
4. the internal operating bands in this guide.

Higher-ranked evidence overrides lower-ranked priors. Record every override,
its evidence, and the next review condition. Never turn a market average,
platform recommendation, or internal band into a guaranteed outcome.

Marketing owns demand, channel, funnel-experiment, and downstream-quality
evidence. Planning consumes that evidence to define milestones, dependencies,
spend stages, acceptance criteria, and stop conditions. Neither role may approve
external spend, a gate, or final verification.

## Market And Platform Priors

- Treat a Korea-first paid-subscription strategy as a negative exploration
  prior until product evidence proves otherwise. Test willingness to pay and
  reachable demand in Korea and candidate overseas markets instead of turning
  the prior into an absolute claim that Korea can or cannot monetize.
- Start iOS subscription exploration before Android when the product can
  plausibly support recurring value. Start Android with ads or a hybrid model
  when demand and willingness-to-pay evidence are absent, using a lower
  top-of-funnel subscription-conversion prior than on iOS.
- Do not rule out Android subscriptions. RevenueCat's 2026 benchmark reports
  similar trial-to-paid conversion after a trial starts on iOS and Google Play,
  even though overall download-to-paid conversion differs materially by store.
- Product evidence overrides these platform priors. Compare like-for-like
  mature cohorts rather than copying the same paywall or allocation across
  stores.

## Monetization Decision Sequence

Before choosing a price, paywall, business model, or acquisition channel,
record:

- the `paying problem`: the costly, frequent, or urgent progress that is not
  served well enough today;
- the `reachable payer`: who transfers money and how that payer can be reached;
  distinguish an end user from an advertiser, merchant, or other payer;
- the `value event and cadence`: the observable user outcome and how often the
  product can deliver it;
- the `payment trigger`: the event that makes payment appropriate without
  coercion or surprise;
- the `model hypothesis`: why the proposed model fits the value cadence, payer,
  variable cost, and expected downstream quality.

Use this decision chain:

`paying problem and reachable payer -> user value -> value event -> payment trigger -> settled revenue -> repeatable economics -> scale`

Keep the evidence levels separate:

1. `behavioral demand evidence` shows that the target user acts on the problem
   or seeks the proposed progress;
2. `first settled revenue` shows that the payment path worked and at least one
   payer paid under the observed conditions;
3. `repeatable economics` requires mature, comparable cohorts with activation,
   retention, renewal or repeat purchase, refunds, billing failures, CAC, LTV,
   and contribution evidence appropriate to the model;
4. `scale readiness` additionally requires marginal acquisition economics,
   channel capacity, payback, cash-window fit, and stable downstream quality.

Passing one level does not imply the next. A first purchase does not prove
product-market fit, ROAS, profitability, or permission to continue spending.

Match the business model to the value mechanism instead of copying a category
default:

- use recurring subscriptions when meaningful value recurs and remains
  deliverable across renewal periods;
- use one-time purchases when a discrete unlock or durable outcome carries the
  value;
- use metered credits when a clear usage unit maps to variable service cost and
  customers can understand the charge;
- use advertising when repeated engagement and advertiser demand can support
  inventory without degrading the user experience or trust;
- use affiliate or marketplace revenue when attributable purchase intent and
  transaction quality are observable;
- for a hybrid model, state which model subsidizes or competes with the other
  and how cannibalization will be detected.

Treat trial length, platform choice, and model mix as category-, country-, and
product-specific hypotheses. Before each experiment, name its evidence level,
hypothesis, intervention, comparison or baseline, cohort, primary metric,
maturity window, downstream guardrails, and win, loss, or inconclusive action.
Attribution and conversion alone remain directional evidence unless the design
supports a causal claim.

## Practitioner Option Register

Keep practitioner observations in the option space even when their evidence is
not strong enough for a default. `Deck-reported` below means the supplied ATC
presentation states the claim or example; it does not mean Agent Company has
independently reproduced it. For each option, record why it may fit, the
smallest reversible test, required evidence, stop condition, owner, and next
review point. None of these options authorizes external spend or overrides the
stages and trust guardrails below.

- **Problem-and-payer concentration heuristic.** The deck reports that choosing
  the problem and payer determines roughly `70-80%` of monetization success.
  Preserve this as a prioritization reminder to validate the paying problem and
  reachable payer early. The deck does not provide a sample, denominator, or
  success definition, so do not turn the range into a probability forecast,
  score weighting, pass threshold, or portfolio-ranking formula.
- **Immediate post-approval acquisition.** The deck proposes store approval,
  then AdMob or Google Ads, then first revenue, followed by analytics-led
  iteration. Consider this a fast first-revenue smoke-test option only after
  Stage 0 instrumentation and purchase-path verification are already complete,
  the spend has the required approval, and Stage 1 caps and stop conditions are
  defined. Do not adopt the deck's measurement-after-spend ordering. A purchase
  may validate paid demand or payment plumbing under the observed conditions;
  it does not establish ROAS, profitability, or permission to continue.
- **Store visibility workstream.** Consider App Store editorial featuring and
  policy-compliant visibility work across metadata and ASO, product updates,
  in-app events, download momentum, and authentic rating or review signals. The
  deck's list is an investigation map, not a ranking formula or a promised
  outcome. Never buy, fabricate, gate, or otherwise manipulate downloads,
  ratings, or reviews, and recheck current store rules before execution.

The deck labels the following table `Apple Data (2024)` but does not include a
methodology or source link. Preserve it as a trial-design prompt, not a default:

| Segment lens | About 1 month | About 1 week | About 3 days |
| --- | --- | --- | --- |
| Category examples reported in the deck | Entertainment, social, books, music | Health and fitness, productivity, education, weather | Photo and video, games, utilities, business |
| Regional examples reported in the deck | United States and Canada, Korea, Europe, Australia and New Zealand | China, Japan, Latin America | Southeast Asia, broader Middle East |

Do not combine the category and regional rows into a universal rule. Treat each
duration as a segmented experiment candidate and compare like-for-like cohorts
with activation, paid conversion, renewal, cancellation, refund, and retention
guardrails. Reverify the underlying data and current market behavior before a
material trial decision.

Keep portfolio realization paths visible without making them product-stage
requirements. The deck names IPO, M&A or secondary sales, and app marketplaces,
with Acquire.com, Round.com, Flippa, and TrustMRR.com as discovery leads. These
names are neither endorsed nor confirmed-current vendors. Reverify availability,
fees, buyer and revenue diligence, platform-account transfer rules, contracts,
IP ownership, privacy and user-data obligations, revenue concentration, and
maintenance burden before considering a transaction. An asking price or listing
does not validate product economics.

## Funnel Definitions

Name the acquisition denominator before reporting a rate:

- `install cohort`: distinct attributed first installs or first opens entering
  the cohort;
- `download cohort`: distinct store downloads when that is the only available
  denominator.

Do not relabel a download benchmark as an install result or combine the two in
one trend. Deduplicate users and preserve paid versus organic attribution.

| Metric | Numerator | Denominator | Observation rule |
| --- | --- | --- | --- |
| `D30 install-to-trial` | Distinct cohort users whose first trial starts within 30 days | Distinct attributed install-cohort users | Every included user has completed the 30-day window |
| `trial-to-paid` | Eligible trial starts that produce a settled first paid charge | Trial starts whose trial, grace, and relevant billing-retry state are observable | Use one trial length and paywall type per comparison |
| `D35 install-to-paid` | Distinct cohort users with a settled first paid charge within 35 days | Distinct attributed install-cohort users | Every included user has completed the 35-day window |

A cohort is `mature` only after its full observation window and relevant
trial/payment state have settled. Separate results by country, store, channel,
paid versus organic source, paywall type, trial length, and material price
change. If the cohort is too small to support the decision, label it
`inconclusive`; do not treat absence of evidence as failure.

## Early Operating Bands

These are internal decision bands derived from the sourced market context. They
are not direct vendor thresholds and do not prove product-market fit.

### D30 Install-To-Trial

| Mature cohort result | Default decision |
| --- | --- |
| `< 4%` | Stop acquisition expansion and diagnose targeting, onboarding, value demonstration, paywall timing, price, and purchase-path defects. |
| `4% to < 6%` | Maintain a small baseline and improve the weakest funnel step. |
| `6% to < 8%` | Treat as promising; continue bounded tests and downstream-quality observation. |
| `>= 8%` | Candidate for a small paid expansion, subject to trial-to-paid and quality gates. |

### Trial-To-Paid

| Mature cohort result | Default decision |
| --- | --- |
| `< 25%` | Diagnose trial intent, activation, trial length, billing failures, expectation mismatch, and cancellation behavior. |
| `25% to < 35%` | Improve before scale; this can still support a small learning test when install-to-paid passes. |
| `>= 35%` | Healthy early conversion signal; continue renewal, refund, retention, and unit-economics checks. |

Travel-like apps may use roughly `40%` as a category comparison, not a target or
cross-category requirement. The cited 2026 Travel benchmark was higher than
the broad cross-store median.

### D35 Install-To-Paid

| Mature cohort result | Default decision |
| --- | --- |
| `< 1%` | Stop acquisition expansion and diagnose the end-to-end funnel. |
| `1% to < 2%` | Improve the limiting step and keep spend bounded. |
| `>= 2%` | Candidate for a small paid expansion, not scale by itself. |

An `8%` install-to-trial rate and `2%` install-to-paid rate imply `25%`
trial-to-paid. That clears the lower bound for a small paid learning test but
does not clear the `>= 35%` healthy band or the scale gate.

## Spend Stages

### Stage 0: Instrument Before Spend

Verify on a real device that onboarding, paywall display, trial start, purchase,
restore, cancellation/refund state, and analytics events work. Preserve raw
counts for every funnel step. Do not buy traffic to compensate for an unknown
or broken purchase path.

### Stage 1: Initial Smoke Test

Use the following as daily exploration caps when product-specific cost evidence
does not yet exist:

- install-objective exploration: `KRW 10,000 per day`;
- subscription or paid-signal exploration: about `KRW 15,000 per day`, adjusted
  for category constraints.

These amounts mean a smallest reversible signal test. They are not CPI or CPA
targets, profitability claims, minimum viable algorithm-learning budgets, or
permission to continue until spent. Use one objective at a time. Stop early for
broken attribution, purchase defects, harmful user experience, or obviously
wrong traffic. Treat insufficient volume as inconclusive.

### Stage 2: Platform Learning

Replace the smoke-test cap with product economics and platform requirements:

- Google App campaigns for installs: daily budget at least `target CPI x 50`;
- Google App campaigns for in-app actions: daily budget at least
  `target CPA x 10-15`;
- optimize to an in-app event observed from at least
  `10 distinct users per day`; otherwise use a sufficiently frequent upstream
  event while preserving
  the paid outcome as a downstream guardrail;
- allow roughly `7-14 days` for learning before material campaign changes and
  use about a `30-day` action-evaluation window where the conversion lag
  requires it.

Use Apple Ads' account- and app-specific recommendations rather than inventing
a universal Apple Search Ads daily budget.

### Stage 3: Scale

There is no fixed scale budget. Increase spend only when multiple consecutive
mature cohorts pass the relevant funnel bands and the product's approved unit
economics. At minimum inspect:

- CPI and action CPA by marginal spend level, not only blended averages;
- net revenue or contribution LTV relative to CAC;
- payback period relative to the available cash window;
- activation, retention, renewal, cancellation, refund, and billing-failure
  quality;
- channel capacity, attribution uncertainty, and cohort mix changes.

Define scale, hold, reduce, and stop actions before changing the budget. A
conversion-rate win cannot authorize scale when retention or economics fail.

## Trust And Reporting Guardrails

- Show numerator, denominator, raw count, cohort dates, maturity, attribution
  method, exclusions, and uncertainty with every rate.
- Preserve country, store, channel, paywall, price, and trial-length differences.
- Do not use forced continuity, hidden cancellation, misleading free-trial
  language, fabricated urgency, or other dark patterns.
- Do not optimize paywall conversion by degrading retention, refund rate,
  customer trust, or platform compliance.
- Treat vendor data as operational evidence, not causal proof. Use a valid
  comparison or randomized design when claiming incremental lift.

## Sources And Freshness

Accessed `2026-07-21`:

- [RevenueCat, State of Subscription Apps 2026](https://www.revenuecat.com/state-of-subscription-apps-2026-utilities): most non-gaming categories cluster near `5-6%` D30 download-to-trial; global D35 download-to-paid median is `2.0%`; iOS and Google Play are `2.6%` and `0.9%`; trial-to-paid is approximately `32.6%` and `32.5%`; Travel is approximately `43.5%` trial-to-paid.
- [Google Ads, Best practices for App campaigns](https://support.google.com/google-ads/answer/6167156?hl=en): target-CPI and target-CPA budget multiples, event-volume, learning, and evaluation guidance.
- [Apple Ads recommendations](https://ads.apple.com/app-store/help/recommendations/0055-review-recommendations): account- and app-specific campaign recommendations.
- 윤성민, `20260720 ATC 앱수익화` presentation, pages 7, 9,
  14-16, supplied and reviewed `2026-07-22`, SHA-256
  `870b4a9b9aaa6f9b2fe4b560e42663b6ecfef8d33fc6b0b1940ffbe52a1989f3`:
  practitioner evidence for the option register; quantitative methodology was
  not supplied and the named services were not independently verified.

Refresh the sources before using these figures for a new material budget or
after a vendor changes its methodology. Record the access date and preserve the
older decision evidence rather than silently rewriting past cohort judgments.
