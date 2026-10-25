# Design methods

## Judgment sequence

Ask these in order and stop when evidence is insufficient.

1. Purpose: What user task deserves time and attention, and what should not be built?
2. Agency: Can people understand, choose, undo, leave, and recover?
3. Responsibility: What privacy, safety, accessibility, trust, interruption, or secondary effect must the design handle?
4. Familiarity: Which product or system patterns reduce learning without erasing product identity?
5. Flexibility: Do text size, content length, appearance, input, device size, localization and interrupted use still work?
6. Simplicity: Is each element necessary for the primary task or an explicit recovery path?
7. Craft: Are hierarchy, alignment, rhythm, typography, motion and feedback coherent at the matching surface?
8. Delight: What intended emotion emerges from the whole experience rather than from decorative effects?

## Tier matrix

| Signal | Minimum | Standard | Deep |
| --- | --- | --- | --- |
| Existing semantics and state model preserved | Required | Optional | Optional |
| New screen, navigation, state, or interaction | Forbidden | Trigger | Included |
| Payment, health, privacy, permission, destructive action, AI agency | Forbidden | Escalate | Trigger |
| Alternatives | Only when a real decision exists | Material uncertainty | Multiple distinct directions |
| Prototype | Usually unnecessary | When interaction cannot be judged statically | Required for consequential flow or novel interaction |
| Runtime review | Focused changed surface | Core flow and critical states | Core flow, recovery, accessibility and risk surfaces |

Select the highest triggered tier. A smaller requested artifact does not reduce the risk tier; it only narrows the current output.

Readiness is separate from completeness. If the brief fixes the user outcome,
invariants and required states, produce the bounded direction and mark unknown
copy, content or implementation values as placeholders. Use `conditional` only
when one unknown can reverse the current artifact. Do not turn every unknown
into a planning gate.

For Minimum work, prefer an exact recommendation over a framework: one copy
pattern or hierarchy delta, the affected states, accessibility behavior and a
focused verification list. For Standard and Deep work, make the result buildable
by naming state ownership, standard component or API families, the data each
surface needs and recovery behavior. Risk still determines the tier; it does
not justify withholding constraints that are already supported by the brief.

## Direction Before Conformance

Lead with the selected direction, decisive source-backed evidence, rejected
alternative, recovery behavior, and reversal evidence. Keep only the known,
inferred, unknown, provenance, state, and named-scenario facts that can change
that decision. A missing candidate or oracle does not block this bounded
direction; it blocks only an exact `match` or `deviation` claim. Do not fill a
candidate gap with inherited captures, environment values, or an implied
implementation result.

Prefer the observed product role, then the system component role. If OS,
framework, or API specifics are unavailable, select the semantic role, mark
only the version-specific claim `unknown`, and escalate only if it can reverse
the direction.

## Critical state matrix

Include only applicable states, but make omissions intentional:

- initial, loading and loaded;
- empty, zero-result and first-use;
- recoverable error and terminal error;
- permission unknown, denied, restricted and granted;
- offline, stale, retrying and partial success;
- destructive confirmation, cancellation, undo and recovery;
- long text, localization expansion, Dynamic Type and reduced motion;
- interrupted, backgrounded and resumed;
- AI proposal, uncertainty, review, correction and reversal.

## Alternatives

Generate alternatives only when a decision can change. A serious alternative changes information hierarchy, interaction model, user agency, recovery, product emphasis, or emotional hypothesis. Color swaps and decorative variants do not count.

Record why the selected direction serves the target task better and what evidence would revive a rejected direction.

## Trend restraint

Treat a trend as a candidate mechanism, never a goal. Record the source date, user problem, applicable surfaces, accessibility implications, failure modes and recheck trigger. Reject a trend when it weakens comprehension, agency, performance, accessibility, platform fit or product identity.

For Liquid Glass, prefer standard components and use the material for controls and navigation. Do not make it a decorative content-layer default. For agent-assisted prototypes, use realistic data, long content, empty and error states, then tune key motion moments; agent output is a starting point, not acceptance evidence.

## Post-implementation review

Compare the fresh matching surface with the selected intent only when the exact
candidate, matching surface, and observation authority are bound. Return:

- `match`: behavior or presentation that satisfies the selected intent;
- `deviation`: observable mismatch plus artifact reference;
- `unknown`: a surface not observed or evidence too weak to judge;
- `severity`: `critical`, `major`, `minor`, or `note`, with rationale.

Without those conformance prerequisites, return the source-backed direction,
recovery contract, and reversal evidence without a `match` or `deviation`
claim. Do not decide completion. QA owns matching-surface outcome observation
and the assigning lead owns final execution verification.
