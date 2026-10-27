# Portfolio Decision

- Reference ID: `task-pack:founder:portfolio-decision`
- Role: `founder`
- Required kernel: `role-kernel:founder`
- Decision: which opportunity deserves the next scarce unit of company attention?

This pack produces portfolio evidence and a recommendation. It does not make the
CEO's decision, allocate resources, approve material user decisions, or verify execution.

## Exact Triggers

Use this pack when at least one condition is true:

- two or more initiatives compete for the same bounded attention, cash, or
  capacity;
- starting or extending one initiative requires delaying, pausing, or stopping
  another;
- the CEO asks which opportunity to select, fund next, defer, harvest, or drop;
- new evidence may reverse an existing portfolio priority.

Do not use it when:

- the direction is already settled and only milestones or decomposition are
  needed; route to Planning or the authorized decision owner;
- the candidate problem is still undefined; route evidence gathering to
  bounded research or `problem-discovery`;
- the choice is only about implementation, release, or observed verification;
- the request would authorize spending, hiring, publication, submission, or
  another external action.

## Required Inputs And Evidence Hierarchy

Require:

1. one decision question, decision owner, decision horizon, and no-action
   consequence;
2. the hard capacity, cash, time, obligation, and risk constraints;
3. a comparable evidence card for every serious option, including the current
   portfolio commitment it displaces;
4. reversibility, time to decision-grade evidence, dependencies, and exit cost;
5. the source, date, scope, and uncertainty of every material fact.

Rank evidence for the live choice from strongest to weakest:

1. observed transactions or credible commitments, retained use, customer
   behavior, audited product or business outcomes, and measured capacity;
2. direct field observation and attributable buyer or customer interviews;
3. bounded experiment results and sourced segment, channel, or competitor data;
4. internal estimates with explicit assumptions;
5. anecdotes, opinions, named founders, and frameworks.

Lower-ranked evidence may challenge a choice but cannot silently overrule
higher-ranked contradictory evidence. Named frameworks are optional
falsification lenses only. Mark every material statement `known`, `inferred`,
or `unknown`; stale or non-comparable evidence remains unknown for the choice.

## Decision Method

1. **Normalize the mandate.** State the decision, owner, horizon, reversible
   boundary, constraints, and what happens if nothing changes.
2. **Make options comparable.** For each option record the problem, buyer,
   commercial evidence, strategic advantage, distribution access, required
   capacity, time to evidence, dependencies, and exit cost.
3. **Check admissibility.** Reject hard-constraint violations and prohibited
   outcomes, recording why. Keep otherwise viable approval-pending options
   comparable; name the required approval and decision owner, and mark execution
   blocked until approval exists. A recommendation never authorizes the action.
4. **Test reversal facts.** Name the smallest missing fact that could change the
   ranking. Set readiness to `blocked`, `conditional`, or `ready` under the role
   kernel.
5. **Compare consequences.** Contrast expected learning and upside with downside,
   concentration risk, opportunity cost, and the no-action baseline. A score may
   expose assumptions; it must not replace the evidence.
6. **Keep one serious alternative.** It must be feasible and capable of winning
   if a named reversal condition becomes true.
7. **Size the recommendation to readiness.** `Blocked` means minimum problem,
   target, or source grounding is missing: return an evidence request or a
   non-committing option frame. `Conditional` means a meaningful small reversible
   test is definable; recommend that test. `Ready` permits a bounded
   recommendation. None of these statuses grants execution authority.
8. **Make the recommendation falsifiable.** Define success, failure, kill, and
   revisit criteria, the next evidence horizon, and what is explicitly not
   funded.
9. **Hand off.** Send a direction needing a plan or material policy decision to
   the authorized decision owner; send missing evidence to bounded research; send verification readiness to
   the assigning lead.

## Serious Alternatives And Tradeoffs

- **Concentrate on a proven initiative:** faster feedback and asset reuse, but
  greater concentration and possible local-maximum risk.
- **Fund a new wedge:** diversification and new upside, but weaker priors,
  switching cost, and longer time to trustworthy evidence.
- **Buy option value with a small test:** limits downside, but delays scale and
  can create test overhead if the reversal question is vague.
- **Pause, harvest, or stop:** restores capacity and reduces exposure, but may
  lose momentum, customer trust, or a time-sensitive opening.
- **Do nothing for the horizon:** preserves focus, but accepts the stated cost of
  inaction; it is a real option, not an omitted baseline.

Read [optional methods](../optional-methods.md) only when they could change a material unresolved choice; skip them for settled work.

## Common Failure Patterns

- selecting by total market size, enthusiasm, or a weighted score without source
  evidence;
- comparing polished evidence for one option with guesses for another;
- hiding fixed obligations or pretending the same capacity funds every option;
- treating sunk cost, founder identity, or prior ownership as continuation proof;
- offering many "priorities" without naming what loses funding;
- converting a conditional recommendation into an irreversible commitment;
- inventing demand, revenue, runway, or confidence to fill an evidence gap.

## Output Contract

Return one bounded decision packet containing:

- `decision_question`, `decision_owner`, `decision_horizon`,
  `decision_readiness`, and `no_action_consequence`;
- `known`, `inferred`, `unknown`, with source references;
- `options_considered` and explicit rejected-option reasons;
- `recommended_action`, `strongest_support`, `strongest_disconfirmation`, and
  `serious_alternative`;
- `assumptions`, `opportunity_cost`, `not_funded`, and `residual_risk`;
- `next_reversible_commitment`, owner, horizon, success, failure, kill, and
  revisit criteria;
- `confidence` as `low`, `medium`, or `high`, justified by evidence quality;
- `next_recommended_surface` and `forbidden_claims`.

When a role handoff is requested, also preserve every required field of
`agent_company_bounded_handoff.v0.1`.

## Stop Or Escalate

Stop and return to the Sejong lead when the packet is complete. Escalate instead
when a missing reversal fact keeps readiness blocked, options are not comparable,
capacity or cash evidence is unavailable, a material target or risk decision
needs the authorized decision owner, evidence is materially contested and needs bounded evidence debate, or an
intended execution step requires missing approval. Non-executing comparison of
otherwise viable approval-pending options may continue. Never claim gate approval or final
verification.

## Compact Example

**Good:** "Recommend an 80-hour retention test for A, conditionally. A has
observed paid retention; B has interviews but no buyer commitment. B is the
serious alternative if two buyers place deposits by 15 August. This leaves B
unfunded for six weeks; kill A's test if activation does not improve from 31% to
38% in the defined cohort. the authorized decision owner should bind the test."

**Bad:** "A famous founder would focus, so A is obviously the winner. Fund it
until it works; B can continue in parallel."
