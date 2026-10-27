# Feature Implementation

- Reference ID: `task-pack:development:feature-implementation`
- Role: `development`
- Required kernel: `role-kernel:development`
- Task type: `feature-implementation`
- Decision boundary: deliver an approved feature slice without changing its
  established contract.

Use this pack for authorized code that adds a stable user, caller, or operator
outcome. Use causal debugging when the failing seam is unknown, architecture
risk when a consequential boundary changes, and the authorized decision owner when outcome, risk, or
authority is unsettled.

## Decision Method

1. **Bind the slice.** Record outcome, actor, observable transition,
   requested quality, must-preserve behavior, non-goals, write scope, stop
   condition, candidate, and independent verifier. Preserve unrelated work.
   Reuse prior evidence only with its source, rationale, counterevidence, scope,
   freshness, and supersession state.
2. **Trace the feature seam.** Inspect the entry point, direct callers, state
   owner, side effects, and relevant persistence, API/UI, lifecycle, and
   compatibility boundaries. Mark each changed, preserved, unverified, or not
   applicable; a missing product rule is a blocking unknown.
3. **Choose the smallest option.** Compare the local seam with one alternative
   when coupling, containment, reversibility, or total maintenance, integration,
   and verification burden can change the choice. The minimum-solution ladder
   orders exploration, not selection; a sufficient later rung may have lower
   total burden. Reject added
   framework, service, cache, module, or adapter unless a current requirement
   pays for it; record the `revisit_signal`.
4. **Set proof before production change.** For every changed or must-preserve
   criterion name a focused seam, oracle, fixture, and falsification signal.
   Run the narrowest check that fails for the intended behavior. If it is unsafe
   or unavailable, record `unavailable_control`, `safety_reason`,
   `bounded_substitute_observation`, and `remaining_verification_owner`.
5. **Implement one vertical slice.** Change only authorized files and preserve
   callers, stored data, error mapping, cancellation, and partial-success rules.
   Do not fold in cleanup or speculative extensibility.
6. **Check seam and boundary.** Run the focused check and an applicable negative control
   (for example denial, invalid input, duplicate, cancellation, or
   dependency failure). Then exercise the smallest available integrated path on
   the exact candidate through the actual caller or product path needed by the
   claim; a mock, harness, direct code invocation, or unit check does not
   replace this observation. Record manual assistance and substitute paths.
7. **Hand off.** Return changed files and behavior, selected and rejected option,
   exact checks/results, negative and integrated observations, unverified
   surface, residual risk, reproduction, and owner for independent verification.

Use only the smallest allowed inspection, test, or runtime check that could
reverse a current decision. Do not set a tool-count quota.

Read [optional methods](../optional-methods.md) only when they could change a material unresolved choice; skip them for settled work.

## Compact Record

Return the standard bounded handoff plus the executable feature contract,
impact-surface statuses, criterion-to-proof mapping, chosen option and
`revisit_signal`, and either `pre_change_evidence` or the bounded infeasibility
record. Keep `known`, `inferred`, and `unknown` distinct. Validate the handoff
with `scripts/agent_company_handoff.py import <handoff.json> --json` when
available; QA-Release owns matching-surface observation and the assigning lead owns
final execution verification.

## Stop

Stop before editing when authority, intent, a must-preserve rule, safe proof, or
a current source that can reverse the choice is missing. Escalate the exact
unknown with its smallest next check; do not widen the slice to route around it.
