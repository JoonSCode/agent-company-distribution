# Architecture Risk

- Reference ID: `task-pack:development:architecture-risk`
- Role: `development`
- Required kernel: `role-kernel:development`
- Task type: `architecture-risk`
- Decision boundary: recommend the smallest architecture choice whose material
  risks have issued evidence and whose blocking unknowns fail closed.

Use this pack when a change may alter a module, process, service, trust, storage,
serving, recovery, compatibility, or ownership boundary. Use feature
implementation for a local accepted seam and causal debugging for an untraced
failure.

## Fail-Closed Method

1. **Bind the decision.** Record outcome, invariants, non-goals, decision and
   acceptable-risk owners, scope, horizon, stop condition, and authority for
   migration, rollout, rollback, and external actions. Missing ownership for an
   irreversible boundary blocks selection.
2. **Bind inspected evidence.** Give each current-state reference an ID and
   immutable identity. Claims are `known` only when cited, `proposed` when an
   unevidenced option, and `unknown` with a next check and owner. Diagrams and
   remembered platform behavior are not current-state evidence.
3. **Classify decision-bearing domains.** Classify a plausible domain only when
   its disposition can change the option, blocker, check, test, or independent
   handoff. Record `material`, `preserved`, `not_applicable`, or `unknown` with
   impact scope, reversibility, evidence, and materiality reason. A
   decision-blocking `unknown` permits only `blocked` or `evidence_only`, never
   a selected production architecture.
4. **Supply material controls.** For migration, state `last_known_good`,
   `rollback_dependency`, exact `rollback_dependency_detail`,
   `forward_recovery`, `cleanup_owner`, and
   `irreversible_transition_disclosure` together. For trust, include replay and key-loss/compromise controls plus
   independent security evidence. For serving, name authority, propagation,
   monitor owner, and served-state oracle. For recovery, prove its access path
   does not depend on the failed primary system.
5. **Compare only credible choices.** Contrast the direct option with one
   alternative and status quo when delay is viable on outcome fit, invariant
   risk, blast radius, operations, migration, and reversibility. Defer a new
   module, protocol, cache, service, queue, framework, or store without a
   current requirement; name a measurable `revisit_signal`.
6. **Seek reversal evidence.** Run only the smallest safe compatibility check,
   representative-data dry run, failure injection, recovery rehearsal, or
   evidence-only spike that could disqualify an option. A spike is not runtime
   or release proof.
7. **Validate and hand off.** Attach `architecture_safety` and validate it with
   `scripts/agent_company_architecture_safety.py` before the architecture-risk
   handoff. Return selected/blocked decision, rejected complexity, compact
   rationale, residual risk, unverified surface, recheck trigger, and independent
   verification target.

Use only the smallest allowed check that could reverse the choice. Do not set a
tool-count quota.

## Stop

Stop when evidence, owner, or safe control for a decision-blocking domain is
missing. Preserve the `unknown` and return `blocked` or `evidence_only`; do not
claim migration, security, runtime, release, or final-verification safety.
