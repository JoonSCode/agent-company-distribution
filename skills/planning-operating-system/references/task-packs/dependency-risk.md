# Dependency And Risk

- Reference ID: `task-pack:planning:dependency-risk`
- Role: `planning`
- Required kernel: `role-kernel:planning`
- Task type: `dependency-risk`
- Decision: which real prerequisites and failure risks should control order,
  parallelism, containment, and replanning?

This pack audits and revises plan topology. It does not diagnose a live incident,
approve a risky action, execute a mitigation, or certify that a dependency or
release is safe.

## Decision Core

Apply `planning-contract.json#/decision_output_policy` and answer four things
before producing a ledger: what is blocked now, what can proceed independently,
which single edge or risk controls the order, and what observation would change
that decision. Distinguish dependencies that control start, finish,
verification, and release; do not collapse them into one serial chain. Expand
only decision-bearing edges and material risks. Each selected risk needs a
cause, failure event, criterion impact, earliest detector, trigger,
containment, owner, and proof target; otherwise expose it as unresolved instead
of padding the register.

## Exact Triggers And Non-Triggers

Use this pack when:

- a plan crosses roles, systems, accounts, approvals, vendors, data boundaries,
  or shared resources;
- sequencing or parallelization depends on disputed prerequisite claims;
- a critical path, cycle, bottleneck, single point of failure, or rollback path
  needs explicit review;
- new evidence changes dependency status, likelihood, impact, or containment;
- a handoff needs an evidence-backed risk and replan contract.

Do not use it when:

- approved intent or acceptable risk is materially unsettled; return to the authorized decision owner;
- no bounded leaf set or produced and consumed outputs exists yet; use the
  execution-plan pack first;
- the request is runtime root-cause analysis, implementation, security scanning,
  final QA, or release approval;
- acceptance criteria and proof surfaces are the only unresolved issue; use the
  acceptance-verification pack;
- a broad portfolio risk decision belongs to Founder.

## Required Inputs

Require:

1. proposed leaves with the contract-defined assignment tuple, first actions,
   done criteria, scopes, and named produced and consumed artifacts;
2. the current status and provenance of every claimed prerequisite;
3. interface, schema, account, approval, policy, data, resource, and environment
   constraints that could block or reorder work;
4. supplied duration or capacity ranges and their basis, if schedule analysis is
   requested;
5. failure effects on success criteria, must-preserve behavior, users, data,
   money, safety, and reversibility;
6. available prevention, detection, fallback, containment, rollback, and
   recovery evidence;
7. risk owners, independent verification owners, decision owners, and recheck
   horizons.

Unknown duration is not zero, an unconfirmed approval is not available, and a
mock is not a satisfied runtime dependency.

## Evidence Priority

Rank dependency and risk evidence from strongest to weakest:

1. current direct observation of the prerequisite, owner-controlled approval
   state, or accepted upstream artifact on the exact required version;
2. exercised interface contracts, integration evidence, recovery tests, and
   verified production-like behavior within the named scope;
3. binding schemas, policies, role authority, resource reservations, and
   measured capacity;
4. comparable incident, delivery, or operational data with source and context;
5. owner estimates with assumptions, ranges, and recheck triggers;
6. generic risk lists, nominal ownership, intuition, and unsupported point
   estimates.

Applicability matters more than volume. Evidence for a fixture, old version, or
different environment cannot silently satisfy the live edge. Preserve
contradictory evidence and label facts `known`, `inferred`, or `unknown`.

## Step-By-Step Method

1. **Normalize each edge.** Express it as `producer leaf -> write artifact or
   condition -> consumer read -> observation -> assignment tuple`. If the
   consumer can start and finish without that output,
   remove the edge and record any coordination preference separately.
2. **Classify the dependency.** Mark it `hard`, `soft`, `approval`, `external`,
   `resource`, `evidence`, or `safety`. State whether it controls start, finish,
   verification, release, or only optimization.
3. **Test satisfiability.** For every edge record the producer, exact artifact
   or state, acceptance condition, assignment tuple, current status, evidence
   reference, expiry or recheck trigger, and fallback. Set a
   `surface_disposition` of
   `satisfied`, `unsatisfied`, `conditional`, `unknown`, or `not_applicable`.
4. **Find missing producers and cycles.** Every consumed artifact needs one
   authorized write, named reader, observation point, and assignment tuple. For
   a cycle, split a stable contract from its
   implementation, replace an unnecessary edge, or mark the plan blocked; do
   not hide the cycle with a fictional milestone. Record `cycle_review` as
   `no_cycle`, `cycle_resolved`, or `cycle_blocked`.
5. **Identify the critical path carefully.** Use only supplied duration ranges
   and satisfied-edge evidence. Show uncertain branches and resource
   contention. Do not produce a precise completion date from unknown work.
6. **Create a causal risk statement.** Use `because <condition>, <failure event>
   may occur, causing <criterion or must-preserve impact>`. Separate cause,
   event, and consequence so that a mitigation can target the correct part.
7. **Score without fake precision.** Classify likelihood and impact with cited
   evidence, confidence, and time horizon. A numeric score may sort a ledger but
   may not erase a catastrophic boundary, an unknown, or a low-frequency
   irreversible consequence.
8. **Design controls.** For each material risk name prevention, earliest
   detection signal, trigger threshold supplied by the plan, containment or
   rollback, recovery assignment tuple, verification owner, residual risk, and
   —when it mutates state—no-action and abort transitions. If no control exists,
   expose the decision rather than writing "monitor."
9. **Reconsider order and parallelism.**
   - Pull forward a bounded spike when it resolves a reversal fact.
   - Freeze an interface before parallel consumers when contract risk is lower
     than coordination delay.
   - Serialize irreversible, migration, or shared-resource work when collision
     risk exceeds the evidenced schedule benefit.
   - Keep independent work parallel when it has no shared write or proof
     dependency.
10. **Model fallback topology.** State what can continue if a dependency is
    late, what is paused, which substitute is acceptable, and what outcome the
    fallback cannot prove.
11. **Bind replan triggers.** Name events that invalidate the graph: interface
    change, approval denial, owner loss, capacity breach, failed recovery test,
    expired evidence, or a changed verification bar.
12. **Route residual decisions.** Record each edge's `authority_class`,
    the contract-defined assignment tuple and `residual_risk_authority`; keep it
    outside the current runtime invariant schema. Apply the contract's blocked
    rule before handing off control. Return risk acceptance or intent changes to
    the authorized decision owner and hand only authorized, bounded controls to the assigning lead. Planning
    may recommend order; it may not approve residual risk.

## Options And Tradeoffs

- **Strict serial order:** minimizes shared-write and irreversible-action
  collisions, but may leave safe capacity idle.
- **Contract-first parallelism:** shortens elapsed time and isolates consumers,
  but a weak or unstable contract multiplies rework.
- **Spike the riskiest edge first:** buys early disconfirmation, but delays
  direct outcome work and must not become an unbounded prototype.
- **Adapter, mock, or stub:** unblocks bounded consumer development, but proves
  only the agreed contract—not integration, external state, or user outcome.
- **Fallback path:** preserves partial delivery when a dependency fails, but may
  reduce scope only if the approved outcome remains intact.
- **Rollback or containment before migration:** increases preparation cost, but
  caps irreversible impact and makes a stop rule executable.

Choose the topology that preserves the objective under the named risk boundary,
not the topology with the most parallel boxes.

## Common Failure Patterns

- drawing edges because two tasks are related or owned by different teams;
- treating an expected approval, account, credential, owner, or vendor response
  as already available;
- using a mock, schema file, or worker receipt as integrated dependency proof;
- assigning exact dates from unsupported point estimates;
- sorting by a risk score while ignoring irreversible impact or weak evidence;
- writing vague risks such as "API risk" without cause, event, consequence, or
  trigger;
- naming "monitor closely" as mitigation with no detector, threshold, or owner;
- omitting fallback and rollback for consequential changes;
- allowing the executor to be the only verifier of its mitigation;
- silently reducing success criteria to route around a blocked dependency;
- claiming the plan, migration, or release is safe.

## Output Contract

Return the Decision Core first. Expand only edges and risks that can change
order, parallelism, containment, rollback, or replanning:

- `objective_binding`, `plan_artifact_readiness`, `execution_startability`,
  `known`, `inferred`, and `unknown`;
- a dependency graph with edge type, producer write, consumer read,
  observability, assignment tuple, surface disposition, evidence, expiry,
  fallback, cycle review, authority class, and
  residual-risk authority;
- missing producers, cycles, bottlenecks, shared resources, parallel groups,
  and critical-path ranges or explicit schedule unknowns;
- a risk register with causal statement, affected criterion, likelihood,
  impact, confidence, horizon, prevention, detector, trigger, containment,
  rollback or recovery, no-action and abort transitions when applicable,
  assignment tuple, independent verifier, and residual risk;
- the selected ordering, serious alternative, and tradeoff;
- assumption register, dependency recheck schedule, stop conditions, replan and
  material-decision re-entry triggers;
- blocked work, work that may continue, external or approval-gated actions,
  confidence, `next_recommended_surface`, and `forbidden_claims`.

When a role handoff is requested, also preserve every required field of
`agent_company_bounded_handoff.v0.1`.

## Stop Or Escalate

Stop when every material edge is evidenced, conditional, or explicitly blocked
and every material risk has a decision owner plus a usable trigger. Escalate
missing state to bounded research, contested causal or topology claims to
bounded evidence debate, changed acceptable risk or outcome to the authorized decision owner, and execution plus
independent control verification to the assigning lead. Stop before approving risk,
performing a migration, changing an external account, releasing, or declaring
safety.

## Compression Examples

**Good:** "API work depends on the accepted `schema-v2` artifact, not on the
database migration finishing; UI may start against that frozen contract.
Integrated verification still depends on both API and migration. Production
migration is blocked because operator approval is unknown. Its leading signal
is a failed staging rollback rehearsal; if observed, stop migration preparation
and return the residual data-loss decision to the authorized decision owner. Notification drafting may
continue, but sending remains an unauthorized external action."

**Bad:** "Database, API, UI, and launch all depend on each other. Run them in
parallel to save time, monitor migration risk, and ship when the developers say
their mocks pass."
