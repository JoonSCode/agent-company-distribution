# Implementation Design QA

- Reference ID: `task-pack:design:implementation-design-qa`
- Role: `design`
- Required kernel: `role-kernel:design`
- Task type: `implementation-design-qa`
- Decision: where does an exact implemented candidate match, deviate from, or
  remain unverified against the selected experience intent across required
  sizes, states, inputs, appearances, and accessibility settings?

This pack produces independent design-review evidence from the actual build. It
does not implement fixes, replace functional QA, accept a gate, approve a
baseline change, certify accessibility, decide release disposition, or claim
final verification.

## Decision Core

Apply `design-contract.json#/decision_output_policy`. Lead with the exact
candidate and surface, review and conclusion readiness, the highest-severity
observed deviation, the most consequential unknown, and the exact
re-verification target. Report only observations supported by that candidate's
own environment and artifact evidence. Use named risk scenarios rather than a
Cartesian matrix; retain unsupported required conditions as `unknown` instead
of fabricating rows or inheriting values from another capture.

## Exact Triggers And Non-Triggers

Use this pack when:

- Development has produced an identifiable runnable candidate and Design must
  compare it with an approved flow, hierarchy, visual direction, or acceptance
  target;
- a changed screen or interaction needs observation across target device or
  viewport sizes, critical states, appearance modes, content, and accessibility
  settings;
- a visual regression, state mismatch, focus issue, clipping, overflow,
  hierarchy drift, motion problem, or platform-fit concern needs reproducible
  evidence and severity;
- screenshots, video, accessibility captures, or runtime observations must be
  classified as `match`, `deviation`, or `unknown`;
- a reported Design defect has a new candidate and requires focused
  re-verification without silently closing residual states;
- QA-Release or Seungjeongwon needs a bounded Design evidence packet, not a
  Design-owned verdict.

Do not use it when:

- no exact candidate, runnable matching surface, or observation authority
  exists; first request the missing evidence;
- the task is to invent or change the information architecture, interaction
  model, visual system, product rule, or verification bar; use the corresponding
  Design pack or Uigwe;
- the request is code review, architecture diagnosis, implementation, test
  authoring, production mutation, release approval, or broad functional QA;
- only fixture, mock, static code, design-source artboard, worker narrative, or
  unavailable image path exists for a runtime or visual-quality claim;
- the expected and actual artifacts cannot be matched by state, content, size,
  scale, appearance, or locale and the mismatch would make comparison
  misleading.

## Required Inputs

Require:

1. the selected experience intent and its source when available: approved flow,
   hierarchy, state contract, visual constraints, intentional deviations, and
   Design acceptance targets; when unavailable, observation may continue but
   every comparison conclusion remains `unknown`;
2. exact candidate identity, such as commit, build, artifact digest, target,
   configuration, feature flags, data seed, and observation time;
3. a reproducible runtime entry point and authorized device, simulator,
   browser, Preview, or other matching surface;
4. target device or viewport sizes, scale, orientation or window class,
   appearance, locale, text-size categories, accessibility settings, and input
   methods;
5. realistic fixtures and a critical-state matrix covering the applicable
   normal, boundary, loading, empty, error, offline, permission, interruption,
   partial-success, and recovery states;
6. baseline artifact identity and provenance, or explicit constraints when no
   image baseline exists;
7. known defects, approved deviations, evidence-retention location, executor,
   independent observer, and QA or final-verification owner.

Do not invent a candidate ID, baseline, device, state, expected pixel value,
contrast result, reproduction step, or fix. If the exact build cannot produce a
required state, record that row `unknown` and escalate the fixture or
instrumentation need.

Treat every environment dimension as an independently sourced field. Populate
a row's size, scale, orientation, appearance, locale, text size, accessibility
setting, input, and state only when the evidence for that exact row supplies
the value. A value from another row, a candidate default, or a nearby capture
must not be copied forward. Use `unknown` or `not supplied` for an omitted
dimension even when another row names it.

## Required Runtime And Visual Evidence

A review claim must cite evidence that directly supports its surface:

- direct observation of the exact runnable candidate for interaction,
  transition, focus, interruption, input, or recovery claims;
- fresh screenshots for static visual claims, with candidate, device or
  viewport, scale, state, content, appearance, locale, text size, and timestamp;
- video or event-timestamped capture for motion, temporal feedback, sequencing,
  keyboard, pointer, focus, or gesture behavior;
- accessibility-tree, focus-order, label, trait, value, announcement, or
  assistive-technology observation for semantic accessibility claims;
- measured frame, spacing, text, or color-pair evidence with the method and
  applicable source when a numeric mismatch or contrast claim is made;
- comparable baseline and candidate artifacts for visual-delta claims.

A build log proves buildability only. Automated tests prove only the exercised
behavior. Code inspection can suggest a cause but cannot substitute for the
matching surface. A screenshot cannot prove motion, focus, VoiceOver output,
tap behavior, persistence, or recovery. Without an inspectable image or direct
runtime observation, visual quality remains `unknown`.

## Evidence Priority

Rank evidence from strongest to weakest:

1. approved intent, explicit Design constraints, accepted deviations, and
   current verification bar from their named owners;
2. fresh direct observation and inspectable captures of the exact candidate on
   the matching runtime surface and required state;
3. comparable baseline artifacts and measured evidence with identity,
   provenance, and method;
4. accessibility and interaction captures from the exact candidate, supported
   by focused automated or instrumentation evidence for the same state;
5. implementation diff, component fixture, snapshot test, or code inspection
   used only for supported static or causal hypotheses;
6. executor self-checks, worker receipts, stale screenshots, mockups,
   inaccessible file references, memory, and subjective reports.

Use lower-ranked evidence to request a scenario or form a probable-cause
inference. Never upgrade it into observed runtime or visual proof. Keep
candidate facts in `known`, causal interpretations in `inferred`, and unseen or
unmatched surfaces in `unknown`.

## Current Source Set Recheck Conditions

Refresh and re-materialize the Current Source Set before judging against an
external current fact when:

- expected behavior depends on the current OS, SDK, browser, framework,
  component, material, typography, accessibility, input, or design-resource
  contract;
- the runtime target differs from the source's platform, version, device class,
  accessibility setting, or input mode;
- a current contrast threshold, system metric, component behavior, symbol,
  motion rule, or platform convention is used to classify a deviation;
- the source lacks an access date, applicable version, immutable or live-page
  marker, allowed use, or recheck trigger;
- canonical current evidence conflicts with the stored baseline, operational
  kit, external repository, or prior review.

Do not silently update the approved intent because a platform source changed.
Report the conflict and return any baseline or verification-bar decision to
Uigwe. Keep remote sources read-only and leave implementation adoption to
Development.

## Step-By-Step Method

1. **Bind the review contract.** State the candidate, selected intent, target
   user and task, matching surface, acceptance targets, approved deviations,
   Design readiness, selected highest tier, allowed observation scope,
   evidence owner, and independent verification owner.
2. **Check two readiness states.**
   - `review_readiness=blocked`: the exact candidate, matching runnable surface,
     or observation authority is absent. Block candidate-specific conformance
     and disposition. When supplied requirements support it, still return
     bounded semantic direction with source refs plus one exact evidence
     request; otherwise return only the request.
   - `review_readiness=evidence_ready`: capture and retain direct observations.
   - `conclusion_readiness=ready`: approved intent and oracle are both bound.
   - `conclusion_readiness=unknown`: intent or oracle is absent; preserve the
     observations and classify their conclusion `unknown`, never as a match.
   The review tier remains the tier selected for the experience or the highest
   newly triggered risk; a small screenshot request does not downgrade it.
3. **Pin candidate and environment.** Record commit or digest, target, build
   configuration, feature flags, seed, account or role, OS or browser version,
   device or viewport, scale, appearance, text size, locale, accessibility
   settings, input, and capture time. Bind every capture to the inclusive
   parent-issued observation window from `task_started_at` through
   `evidence_deadline_at`; the deadline is fixed before the work and is not a
   post-observation validation timestamp. Reject evidence whose identity cannot
   be tied to the reviewed candidate or whose capture time falls outside that
   window.
4. **Normalize the baseline.** Record whether each expectation comes from a
   visual artifact, state contract, interaction specification, semantic token,
   current source, or accepted product behavior. Match baseline and candidate
   by content, state, size, scale, appearance, locale, and crop. When exact
   pixel equivalence was never approved, compare semantic constraints instead
   of inventing one.
5. **Use the shared ledger, then sample by risk.** Apply the sole
   `implementation_review_ledger` in `design-contract.json`. Reconcile every
   explicit, supplied, task-pack and risk-derived required or forbidden
   condition exactly once as `covered`, `unknown`, or
   `source_backed_omitted`. Name decision-relevant scenarios rather than
   expanding a Cartesian product. Bind environment and observation provenance
   to the exact candidate; never inherit a value or artifact from another
   candidate, row or capture.
6. **Observe the core task in the actual build.** Start from a reproducible seed
   and perform entry, primary action, feedback, completion, back or dismissal,
   cancellation, failure, retry, interruption, and recovery paths that apply.
   Capture state before, during, and after material transitions.
7. **Capture comparable visual evidence.** Use paired baseline and candidate
   images or a clearly annotated single-candidate constraint check. Preserve
   original resolution when precision matters. Record the crop and scale; do
   not use a resized or different-state image for spacing, clipping, or
   alignment claims.
8. **Review hierarchy and system coherence.** Inspect task prominence,
   grouping, typography roles, semantic color, component states, alignment,
   spacing rhythm, content growth, icon or asset use, appearance behavior, and
   platform familiarity. Distinguish observed mismatch from personal taste.
9. **Review interaction and accessibility.** Observe focus entry and
   restoration, VoiceOver name, trait, value, order and announcements,
   keyboard or switch path, non-color meaning, text reflow, touch or pointer
   affordance, motion interruption, reduced-motion behavior, increased
   contrast, and reduced transparency where applicable.
   Reconcile each motion token's purpose, trigger, timing or spring,
   interruption and reduced-motion disposition. Check reflow at each supplied
   exact width rather than assuming a compact or expanded class represents all
   widths.
10. **Classify each observation.**
    - `match`: the cited evidence satisfies the selected intent on that exact
      surface and state;
    - `deviation`: the cited evidence observably conflicts with the intent;
    - `unknown`: the surface was not observed, evidence is unavailable or
      incomparable, or the oracle is unsettled.
    Assign severity as `critical`, `major`, `minor`, or `note` with a
    user-task, recovery, accessibility, scope, or consistency rationale. Do not
    convert `unknown` into a pass.
11. **Write defect-grade evidence.** For every deviation record finding ID,
    candidate, environment, baseline or expected constraint, start state,
    reproduction steps, expected, actual, artifact refs, affected matrix rows,
    severity and rationale, confidence, probable cause only as `inferred`,
    containment, and the exact re-verification target.
12. **Triangulate selectively.** Preserve three distinct verification layers:
    state-contract semantics, inspectable rendered geometry, and live
    interaction/accessibility observation. Each layer names a verification
    owner from the trusted parent-issued session ownership map. The verifier's
    exact identity and role must differ from the trusted implementation owner;
    another Development alias is not independent. Every named scenario needs a
    fresh, exact-candidate observation for every required layer before the
    review may return a ready or classified result. Every observation's
    `observer_id` must equal the exact trusted verification owner declared for
    each referenced evidence layer; the implementation owner and cross-layer
    verifier substitutions are rejected. Use overlays or difference views for geometry,
    measurements for specific values, video for time, accessibility capture for
    semantics, and code or logs for a causal hypothesis. Automated pixel
    difference is a detector, not a design verdict; antialiasing and dynamic
    content need human interpretation.
13. **Return defects to Development.** Describe the violated experience
    constraint and evidence, not an unauthorized production patch. Development
    owns implementation, dependency choice, and regression-test changes.
14. **Re-verify the new exact candidate.** Capture a new candidate identity and
    repeat the original reproduction plus adjacent risk rows. A developer
    message, diff, rebuilt fixture, or old screenshot does not close a finding.
    Record the new result and residual unknowns; do not erase the original
    evidence.
15. **Route without disposition.** QA-Release and Seungjeongwon own independent
    verification and final execution status. Return changed intent, accepted
    deviation, exception, or verification bar to Uigwe.

## Severity Guidance

- `critical`: prevents the approved primary task or recovery, creates a
  material accessibility barrier, presents an unsafe or irreversible action
  incorrectly, or makes state and consequence dangerously misleading.
- `major`: materially impairs comprehension, completion, navigation, focus,
  content access, or a required state for a meaningful user segment, with no
  reasonable equivalent path.
- `minor`: observable inconsistency or localized degradation that does not
  block the task but violates an approved constraint or weakens coherence.
- `note`: observation, low-risk opportunity, or non-blocking unknown that needs
  tracking but is not an evidenced defect.

Severity is evidence for the authorized verifier. Design does not translate it
into a gate, release, or risk-acceptance decision.

## Options And Tradeoffs

- **Shared ledger versus risk-based sampling:** the machine-readable Design
  contract owns coverage, scenario, provenance and omission rules. Risk chooses
  observations but cannot delete or rewrite a declared condition.
- **Side-by-side versus overlay or difference image:** side-by-side preserves
  context; overlays expose geometry; difference images detect change but can
  exaggerate harmless rendering noise.
- **Screenshot versus video:** screenshots support static hierarchy and layout;
  video supports sequence, focus, timing, motion, and interruption but is
  slower to inspect and cite.
- **Simulator or browser viewport versus physical device:** simulated surfaces
  are reproducible and fast; a real device is stronger when hardware,
  rendering, input, performance, camera, haptics, or accessibility behavior is
  material.
- **Manual observation versus automated snapshots:** manual review judges task
  and semantic fit; automation catches repeatable deltas but needs stable data,
  tolerances, and human disposition.
- **Visual baseline versus constraint baseline:** a visual baseline is precise
  for a frozen composition; semantic constraints tolerate content and platform
  variation better. Use the baseline actually approved.
- **Focused recheck versus adjacent regression sweep:** focused recheck is fast;
  adjacent rows are needed when a fix can alter shared tokens, layout, state,
  navigation, focus, or content behavior.

Choose the smallest evidence set that can falsify the approved constraint on
the matching surface. More screenshots do not compensate for missing critical
states or candidate identity.

## Common Failure Patterns

- reviewing source code, a component fixture, or a build log as though it were
  the integrated experience;
- saying "pixel perfect," "looks good," "accessible," or "matches" without
  inspectable images or direct runtime evidence;
- comparing different content, state, size, scale, appearance, locale, or crop
  without recording the mismatch;
- testing one default screen and omitting loading, empty, error, long text,
  Dynamic Type, dark appearance, interruption, or recovery that the contract
  requires;
- using risk-based sampling to delete a required ledger cell instead of
  retaining it as `planned`, `blocked`, or `unknown`;
- reporting a visual screenshot as proof of focus, VoiceOver, motion, tap,
  persistence, or recovery;
- logging "spacing is off" without baseline, expected constraint, actual
  observation, reproduction, artifact, or severity rationale;
- inventing a numeric pixel or contrast oracle after seeing the candidate;
- treating an automated image-diff percentage as design acceptance;
- closing a finding from an implementation claim or diff without fresh
  observation of the new exact candidate;
- changing the baseline to match the implementation without Uigwe or the named
  decision owner;
- implementing the fix, approving QA, certifying accessibility, or claiming
  release readiness from Design scope.

## Output Contract

Return the Decision Core first. Without an exact candidate, return only bounded
source-backed semantic direction, its limits, and one evidence request; make no
`match`, `deviation`, acceptance, rejection, or disposition claim. With an
exact candidate, expand only observations, defects, and named scenarios needed
for disposition by QA-Release or Seungjeongwon:

- `design_readiness`, selected highest `tier`, target task, matching surface,
  exact candidate identity, environment, selected intent refs, accepted
  deviations, observation authority, `known`, `inferred`, and `unknown`;
- a baseline inventory that identifies each visual, interaction, state,
  semantic, accessibility, and current-source constraint plus its provenance;
- the validated shared-ledger record, including named scenarios, exact
  condition reconciliation, candidate-bound environment and observation
  provenance, motion-token dispositions, width-specific reflow expectations,
  and the three independently owned verification layers;
- an evidence index with image, video, accessibility, measurement, log, or test
  type; candidate and environment identity; capture time; provenance; and the
  claims each artifact can and cannot support;
- observations expressed only as `match`, `deviation`, or `unknown`, each with
  surface, state, evidence refs, confidence, and `critical|major|minor|note`
  severity rationale;
- a defect record for every deviation with reproduction, expected, actual,
  affected rows, user consequence, probable cause labeled `inferred`,
  containment, owner handoff, and exact re-verification target;
- matches kept separate from uncovered rows, blocked fixtures, stale evidence,
  and other residual unknowns;
- focused and adjacent re-verification scope for a new exact candidate,
  Current Source Set recheck needs, confidence, residual risk, and exactly one
  `next_recommended_surface`;
- unchanged company `forbidden_claims` in any bounded role handoff.

Preserve every required field of `agent_company_bounded_handoff.v0.1` when a
role handoff is requested. Do not emit an overall pass, gate, no-regression,
release, or completion verdict.

## Stop Or Escalate

When the exact candidate, matching runtime, or observation authority is absent,
block conformance and disposition, give bounded source-backed direction when
available, and return one evidence request. If no supplied source supports a
direction, return only that request. Missing approved intent or a decisive
oracle does not block direct observation: retain the evidence and keep its
conclusion `unknown`. Mark inaccessible images,
unproduced states, and incomparable captures `unknown`; route fixture,
build-access, or implementation needs to Development through Seungjeongwon.
Return any changed intent, accepted deviation, exception, risk tolerance, or
verification bar to Uigwe. Route missing current platform evidence to
JangYeongsil, contested interpretation to Jiphyeonjeon, and final independent
verification or QA disposition to QA-Release and Seungjeongwon. Stop before
production edits, baseline mutation, gate approval, accessibility
certification, release readiness, or final verification.

## Compression Examples

**Good:** "Candidate `build-42` was directly observed at 320 pt width with AX5
text in the retry state. Against constraint `VIS-7`, the title truncates before
the distinguishing noun; capture `obs-ax5-retry` and the recorded focus trace
support a major deviation because the recovery choice becomes ambiguous.
Default 390 pt light mode matches the approved hierarchy. Dark appearance,
Reduce Motion, and the permission-denied state were not observed and remain
unknown. Development reports a fix in `build-43`, but that is not closure:
re-run the AX5 retry reproduction and the adjacent empty and error rows on the
new exact candidate. QA-Release owns disposition."

**Bad:** "The screenshots look close enough and the developer fixed the one
issue, so design QA passes and the build is ready to release."
