# Planning hierarchy

The hierarchy has one coordination plan and one local plan per assigned leaf.
It does not add an approval surface.

| Surface | Owns | Must not own |
|---|---|---|
| Uigwe | Material why, what, scope, definition of done, and re-entry decisions | Role-local implementation details or execution receipts |
| Planning | Company-plan draft, milestone schedule, dependency DAG, assignments, and non-material schedule/dependency deltas | Material scope or success-criteria changes without Uigwe re-entry |
| Sejong | Lead synthesis and resolution of cross-role evidence | Role execution or self-verification |
| Role plan | The local how for exactly one company assignment/leaf: inputs, approach, scopes, outputs, local QA, and escalation | Uigwe scope, company criteria, dependency graph, another assignment, synthesis, approval, or final verification |
| Seungjeongwon | Execution attempts, receipts, retry state, and verification evidence bound to the role plan | Redefining the approved plan |

## Binding rules

- A company plan uses `agent-company.company-plan/v0.2` and owns the objective,
  milestone DAG, assignments, company success/stop criteria, decision register,
  planning deltas, and re-entry triggers.
- A company plan owns an objective and company definition of done, so v0.2
  treats it as material and always byte-binds its Uigwe packet and decision.
  Clearing the material flag or binding is a downgrade attempt, not permission
  to continue. Changed or missing source bytes are stale state.
- An assignment names one unique leaf. A role plan uses
  `agent-company.role-plan/v0.2`, binds that assignment and leaf, and byte-binds
  the company plan. Two role plans cannot own the same leaf.
- Marketing, Design, Development, and QA/Release role plans additionally bind
  one canonical machine-readable operating contract by contained relative path
  and exact digest. Founder and Planning have no such contract. The validated
  binding is carried into the explicitly versioned v0.2 execution handoff and
  rechecked there. Historical marker-free v0.1 handoffs remain readable but may
  not carry an unversioned contract binding.
- Role read/write scopes and outputs are subsets of their assignment. Widening
  requires a company-plan delta; a material widening returns to Uigwe.
- Planning may directly delta-maintain schedules and dependencies. No delta
  kind may mutate an assignment, including role ownership, read/write scope,
  outputs, or forbidden mutations. Any delta
  touching the objective, Uigwe scope, company success criteria, or company
  stop criteria requires a fresh byte-bound `uigwe_reentry`.
- Runtime references are symbolic and remain under
  `${SEJONG_HOME}/runs/agent-company/<run-id>/...`. Source contracts and tests do
  not create or mutate the user's real Sejong runtime. Validators resolve the
  canonical path and reject `..` traversal and symlink escapes even when the
  escaped bytes match a supplied hash.

## Handoff and verification

The company plan is Sejong's synthesis input. Each role plan is a bounded
execution input. Its `execution_receipt_binding` names a unique receipt id and
ref plus the exact role-plan, assignment, and role identities. Two role plans
cannot share a receipt ref or identity. Seungjeongwon receipts use that binding
to report attempts and observed evidence. A role-local QA check is useful
evidence, but it cannot claim company completion or final verification.
