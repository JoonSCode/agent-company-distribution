# Apple Ads Search-Intent Learning Playbook

Use this reference for Apple Ads search results decisions involving Brand,
Category, Competitor, Discovery, broad match, Search Match, search-term mining,
negative-keyword fencing, or feedback into App Store product-page language.
It is a decision and experiment guide, not permission to spend or change a live
account.

Read
[External Channel Evidence Intake](channel-evidence-intake.md) first when the
request begins with a post, thread, deck, newsletter, case study, or agency
recipe.

## Evidence Register

The following first-party sources were checked on `2026-09-03`. Recheck them
before a material campaign or metadata decision when Apple changes product
names, campaign settings, match behavior, reporting, App Store review rules,
or custom product pages.

| Source | Authority | What it can establish |
| --- | --- | --- |
| [Apple Ads campaign structure](https://ads.apple.com/app-store/best-practices/campaign-structure) | `platform_mechanic`, first-party | Brand, Category, Competitor, and Discovery intent; exact and broad organization; Search Match separation; exact-negative fencing; movement of useful search terms. |
| [Understand Search Match](https://ads.apple.com/app-store/help/campaigns/0006-understand-search-match) | `platform_mechanic`, first-party | Search Match availability and use of App Store listing metadata, similar-app information, and other search data to find relevant searches. |
| [Manual bidding](https://ads.apple.com/app-store/best-practices/manual-bidding) | `platform_mechanic`, first-party | Max CPT bidding controls and Apple's recommendation surfaces; not a universal bid. |
| [Keyword match types](https://ads.apple.com/app-store/help/keywords/0059-understand-keyword-match-types) | `platform_mechanic`, first-party | Exact, broad, and negative match behavior. |
| [Create ad variations](https://ads.apple.com/app-store/help/ads/0077-create-ad-variations) | `platform_mechanic`, first-party | Keyword-theme ad variations using custom product pages. |
| [Creating your product page](https://developer.apple.com/app-store/product-page/) | `platform_mechanic`, first-party | Relevant functional keyword guidance and the prohibition on competing app names and unauthorized trademarked terms in keywords. |
| [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) | `platform_mechanic`, first-party | Accurate metadata and third-party intellectual-property boundaries. |
| [Custom product pages](https://developer.apple.com/app-store/custom-product-pages/) | `platform_mechanic`, first-party | Intent-aligned custom page content and keyword assignment. |

The practitioner post that motivated this playbook is
[`bubblbear` on Threads](https://www.threads.com/@bubblbear/post/Dckczv_G9gS),
published `2026-08-28` and accessed `2026-09-03`. It describes a compact
discovery-versus-exact operating recipe, weekly query review, relative bids,
a short CPA/LTV scale check, and ASO feedback. Treat the operating loop as
`inspiration_only`. Its bid values, keyword counts, review interval, threshold,
and reported outcomes are `account_parameter` or `tactic_hypothesis`, not
Apple policy or Agent Company defaults.

Official documentation establishes mechanics. Neither official advertiser
examples nor the practitioner post establish expected installs, profit,
incrementality, or fit for the current app.

## Decision Scope And Preconditions

Name the app, country or region, product stage, search-results placement,
primary business outcome, available budget authority, and decision owner.
Before any paid test, verify the install or first-open denominator, Apple Ads
attribution, the core activation event, paid conversion when relevant, and the
maturity and settlement rules required by
[Mobile App Monetization Experiment Priors](mobile-app-monetization-priors.md).

If attribution, purchase, restore, cancellation, refund, or downstream-quality
measurement is broken for the decision in scope, keep execution blocked. Do
not use paid traffic to diagnose an unknown purchase path.

## Official Structure Baseline

Use Apple's current search-results structure as the baseline to reason from:

| Intent | Positive targeting | Search Match | Operating job |
| --- | --- | --- | --- |
| Brand | Exact keywords related to the app or company name | Off | Capture explicit brand intent and protect its measurement. |
| Category | Exact nonbranded terms describing the category, function, or job | Off | Test known category demand with controlled intent. |
| Competitor | Exact terms for similar apps in the same or a related category | Off | Observe comparison intent inside policy and economics constraints. |
| Discovery broad | Broad versions of relevant Brand, Category, and Competitor terms | Off | Explore related queries while keeping the seed language visible. |
| Discovery Search Match | No positive keywords | On | Let Apple's matching system expose relevant search terms. |

Add the exact keywords already controlled in Brand, Category, and Competitor as
exact negative keywords in Discovery. When a Discovery term is promoted to an
exact campaign, add that exact term to the Discovery negative fence so the
same exact query is not intentionally managed in both places.

For a small account, country, or operational team, multiple intents may be
grouped as distinct ad groups within one campaign when budgets and goals are
compatible. Preserve separate intent labels, Search Match settings, keyword
ownership, negatives, country reporting, and downstream cohorts. Record this
as a compact implementation variant, not a replacement for Apple's baseline.
Do not collapse Discovery broad and Discovery Search Match into an
uninspectable bucket.

## Search-Term Decision Loop

Use a recurring review cadence that matches data volume and conversion lag.
Weekly review is a reasonable `tactic_hypothesis` for some accounts; it is not
a universal maturity window or scale gate.

For every surfaced search term, preserve its raw query and choose exactly one
state:

| State | Evidence condition | Action |
| --- | --- | --- |
| `observe` | Newly surfaced or not yet quality-checked. | Record it without changing targeting. Verify relevance, source ad group, match path, and measurement. |
| `promote_exact` | Relevant intent has enough product-specific evidence for tighter control, with no hard downstream guardrail failure. | Add it as exact to the matching Brand, Category, or Competitor owner; add the same exact term to the Discovery negative fence. |
| `exclude` | The term is irrelevant, misleading, unsafe, or sufficiently observed as harmful or nonconverting for the decision. | Add the narrowest appropriate negative match. Prefer exact negative unless broader exclusion is deliberately justified. |
| `continue_observing` | The term is relevant but immature, sparse, lagged, or conflicting. | Keep it in Discovery at the bounded baseline and name the next observation or expiry point. |

Do not create a universal install count, tap count, CPA cutoff, confidence
shortcut, or number of review cycles for these states. The decision record must
show why the available evidence is sufficient for this app, country, outcome,
and maturity window. An absence of installs after a few taps is not automatically
proof of irrelevance; an install is not automatically proof of quality.

## Minimum Search-Term Worksheet

Keep at least:

- search term, normalized term, country or region, review timestamp, and state;
- source campaign or ad group, keyword, match type, and Search Match status;
- impressions, taps, installs or first opens, spend, TTR, conversion rate,
  average CPT, and acquisition cost with explicit denominators;
- activation, retained activation, paid conversion, settled revenue, renewal,
  cancellation, and refund where those outcomes are relevant and mature;
- product version, listing or custom product page, attribution limits,
  simultaneous changes, and material exclusions;
- decision owner, decision reason, next review or expiry trigger, and the exact
  targeting and negative-keyword changes proposed.

Separate countries, materially different languages, product versions, and
listing experiences unless comparability is demonstrated. Preserve raw counts
beside rates and label immature or insufficient samples `inconclusive`.

## Bid And Budget Guardrails

Higher-intent exact terms may justify more aggressive max CPT bids than
Discovery, while Discovery usually keeps a moderate learning posture. This is
a relative operating hypothesis, not a numeric rule.

Set or change a bid only from current account recommendations, the term's
decision value, observed conversion and downstream quality, marginal response,
country economics, cash constraints, and channel capacity. Use incremental,
reversible changes with a precommitted stop condition. Do not copy another
operator's currency amount, multiplier, keyword count, or budget split.

A higher bid can change auction participation and spend; it does not prove
better users or profitable marginal volume. Search-term movement and a bid
change are separate tested variables unless the experiment explicitly models
their interaction.

## Scale Decision

Do not translate `CPA < LTV for one week` into permission to scale. Before a
material allocation increase, require:

1. multiple mature, comparable paid cohorts rather than one calendar slice;
2. stable measurement definitions and settled revenue, refund, cancellation,
   and attribution states relevant to the model;
3. verified LTV, contribution, or payback inputs rather than an optimistic
   model with hidden uncertainty;
4. marginal acquisition response at the proposed next spend level, not only
   blended historical CPA;
5. channel capacity, cash-window fit, activation, retention, trust, privacy,
   and brand guardrails;
6. a staged increase, hold rule, stop rule, and accountable approval owner.

When reliable LTV is unavailable, retained activation or another validated
quality behavior can guard a small learning test. It cannot prove profitability
or justify scale. A promoted keyword is permission for tighter observation,
not automatically a budget increase.

## ASO And Product-Page Feedback

Treat repeated relevant search language as evidence about how customers
describe a job or feature. Before changing App Store metadata:

- verify that the term accurately describes the app's current functionality
  and fits the intended country and localization;
- separate paid-query association from organic ranking or causal-conversion
  claims;
- do not use competing app names, unauthorized trademarked terms, irrelevant
  popular phrases, or unverifiable claims in metadata;
- test one coherent metadata or product-page hypothesis with a versioned
  baseline and downstream-quality guardrails;
- use a relevant custom product page or Apple Ads ad variation when a keyword
  theme needs matching screenshots, previews, or promotional text;
- keep default-page, custom-page, paid, and organic cohorts distinguishable
  where the measurement allows it.

Search Match's use of listing metadata makes the relationship bidirectional:
metadata can influence matching, and surfaced search terms can inspire better
customer language. That relationship is a learning signal, not proof that a
metadata edit caused demand or organic rank.

## Minimum Decision Output

Return:

1. `decision_question`, stage, country, and narrow `decision_readiness`;
2. `known`, `inferred`, and `unknown` with source authority and freshness;
3. current campaign-intent map and exact-negative ownership map;
4. the reviewed search-term rows and one precommitted action per row;
5. one bounded experiment when a tactic remains conditional;
6. bid or allocation rationale without copied numeric defaults;
7. downstream quality and economics guardrails;
8. next decision, operational surface, and exactly one reasoning owner.

Execution remains fail-closed when credentials, budget authority, current
account state, measurement, or approval is missing. This playbook does not
authorize live campaign changes, App Store metadata changes, publication, or a
claim of verified lift.
