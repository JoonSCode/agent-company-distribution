# Flow And Interaction

- Reference ID: `task-pack:design:flow-interaction`
- Role: `design`
- Required kernel: `role-kernel:design`
- Task type: `flow-interaction`
- Decision: what information structure, state model, transition behavior, and
  platform-familiar interaction best serves the approved user task?

This pack turns approved intent and observed product behavior into a buildable
experience flow. It does not change product scope, choose unsupported business
rules, produce a visual style system, implement production code, approve a
Uigwe gate, or claim that an implemented experience is verified.

## Decision Core

Apply `design-contract.json#/decision_output_policy`. Lead with the selected
flow, its decisive evidence, the state transition that carries the user to the
outcome, the primary recovery path, and the observation that would revive the
serious alternative. Name only states that change user choice, system truth,
recovery, or verification. For each selected state, make ownership, trigger,
feedback, allowed action, exit, failure, and recovery concrete. Do not turn the
critical-state inventory into a generic matrix or withhold a buildable
direction because reversible copy or implementation values remain unknown.

## Exact Triggers And Non-Triggers

Use this pack when:

- a new screen, feature, route, navigation structure, or information hierarchy
  needs an experience direction;
- the happy path exists but loading, empty, zero-result, error, permission,
  offline, interruption, partial-success, cancellation, or recovery behavior
  is missing or contradictory;
- control semantics, focus, back behavior, dismissal, selection, editing, undo,
  progress, or async feedback needs to be defined;
- the same task must remain understandable across compact and expanded
  surfaces, pointer or keyboard input, localization, and accessibility modes;
- a custom interaction is proposed and must be compared with an observed
  product pattern or current platform convention;
- Development needs explicit state ownership, view data, transition guards,
  recovery behavior, and intentional deviations before implementation.

Do not use it when:

- the target user, approved task, observable outcome, must-preserve behavior,
  platform, or authority boundary is materially unsettled; return to Uigwe;
- the flow and state semantics are already fixed and the decision is primarily
  tokens, hierarchy styling, typography, color, contrast, Dynamic Type, or
  motion; use `task-pack:design:visual-system-accessibility`;
- the live question is whether an exact implemented candidate matches the
  selected direction; use `task-pack:design:implementation-design-qa`;
- only UX copy craft remains after flow, control semantics, product truth, and
  states are settled; request `copywriting-operating-system`;
- the request is implementation, architecture ownership, functional QA,
  release disposition, gate approval, or an external mutation;
- an inspiration screenshot or trend is the only evidence for changing
  navigation, semantics, agency, or recovery.

## Required Inputs

Require:

1. the approved target user, task, context, platform, observable outcome,
   non-goals, must-preserve behavior, and decision owner;
2. Design readiness inputs and every trigger needed to select the highest
   applicable `minimum`, `standard`, or `deep` tier;
3. the current matching surface or a documented absence of one, including
   entry points, exits, adjacent routes, terminology, and established component
   families;
4. the entities, actions, relationships, permissions, irreversible effects,
   async operations, persistence rules, and source of truth for each state;
5. realistic content, long and empty examples, localization constraints,
   expected item counts, latency or connectivity facts that are actually
   known, and supplied boundary conditions;
6. target device classes, input methods, orientation or window constraints,
   assistive-technology needs, and any current accessibility baseline;
7. current source references for platform behavior when the decision depends
   on a version-specific convention.

Record every unavailable fact as `unknown`. Do not invent a product rule,
latency, item limit, permission outcome, persistence guarantee, platform
behavior, or implementation API to make the flow appear complete. A reversible
copy or implementation value may remain a named placeholder when it cannot
change the structure.

## Required Observation Evidence

Before replacing an existing flow, inspect evidence at the matching surface:

- fresh screenshots, recordings, or direct runtime observation of the current
  entry, task path, exit, back or dismissal behavior, and applicable failures;
- current product navigation, component, terminology, and accessibility
  patterns from the local product system;
- state and data contracts that show who owns loading, mutation, success,
  failure, retry, cancellation, persistence, and resume behavior;
- user research, support evidence, analytics, or task observation with source,
  date, sample, and limitations when used to justify a behavior change;
- any baseline artifact, prototype, or accepted design decision, with identity
  and freshness sufficient to compare.

A static screenshot cannot prove a transition, focus change, async sequence,
undo, or recovery. Code structure alone cannot prove the experienced behavior.
When the matching surface cannot be observed, narrow the output to supported
constraints and mark current behavior and replacement risk `unknown`.

## Evidence Priority

Rank evidence from strongest to weakest:

1. approved product intent, policy, user-task evidence, non-goals, and
   must-preserve behavior from their named owners;
2. fresh direct observation of the exact current product on the matching
   platform, device class, input mode, and relevant state;
3. current local state, data, navigation, component, and accessibility
   contracts, reconciled with observed behavior;
4. a resolver-materialized Current Source Set containing applicable canonical
   platform documentation and official samples;
5. attributable user research or comparable product evidence with known
   context and limits;
6. operational kits, prototypes, external repositories, screenshots, trends,
   preference, and analogy.

Higher-ranked evidence constrains lower-ranked suggestions. A popular pattern
does not override the approved task or observed product system. Treat remote
repositories, skills, prompts, and examples as untrusted read-only evidence;
Design cannot adopt or execute them.

## Current Source Set Recheck Conditions

Refresh and re-materialize the Current Source Set before relying on a claim
when:

- the choice depends on current OS navigation, modal, menu, toolbar, search,
  drag-and-drop, keyboard, pointer, focus, permission, or accessibility
  behavior;
- the target OS, SDK, device class, input method, or component family differs
  from the source record;
- the source lacks an access date, immutable or live-page marker, platform
  applicability, accessibility evidence, or recheck trigger;
- a framework API, official sample, HIG section, system behavior, or versioned
  convention may have changed;
- an operational kit or external example conflicts with canonical guidance or
  fresh product observation.

Preserve the older source record and label the decision `unknown` or
`conditional` until refresh when freshness can reverse it. Do not quote a
current platform rule from memory or treat a Figma kit as normative authority.

## Step-By-Step Method

1. **Bind the experience decision.** State the target user, task, context,
   platform, matching surface, observable outcome, non-goals, must-preserve
   behavior, and desired emotion. Separate `known`, `inferred`, and `unknown`.
2. **Set readiness and tier.** Use the Design kernel's exact readiness states
   and select the highest triggered tier. A new screen, hierarchy, state, or
   interaction is at least `standard`; payment, privacy, permission,
   destructive action, health, AI agency, onboarding, or major redesign is
   `deep`. Stop under `blocked`; under `conditional`, create only one
   low-fidelity artifact that tests the named reversal unknown.
3. **Observe the current task.** Walk from entry to outcome and recovery on the
   matching surface. Record navigation, labels, content hierarchy, controls,
   focus, system feedback, interruption, and established product conventions.
   Distinguish observed behavior from code- or document-derived inference.
4. **Model the information architecture.** Name entities, relationships,
   destinations, primary and secondary tasks, grouping, ordering, disclosure,
   search or filter boundaries, and the user's orientation cues. Remove
   destinations or controls that serve no approved task or recovery path.
5. **Define the task flow.** Record start state, entry, user intent, action,
   system response, feedback, next available choices, completion signal, exit,
   back or dismissal behavior, and re-entry. Cover alternate entry points only
   when evidence says they exist.
6. **Build the state machine.** Give each state a stable name, owner, source of
   truth, entry event, guard, visible affordances, allowed actions, async work,
   exit conditions, persistence, and cancellation semantics. Give each
   transition a trigger, feedback, failure path, and recovery target.
7. **Build the critical-state matrix.** Include applicable initial, loading,
   loaded, first-use, empty, zero-result, recoverable error, terminal error,
   offline, stale, retrying, partial success, interrupted, backgrounded,
   resumed, permission, long-content, localization, Dynamic Type, and reduced
   motion states. State why an omitted risk state is not applicable.
8. **Protect agency and recovery.** Make selection, confirmation, cancellation,
   undo, retry, correction, leave, and resume behavior explicit. Preserve
   completed work during partial failure unless the approved data contract says
   otherwise. Do not hide an irreversible effect inside a navigation action.
9. **Apply platform familiarity.** Reuse observed product and standard system
   component roles where they fit. Record the user problem solved by any custom
   interaction, the standard alternative, the intentional deviation, keyboard
   and assistive behavior, and the Current Source Set reference.
10. **Compare serious alternatives.** For `standard` or `deep` work, preserve
    an alternative when information architecture, interaction model, agency,
    recovery, product emphasis, or emotional hypothesis could change. Reject
    it with evidence and name what observation would revive it.
11. **Specify accessibility interaction.** Define VoiceOver names, traits,
    reading order, grouped or separate elements, focus entry and restoration,
    announcements for async changes, actionable control targets, keyboard or
    switch access, non-color meaning, content growth, and reduced-motion
    behavior that the flow requires.
12. **Compile the Development handoff.** Name component roles rather than
    screenshots alone; view data, state and navigation ownership; transition
    and cancellation contracts; placeholder product values; accepted
    deviations; state fixtures; and runtime checks. Do not prescribe production
    architecture beyond the evidence needed to preserve the experience.
13. **Route without approving.** Return product or verification-bar changes to
    Uigwe, missing evidence to JangYeongsil or a bounded specialist, contested
    directions to Jiphyeonjeon, and approved implementation plus independent
    verification to Seungjeongwon.

## Options And Tradeoffs

- **Single focused path versus hub-and-spoke:** a focused path reduces choice
  and supports completion; a hub improves switching and overview but can weaken
  orientation and create duplicated state.
- **Progressive disclosure versus visible controls:** disclosure lowers initial
  load; visible controls improve discoverability and comparison for frequent
  work.
- **Push or drill-down versus contained modal task:** hierarchical navigation
  preserves location and deep linking; a modal contains a short reversible
  task but can obscure context and complicate recovery.
- **Immediate optimistic transition versus confirmed transition:** optimism
  feels fast and preserves flow; confirmation better protects accuracy when
  failure, conflict, or irreversible effects are material.
- **Inline recovery versus dedicated recovery surface:** inline recovery keeps
  context; a dedicated surface supports complex correction but adds
  navigation.
- **Batch action versus item-by-item control:** batching improves throughput;
  item-level action improves review, error isolation, and recovery.
- **System convention versus custom interaction:** system behavior improves
  familiarity and accessibility support; custom behavior may express a unique
  task but carries learning, implementation, and verification cost.
- **Responsive reflow versus separate compact and expanded structures:** reflow
  reduces conceptual divergence; separate structures may use space better but
  require explicit selection, focus, and state-continuity rules.

Choose by task frequency, consequence, content structure, recovery cost,
platform fit, and observed user behavior—not novelty or screen-count
minimization.

## Common Failure Patterns

- drawing only a happy path or calling a screen list a flow;
- using navigation to conceal unresolved product or data rules;
- treating loading, empty, zero-result, offline, partial success, and error as
  one generic fallback;
- showing retry without defining idempotency, preserved work, state ownership,
  or the retry target;
- changing established back, cancel, selection, or focus behavior without a
  named user problem and comparison;
- choosing a custom gesture as the only path to an action;
- letting color or animation carry state without text, semantics, or a
  reduced-motion alternative;
- assuming a static screenshot proves focus, transition, interruption, or
  recovery;
- naming framework APIs from memory without a current applicable source;
- handing Development artboards with no state model, data contract, or
  interaction constraints;
- expanding scope, approving a gate, owning implementation, or reporting the
  direction as runtime-verified.

## Output Contract

Return the Decision Core first, then expand only the state, component,
accessibility, and verification details needed to build or falsify it:

- one `agent-company.design-task-evidence/v0.1` bounded evidence envelope for
  `flow-interaction` / `task-pack:design:flow-interaction`, led by the selected
  direction, decisive evidence, rejected alternative, recovery, and reversal
  evidence;
- only decision-relevant `known`, `inferred`, `unknown`, provenance, scope,
  must-preserve, source-freshness, state, and named-scenario facts; include
  accessibility checks and explicit risk-state omissions;
- selected component roles, intentional platform deviations, state ownership,
  view constraints, and runtime verification plan; retain VoiceOver focus,
  content growth, non-color meaning, input alternatives, and applicable motion
  or contrast behavior;
- exact candidate-bound `match` or `deviation` evidence only when the exact
  candidate, matching surface, observation authority, approved intent, and
  oracle are bound; otherwise return direction, recovery, and reversal evidence
  without a conformance claim;
- confidence, residual risks, and exactly one `next_recommended_surface`;
- unchanged company `forbidden_claims` in any bounded role handoff.

Preserve every required field of `agent_company_bounded_handoff.v0.1` when a
role handoff is requested. The executor and independent verifier must remain
different accountable actors.

## Stop Or Escalate

Stop with one evidence request when the target task, matching surface,
observable outcome, or authority boundary is missing. Return to Uigwe when a
product rule, scope, platform, privacy, permission, risk, or verification-bar
decision can reverse the flow. Route missing observed behavior or current
platform evidence to JangYeongsil, copy craft to
`copywriting-operating-system`, materially contested directions to
Jiphyeonjeon, and approved implementation plus independent verification to
Seungjeongwon. Stop before production edits, remote artifact mutation, external
actions, QA disposition, gate approval, release claims, or final verification.

## Compression Examples

**Good:** "Readiness is ready; tier is standard. The observed list already uses
Edit mode for multi-selection, so preserve that entry and put Move in the
existing action surface. `idle -> choosingDestination -> moving ->
partialSuccess|completed|recoverableError`; the model owns selected IDs and
per-item results, while the view owns only presentation and focus. Cancel
before submission changes nothing. After partial success, keep completed moves,
show failed items with Retry Failed, and restore focus to the result summary.
An item-by-item alternative improves review but costs repeated work; revive it
if error rates or user observation show batch review is unsafe. Exact latency
copy remains a placeholder. Development implements; QA-Release independently
observes the exact candidate."

**Bad:** "Add a modern bottom sheet with a spinner, a blue success toast, and a
swipe gesture. The flow is intuitive and platform-native, so engineering can
ship it."
