# Opportunity Validation

- Reference ID: `task-pack:founder:opportunity-validation`
- Role: `founder`
- Required kernel: `role-kernel:founder`
- Decision: is a specific problem commercially testable with a reachable buyer,
  and what is the smallest next commitment?

This pack tests a commercial claim. It does not certify a market, promise
revenue, authorize customer contact or spend, or approve a product plan.

## Exact Triggers

Use this pack when:

- a candidate problem exists but buyer, urgency, payment, access, or switching
  evidence could change whether it deserves investment;
- a portfolio choice needs a commercial wedge rather than a broad market story;
- the CEO asks whether an opportunity is validated, worth testing, or ready for
  a paid pilot;
- discovery evidence exists and the next uncertainty is business-model fit.

Do not use it for:

- open-ended problem search with no bounded candidate; use `problem-discovery`;
- market sizing alone;
- copy, channel execution, solution implementation, or release verification;
- planning an already accepted wedge; route that to the authorized decision owner or Planning;
- rescuing a failed commercial test by changing the problem without
  `problem-business-loop` or material-decision re-entry.

## Required Inputs And Evidence Hierarchy

Require:

1. a falsifiable claim in the form `buyer + situation + painful progress + why
   now + smallest wedge`;
2. separate user, buyer, approver, and economic beneficiary identities;
3. observed pain, frequency, workaround, inaction consequence, and switching
   moment;
4. payment, budget, procurement, access, channel, and sales-friction evidence;
5. current alternatives, proposed wedge, delivery constraint, and the cheapest
   disconfirming test;
6. source, date, sample, selection method, and contradictory evidence.

Rank evidence from strongest to weakest:

1. completed transactions, non-refundable commitments, renewals, or repeated
   paid use in the target segment;
2. budget-confirmed pilots, procurement action, signed credible commitments, and
   costly buyer behavior;
3. observed workflows, switching behavior, direct buyer interviews, and
   attributable field evidence;
4. bounded acquisition or pricing experiments and sourced segment or competitor
   evidence;
5. stated interest, surveys, waitlists, broad market reports, anecdotes, and
   optional practitioner frameworks.

Payment is strong evidence only for the buyer, problem, wedge, and conditions
actually tested. Market size is not product demand. Label claims `known`,
`inferred`, or `unknown`.

## Decision Method

1. **Bound the claim.** Reject labels such as "SMBs need automation"; name the
   buyer, triggering situation, progress blocked, and proposed wedge.
2. **Establish problem reality.** Check frequency, severity, workaround cost,
   inaction consequence, and whether observed behavior matches interview claims.
3. **Resolve the buying system.** Separate user from buyer, approver, budget
   holder, procurement path, and vetoes.
4. **Test urgency and change.** Identify the forcing event and why the buyer
   would switch now rather than tolerate the status quo.
5. **Inspect commercial evidence.** Record payment or commitment terms, price
   context, alternatives, sales friction, delivery cost, and refund or subsidy
   effects.
6. **Check access.** Show a lawful, repeatable path to enough target buyers;
   founder-network access is a biased starting sample, not a channel.
7. **Surface disconfirmation.** State the strongest contradictory behavior and
   the fact most likely to invalidate the wedge.
8. **Set readiness.** Use `blocked` when the problem, target, or credible
   evidence source is too unclear to define a meaningful bounded test. Use
   `conditional` when a clear hypothesis, target, source, owner, and reversible
   test can resolve a material buyer or commercial unknown; use `ready` only
   when a bounded recommendation has direct commercial support. Readiness never
   authorizes spending, contact, publication, or other external action.
9. **Choose one test.** Test the highest-value uncertainty with an owner,
   segment, offer, sample, time box, success, failure, kill, and data-quality
   rule. Do not change segment, offer, channel, and price together.
10. **Recommend and route.** State what the test funds, what remains unfunded,
    and the next supported Company handoff destination.

## Serious Alternatives And Tradeoffs

- **Paid concierge pilot:** strongest early payment and workflow evidence, but
  labor-heavy and not proof of scalable delivery.
- **Deposit or pre-commitment test:** fast buying-intent evidence, but terms,
  refundability, and trust can distort results.
- **Buyer observation or interviews:** useful when the buying system is unknown,
  but stated intent is weaker than costly action.
- **Bounded channel test:** tests reachable demand, but a failed message or
  channel does not by itself invalidate the problem.
- **Return to discovery or stop:** avoids solution escalation when problem
  evidence is weak, but delays commercial learning.

Choose the alternative that resolves the named reversal question, not the one
that produces the most activity.

## Common Failure Patterns

- treating compliments, waitlists, downloads, or TAM as willingness to pay;
- interviewing users while assuming they control budget;
- asking hypothetical price questions and reporting the answer as payment proof;
- ignoring selection bias, subsidies, refunds, procurement, or switching cost;
- testing several material variables and inventing a causal explanation;
- leading with a solution and failing to observe the current workaround;
- using named founders or frameworks as authority;
- declaring "validated" while the decisive buyer fact remains unknown.

## Output Contract

Return:

- `opportunity_claim`, `target_user`, `buyer`, `approver`, and
  `decision_readiness`;
- `known`, `inferred`, `unknown`, each with evidence references;
- `problem_evidence`, `commercial_evidence`, `access_evidence`,
  `switching_friction`, and `strongest_disconfirmation`;
- `recommended_action`, `serious_alternative`, `assumptions`,
  `opportunity_cost`, `not_funded`, and `residual_risk`;
- one `next_reversible_commitment` with segment, offer, owner, time box, sample,
  success, failure, kill, and revisit criteria;
- `confidence`, `next_recommended_surface`, and `forbidden_claims`.

When a role handoff is requested, also preserve every required field of
`agent_company_bounded_handoff.v0.1`.

## Stop Or Escalate

Stop with an evidence request when the buyer, problem, or source provenance is
missing. Route new problem discovery to bounded research or `problem-discovery`;
route a commercial failure that changes the problem to `problem-business-loop`;
route material target, risk, or scope changes to the authorized decision owner; route contested
interpretation to bounded evidence debate; and route verification readiness to
the assigning lead. Stop before outreach, spend, contracting, data collection, or
another external action without explicit authority.

## Compact Example

**Good:** "Readiness is conditional, not validated. Seven managers report the
weekly workaround, but no budget owner was interviewed and both pilot promises
are unpaid. Test one redacted paid concierge offer with five owners for 10 days;
success is two non-refundable deposits, failure is zero after five completed
owner conversations. the authorized decision owner must bind any product or regulated-data work."

**Bad:** "The market report says this is a billion-dollar category and managers
loved the demo, so build the platform now."
