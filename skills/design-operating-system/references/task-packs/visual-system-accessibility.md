# Visual System And Accessibility

- Reference ID: `task-pack:design:visual-system-accessibility`
- Role: `design`
- Required kernel: `role-kernel:design`
- Task type: `visual-system-accessibility`
- Decision: what semantic visual system, hierarchy, typography, color, motion,
  and accessibility constraints should express the approved experience across
  its required surfaces and states?

This pack turns a settled experience structure into coherent, testable visual
constraints and proportional visual artifacts. It does not resolve an
unsettled product flow, generate an unbounded brand system, adopt an external
kit, implement production UI, certify accessibility, approve a gate, or claim
visual quality without inspectable visual or runtime evidence.

## Decision Core

Apply `design-contract.json#/decision_output_policy`. Lead with the semantic
hierarchy, selected visual direction, existing roles to reuse, the smallest
new token or component-state need, the accessibility constraint most likely to
break the direction, and its reversal evidence. Distinguish proposed
constraints from measured or observed quality. Expand only named content,
appearance, width, state, motion, and assistive scenarios that can falsify a
required constraint; do not generate a token catalog or device matrix merely
because dimensions are available.

## Exact Triggers And Non-Triggers

Use this pack when:

- an approved screen or flow needs visual hierarchy, layout rhythm,
  typography, semantic color, surface, icon, or motion direction;
- duplicated or hard-coded values need a semantic token model and component
  state rules;
- light, dark, increased-contrast, reduced-transparency, reduced-motion,
  localization, or content-growth behavior needs explicit constraints;
- Dynamic Type or an equivalent platform text-scaling mode exposes hierarchy,
  wrapping, reflow, truncation, focus, or action-placement risk;
- a new or changed visual artifact is required at the proportional fidelity of
  the selected Design tier;
- a visual direction must become an implementable handoff with measurable
  tokens, component roles, state variants, and runtime verification targets;
- an existing visual system needs critique and fresh images or runtime
  captures of the matching surface are actually available.

Do not use it when:

- the target task, information hierarchy, state model, control semantics, or
  recovery behavior can still reverse the visual artifact; use
  `task-pack:design:flow-interaction` or return to Uigwe;
- the question is whether an exact implementation matches an approved visual
  direction; use `task-pack:design:implementation-design-qa`;
- only wording, voice, or localization copy craft remains; request
  `copywriting-operating-system`;
- the request is an unbounded logo, illustration, marketing campaign, brand
  exploration, asset library, production implementation, or release decision;
- no image, editable artifact, or runtime evidence is available and the request
  is to judge current visual quality rather than specify a bounded direction;
- a current contrast threshold, platform material behavior, typography API,
  accessibility requirement, or design-resource capability is material but no
  applicable Current Source Set is available.

## Required Inputs

Require:

1. the approved target user, task, context, platform, matching surface,
   observable outcome, desired emotion, flow, hierarchy, component semantics,
   critical states, non-goals, and must-preserve behavior;
2. Design readiness inputs and every signal needed to select the highest
   applicable `minimum`, `standard`, or `deep` tier;
3. current product tokens, components, type roles, color roles, icon sources,
   spacing rules, brand constraints, and accepted deviations, including
   explicit unknowns;
4. realistic content at shortest, typical, longest, empty, error, and localized
   lengths, plus data density and image or asset rights constraints;
5. target device or viewport sizes, orientations or window widths, appearance
   modes, text-size categories, assistive settings, and input methods;
6. the exact artifact requested—constraint brief, token table, component state
   sheet, annotated screenshot, isolated native Preview, or editable design
   file—and its allowed write and sharing scope;
7. current source references for any versioned typography, contrast,
   accessibility, motion, material, symbol, or component claim.

If values such as a brand color, typeface license, minimum width, contrast
target, motion duration, asset right, or supported accessibility setting are
not supplied or observed, record them as `unknown`. Do not invent measurements
or silently turn examples into approved tokens.

## Required Observation And Visual Evidence

For critique or a claim about current visual quality, require:

- fresh screenshots, video, or direct runtime observation of the exact
  matching surface, with candidate identity, device or viewport, scale,
  appearance, text size, locale, state, and observation time;
- the selected baseline or intent artifact at a comparable crop, size, state,
  content, and appearance;
- inspectable local token, component, or design-library definitions when
  consistency or reuse is claimed;
- measured color pairs and method when a contrast claim is made;
- actual content reflow and focus behavior under the required text sizes,
  localization, and accessibility settings;
- motion capture or direct observation when timing, continuity, spatial
  meaning, or reduced-motion behavior is judged.

Textual descriptions, code, token names, a worker receipt, or an unavailable
image path can support a verification plan but cannot prove that a surface
looks coherent, matches a baseline, avoids clipping, or has acceptable
contrast. Label unsupported visual conclusions `unknown`.

## Evidence Priority

Rank evidence from strongest to weakest:

1. approved experience intent, hierarchy, critical states, product truth,
   accessibility target, non-goals, and must-preserve constraints;
2. fresh, inspectable images or direct runtime observation of the exact
   matching surface under the target state and settings;
3. current local semantic tokens, component definitions, editable artifacts,
   asset records, and measured values reconciled with the runtime;
4. a resolver-materialized Current Source Set containing applicable canonical
   platform and accessibility sources;
5. attributable user evidence about comprehension, readability, preference,
   sensory needs, or motion effects in the target context;
6. operational kits, external systems, benchmark galleries, trends, generated
   images, screenshots from other products, and subjective preference.

Use lower-ranked material to form a hypothesis, not to overrule product intent
or prove visual quality. Treat Figma, ImageGen, curated skills, and remote
repositories as capabilities or read-only evidence, not normative authority or
production adoption permission.

## Current Source Set Recheck Conditions

Refresh and re-materialize the Current Source Set before a material decision
when:

- the decision depends on current contrast, typography, Dynamic Type, motion,
  transparency, accessibility, system-material, symbol, component, or
  design-resource guidance;
- the target OS, SDK, device family, appearance, input mode, accessibility
  setting, or product design-resource version changed;
- a claimed numeric threshold, API behavior, template capability, plan
  entitlement, license, or redistribution right lacks current provenance;
- the source has no access date, applicable version, immutable or live-page
  marker, allowed use, or recheck trigger;
- a current canonical source conflicts with an operational kit, external
  repository, old screenshot, or generated visual.

Keep external sources read-only. Preserve old records, and mark affected
decisions `unknown` or `conditional` until refresh. Development must approve
dependency or source adoption; the authorized specialist workflow must govern
remote Figma mutation or published design-system mappings.

## Step-By-Step Method

1. **Bind the visual decision.** State target user, task, context, platform,
   matching surface, approved hierarchy and state model, desired emotion,
   artifact scope, non-goals, must-preserve behavior, `known`, `inferred`, and
   `unknown`.
2. **Set readiness and tier.** Apply the Design kernel before making artifacts.
   A bounded token or style adjustment that preserves semantics may be
   `minimum`; a new screen, hierarchy, component state system, or meaningful
   visual interaction is `standard`; a new product, major redesign, onboarding,
   payment, privacy, permission, health, destructive action, or AI agency is
   `deep`. Under `blocked`, return only one evidence request. Under
   `conditional`, create only one low-fidelity artifact that tests the named
   reversal unknown.
3. **Pin the evidence surface.** Record candidate or baseline identity, size,
   scale, appearance, text size, locale, state, and content. If no inspectable
   visual or runtime evidence exists, separate proposed constraints from
   observed quality and keep the latter `unknown`.
4. **Restate the content hierarchy.** Order the primary task, title, key value,
   supporting context, status, actions, metadata, and recovery content. Use
   structure, grouping, position, type role, and spacing before relying on hue,
   decoration, or motion.
5. **Inventory and normalize tokens.** Map existing raw values to semantic
   roles for content, background, fill, border, text, status, spacing, radius,
   elevation or depth, icon, and motion. Reuse product or system roles before
   adding a token. For every motion token, record purpose, trigger, duration or
   spring, interruption, reduced-motion disposition and source. Record aliases,
   component consumers, states, appearance variants, and migration owner
   without editing production definitions.
6. **Define typography behavior.** Name semantic text roles, scaling behavior,
   weight and emphasis, line count policy, wrapping, truncation exception,
   alignment, line spacing, numeral behavior, localization growth, and
   fallback. Test hierarchy through text scaling; do not preserve a fixed
   artboard by clipping or shrinking essential text.
7. **Define layout and density.** Specify container behavior, safe-area or
   window relationship, alignment, minimum and maximum content widths when
   evidenced, spacing rhythm, grouping, touch or pointer affordance, image
   treatment, and reflow rules at every supplied exact width. Do not let a
   compact or expanded class stand in for width-specific structure and content
   priority. Distinguish exact values from principles or unresolved
   implementation values.
8. **Define semantic color and contrast.** Assign color by role and state across
   required appearances. Pair color with text, symbol, shape, position, or
   other non-color meaning. Record foreground/background pairs, measurement
   method, target source, actual result, and unknowns; never claim compliant
   contrast from a token name or visual impression.
9. **Define component states.** Cover enabled, highlighted or pressed, focused,
   selected, disabled, loading, success, warning, error, destructive,
   unavailable, and content-overflow states that apply. Keep state semantics
   consistent across typography, color, icon, and announcement behavior.
10. **Define motion and material behavior.** State the purpose, trigger,
    property, duration or spring only when supported, interruption, completion
    feedback, performance risk, and reduced-motion or reduced-transparency
    alternative. Remove motion that does not explain continuity, state, or
    agency. Treat platform materials as functional behavior subject to current
    source and runtime verification, not decoration.
11. **Create proportional artifacts.** For `minimum`, annotate the exact delta.
    For `standard`, provide the relevant token and component-state sheet plus
    one representative composition. For `deep`, include materially distinct
    visual hypotheses only when they differ in hierarchy, interaction,
    identity, or emotion, and include realistic critical-state prototypes.
    Keep native Preview or Figma work isolated and within authorized scope.
12. **Inspect required variants.** Use realistic content to observe the
    artifact or runtime at target sizes, appearances, locales, text scales, and
    applicable increased-contrast, reduced-transparency, and reduced-motion
    settings. Record `match`, `deviation`, or `unknown`; do not infer unseen
    variants.
13. **Compile the Development handoff.** Provide semantic token roles, component
    states, hierarchy, content behavior, asset provenance, intentional
    deviations, accessibility targets, unresolved values, and exact runtime
    observations needed. Screenshots illustrate intent but do not replace
    constraints.
14. **Route without approving.** Return structural product choices to Uigwe,
    missing current facts to JangYeongsil, contested directions to
    Jiphyeonjeon, and approved implementation plus independent verification to
    Seungjeongwon.

## Options And Tradeoffs

- **Semantic shared tokens versus local component values:** shared roles improve
  coherence and appearance switching; local values contain a one-off need but
  can create drift and hidden variants.
- **System typography versus custom type:** system roles inherit platform
  scaling and familiarity; custom type may express identity but adds licensing,
  fallback, metric, script, and accessibility work.
- **Structural hierarchy versus color-led hierarchy:** structure survives
  grayscale and sensory differences; color adds emphasis but cannot carry
  meaning alone.
- **Flexible reflow versus fixed composition:** reflow supports content growth
  and window changes; fixed composition may preserve an art-directed moment but
  needs explicit bounds and alternate layouts.
- **Opaque surfaces versus platform material:** opacity can improve predictable
  legibility and identity; material can reinforce control or navigation layers
  but depends on background, settings, performance, and current platform
  behavior.
- **Restrained motion versus expressive motion:** restraint protects speed,
  focus, and motion sensitivity; expressive motion can add continuity or
  delight when it has purpose and an equivalent reduced-motion state.
- **One representative artifact versus a component matrix:** one composition is
  faster for a bounded change; a matrix better exposes state and token
  coherence but costs more and does not replace runtime observation.
- **Product-system reuse versus a new visual family:** reuse reduces learning
  and implementation drift; a new family may serve a distinct content mode but
  needs evidence, migration cost, and consistency rules.

Choose by task hierarchy, content variability, platform fit, accessibility,
product identity, implementation cost, and verification surface—not trend
novelty.

## Common Failure Patterns

- declaring a surface polished, delightful, accessible, or matched without
  inspectable image or runtime evidence;
- starting with hex values, shadows, glass, gradients, or type sizes before
  content hierarchy and semantic roles;
- using color alone for status, selection, validation, or destructive meaning;
- preserving a fixed-height card by clipping, shrinking, or truncating
  essential content under Dynamic Type or localization;
- claiming contrast from appearance, a design token name, or an unrecorded
  calculator result;
- creating light and dark palettes without component-state or image-treatment
  behavior;
- specifying animation without purpose, interruption, performance, or
  reduced-motion behavior;
- treating a generated image, trend gallery, Figma kit, or remote repository as
  canonical or adoption-approved;
- producing artboards with no token mapping, component states, content rules,
  asset rights, or runtime verification plan;
- allowing visual polish to conceal an unresolved flow, product truth, or error
  state;
- implementing production UI, approving accessibility, or claiming release
  readiness from Design scope.

## Output Contract

Return the Decision Core first, then expand only the semantic roles, named
scenarios, and verification details required by the selected tier:

- one `agent-company.design-task-evidence/v0.1` bounded evidence envelope whose
  exact task pair is `visual-system-accessibility` /
  `task-pack:design:visual-system-accessibility`; include decision, separated
  evidence, named scenarios with accessibility checks, visual-system-specific
  deliverable refs, trusted implementation and verification owner IDs,
  verification plan refs, and the stop boundary;
- `design_readiness`, selected highest `tier`, target user, task, context,
  platform, matching surface, observable outcome, desired emotion, `known`,
  `inferred`, and `unknown`;
- artifact scope, approved hierarchy and critical states, current visual
  evidence refs, candidate or baseline identity, and explicit evidence limits;
- a semantic token table with role, alias or raw value when known, component
  consumers, states, appearance variants, source, and unresolved values;
- typography roles and scaling, wrapping, truncation, width-specific reflow,
  localization, and fallback rules;
- layout hierarchy, spacing and alignment logic, density and content-growth
  behavior across required sizes;
- semantic color and non-color meaning, measured contrast pairs and method when
  available, appearance behavior, and unsupported claims left `unknown`;
- component visual states, icon and asset provenance, motion-token purpose,
  trigger, timing or spring, interruption, and reduced-motion or
  reduced-transparency disposition;
- proportional artifact references with size, scale, state, appearance,
  locale, text-size, and provenance metadata;
- selected direction, serious alternative when required, rejection evidence,
  intentional deviations, Development constraints, runtime verification
  matrix, confidence, residual risk, and exactly one
  `next_recommended_surface`;
- unchanged company `forbidden_claims` in any bounded role handoff.

Preserve every required field of `agent_company_bounded_handoff.v0.1` when a
role handoff is requested. Phrase unrendered decisions as proposed constraints,
not observed quality.

## Stop Or Escalate

Stop with one evidence request when an unsettled flow, missing matching surface,
unknown asset right, or unavailable visual evidence can reverse the artifact.
Return product, scope, brand-authority, risk, privacy, or verification-bar
choices to Uigwe. Route missing current platform or accessibility facts to
JangYeongsil, copy craft to `copywriting-operating-system`, contested visual
directions to Jiphyeonjeon, and approved implementation plus independent
runtime verification to Seungjeongwon. Stop before production edits, dependency
adoption, unapproved Figma mutation, asset publication, accessibility
certification, QA disposition, gate approval, or final verification.

## Compression Examples

**Good:** "Readiness is ready; tier is standard. The approved hierarchy is
title, current status, primary value, then actions. Use existing semantic text
and surface roles; add only a `statusAttention` alias if the local inventory
cannot express that state. Titles and values wrap and reflow at the supplied
accessibility sizes; essential status text never truncates. Warning meaning
uses text plus symbol, not amber alone. Motion only connects syncing to settled
state and becomes a non-moving progress/status update under Reduce Motion.
There is no supplied screenshot or measured color pair, so present visual
quality and contrast remain unknown. Produce one annotated state sheet, then
verify the exact candidate across the supplied sizes, appearances, locales, and
accessibility settings."

**Bad:** "Use 14 pt gray labels, glass cards, a brighter blue, and a smooth
spring. It will look premium, pass accessibility, and work at every size."
