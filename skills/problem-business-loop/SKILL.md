---
name: problem-business-loop
description: Iterate problem discovery and commercial fit toward an experiment or a blocker.
---

# Problem Business Loop

Use this as a thin orchestrator. It does not replace `problem-discovery`,
`commercial-fit`, `evidence-debate`, user material authority or independent QA.

## Loop

1. Start with a search brief:
   - target audience or source set
   - current constraints
   - non-goals
   - maximum iterations, default `3`
2. Run `problem-discovery`.
3. If no credible candidate appears, tighten or change the search constraints.
4. Run `commercial-fit` on the best candidate or on a small ranked batch.
5. If `commercial-fit` returns `advance`, prepare a planning input summary.
6. If it returns `conditional`, run only the missing evidence check.
7. If it returns `reject` or `return_to_discovery`, convert `failure_reasons`
   into the next `problem-discovery` constraints.
8. Stop when an experiment is planning-ready, the iteration budget is exhausted,
   or a missing source/user decision blocks progress.

## Failure-To-Search Conversion

Convert commercial failures into discovery constraints:

- `frequency_low` -> search for repeated daily or weekly problems.
- `buyer_unclear` -> search only where a payer or decision maker is visible.
- `budget_absent` -> search for paid tools, manual labor, consultants, or time
  cost around the problem.
- `ai_leverage_weak` -> search where AI changes speed, quality, personalization,
  monitoring, synthesis, or coordination.
- `founder_fit_weak` -> search closer to the user's skills, apps, workflows,
  distribution, or lived problems.
- `channel_absent` -> search inside reachable communities, app stores, creator
  audiences, existing users, or direct networks.
- `test_too_large` -> search for problems with concierge, prototype, content,
  or manual-service validation paths.

## Output Shape

Return:

- `loop_goal`
- `iterations_run`
- `candidates_considered`
- `commercial_fit_results`
- `selected_candidate`
- `rejected_candidates`
- `current_search_constraints`
- `uigwe_input_summary`
- `blockers`
- `recommended_next_surface`

`uigwe_input_summary` is a historical payload key for the planning summary;
it does not route work to an external system.

## Guardrails

- Do not hide failed candidates; their failure reasons are loop fuel.
- Do not keep looping after three weak iterations without changing source set
  or audience.
- Do not treat the loop as proof of demand.
- Do not proceed to execution directly; route an experiment through Planning or
  the assigning Company lead. Return material unresolved choices to the user.
