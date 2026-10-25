# Planning hierarchy

The hierarchy has one coordination plan and one local plan per assigned leaf.
It does not add an approval surface. This reference describes the optional
Company plan data contract; it does not launch a separate execution engine.
The current user retains material authority, the accepted overall head owns
integration, and domain leads own their accepted teams.

| Surface | Owns | Must not own |
|---|---|---|
| User | Material why, what, scope, definition of done, and changed authority | Role-local implementation details or execution receipts |
| Planning | Company-plan draft, milestone schedule, dependency DAG, assignments, and non-material schedule/dependency deltas | Material scope or success-criteria changes without the user's decision |
| Overall head | Integration and resolution of cross-team evidence within accepted authority | A team's professional judgment or self-verification |
| Domain lead and role plan | The local how for one accepted team or assignment: inputs, approach, scopes, outputs, local QA, and escalation | User-owned scope, another team's assignment, or approval of its own final outcome |
| Orca Task/Dispatch and receipts | Execution attempts, observed state, and evidence bound to the accepted assignment | Redefining the approved plan or certifying goal completion |

Existing schema keys such as `uigwe_binding`, `uigwe_reentry` and historical
decision-owner labels remain data compatibility names. They require bound
decision evidence, not a Uigwe or Seungjeongwon process, skill, or external Core.
The current actor and authority must be stated in that evidence; an old label
cannot replace the user's decision or an independent review.

## Binding rules

- A company plan uses `agent-company.company-plan/v0.2` and owns the objective,
  milestone DAG, assignments, company success/stop criteria, decision register,
  planning deltas, and re-entry triggers.
- A company plan owns an objective and company definition of done, so v0.2
  treats it as material and always byte-binds its scope packet and decision
  using the existing `uigwe_binding` fields.
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
  requires a company-plan delta; a material widening returns to the user through
  the overall head.
- Planning may directly delta-maintain schedules and dependencies. No delta
  kind may mutate an assignment, including role ownership, read/write scope,
  outputs, or forbidden mutations. Any delta
  touching the objective, user-approved scope, company success criteria, or company
  stop criteria requires a fresh byte-bound `uigwe_reentry`.
- Runtime references are symbolic and remain under
  `${SEJONG_HOME}/runs/agent-company/<run-id>/...`. Source contracts and tests do
  not create or mutate the user's real private records. The historical directory
  name does not imply an external runtime dependency. Validators resolve the
  canonical path and reject `..` traversal and symlink escapes even when the
  escaped bytes match a supplied hash.

## Handoff and verification

The company plan is the overall head's integration input. Each role plan is a bounded
execution input. Its `execution_receipt_binding` names a unique receipt id and
ref plus the exact role-plan, assignment, and role identities. Two role plans
cannot share a receipt ref or identity. Company evidence uses that binding
to reference actual Orca attempts and observations. It does not create a second
scheduler or certify message semantics. A role-local QA check is useful
evidence, but it cannot claim company completion or final verification.
