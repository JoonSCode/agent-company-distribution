# Causal Debugging

- Reference ID: `task-pack:development:causal-debugging`
- Role: `development`
- Required kernel: `role-kernel:development`
- Task type: `causal-debugging`
- Decision boundary: establish an evidenced causal path before an authorized
  durable repair is selected; distinguish approved temporary containment.

Use this pack for an observed failure, regression, incident symptom, or
conflicting metric with plausible competing causes. Use feature implementation
for a stable new outcome, architecture risk for a consequential boundary, and
remain read-only when repair authority is absent.

## Decision Method

1. **Bind the failure.** Record expected and observed behavior, candidate,
   environment, minimal event sequence, oracle, impact, safe scope, stop
   condition, and independent verifier. A missing reproduction is an unknown,
   not a convenient explanation. Within explicit incident-response authority,
   reversible containment may reduce observed harm before full diagnosis.
   Preserve evidence; record rollback and stop conditions, diagnosis owner, and
   re-entry time or signal. Keep the root cause unresolved, and do not treat
   containment success as durable repair or independent verification.
2. **Find the first divergence.** Trace entry, caller, state reads/writes,
   async and persistence boundaries, external calls, retries, cancellation,
   cleanup, and presentation. Identify the first observed break from the
   expected invariant, not the nearest stack frame or final symptom.
3. **Rank causal hypotheses.** For the leading and strongest alternative,
   record mechanism, predicted observation, supporting and contradictory
   evidence, and missing evidence. Each serious deferred hypothesis carries
   `observable_reentry_signal`, `next_bounded_check`, and `owner`.
4. **Run a distinguishing experiment.** Change one causal variable or intercept
   one boundary only after stating distinct predicted results. Include a
   disconfirming negative control so detector or instrumentation behavior cannot
   impersonate the signal. Keep instrumentation bounded and non-perturbing.
5. **Choose the earliest owned repair.** The intervention and timeline must
   support the mechanism and contradict serious alternatives. Otherwise return
   the ranked hypotheses and next discriminator; do not add delay, retry, broad
   catch, reset, or rewrite as an ungrounded durable repair. Approved temporary
   containment above remains separate and must not bypass safety or approval.
6. **Prove the mechanism.** Establish the minimal regression that fails before
   and passes after the repair, rerun the distinguishing experiment and negative
   control, and check the adjacent invariant. Exercise the original integrated
   path when safely available on the exact candidate.
7. **Hand off.** Return reproduction, first divergence, causal path, hypotheses,
   experiment/predictions/results, repair, checks, remaining unknowns, and exact
   independent verification target.

Use only the smallest allowed observation or experiment that could reverse the
causal ranking. Do not set a tool-count quota.

## Compact Record

Return the standard bounded handoff plus `failure_contract`, timeline, first
divergence, causal path, deferred-hypothesis records, focused regression,
negative-control and integrated observations, residual recurrence risk, and
reproduction steps. Keep `known`, `inferred`, and `unknown` distinct; focused
checks do not establish final verification.

## Stop

Stop and escalate when the oracle is disputed, a safe reproduction would mutate
protected data, required observation needs prohibited access, the causal seam is
unowned, or a repair changes product semantics or architecture risk. Return the
blocking unknown, next discriminating experiment, and owner.
