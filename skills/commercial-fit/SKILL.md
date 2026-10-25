---
name: commercial-fit
description: Assess whether a discovered problem merits a focused business experiment.
---

# Commercial Fit

Use this skill after `problem-discovery` produces a candidate problem. Judge
whether the problem deserves a business experiment. Do not search for new
problems here; return failure reasons to `problem-business-loop`.

## Required Input

Start from a candidate with:

- `candidate_problem`
- `user_segment`
- `trigger_context`
- `observed_signals`
- `current_workarounds`
- `known`, `inferred`, and `unknown`

If these fields are missing, request `problem-discovery` or bounded research
evidence before scoring.

## Evaluation Checks

Assess each check as `pass`, `weak`, or `fail`:

1. `frequency`: the problem happens often enough to matter.
2. `urgency`: the user feels pain near the moment of action.
3. `buyer`: the buyer or decision maker is identifiable.
4. `budget_or_willingness`: there is evidence of money, time, reputation, or
   workflow cost.
5. `current_workaround`: users already spend effort solving it.
6. `founder_fit`: the user's current skills, taste, access, or lived context
   create an advantage.
7. `ai_leverage`: AI changes cost, speed, personalization, or quality enough to
   matter.
8. `distribution_access`: the user has a reachable channel for the first test.
9. `one_week_test`: a small experiment can falsify the opportunity quickly.

Use `evidence-debate` when a check has a strong argument on both sides.

## Verdicts

- `advance`: evidence supports a one-week business experiment.
- `conditional`: one or two gaps can be checked before a material user decision.
- `reject`: the problem is real but not a good current business target.
- `return_to_discovery`: the candidate is too weak or mismatched; convert the
  failure into new search constraints.

## Output Shape

Return:

- `candidate_problem`
- `verdict`
- `scorecard`
- `strongest_business_case`
- `strongest_rejection_case`
- `failure_reasons`
- `next_search_constraints`
- `one_week_experiment`
- `success_criteria`
- `failure_criteria`
- `recommended_next_surface`: usually `planning` for `advance`, `company-lead`
  for missing evidence or rejected directions

## Guardrails

- Do not invent market proof from generic AI enthusiasm.
- Do not pass a candidate without a reachable first user or evidence path.
- Do not require perfect proof; prefer a falsifiable one-week test when the
  downside is low.
- Do not approve execution. Route handoff-ready experiments to Planning or the
  assigning Company lead; unresolved material choices remain with the user.
