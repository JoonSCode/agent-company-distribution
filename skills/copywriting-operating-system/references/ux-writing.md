# UX Writing

Use this reference when copy participates in an interface, flow, state, or
system response.

## Model The Moment

Before writing, record:

- `trigger`: what happened immediately before this copy appears;
- `system_state`: what the product knows, changed, needs, or cannot do;
- `user_goal`: what the person is trying to accomplish;
- `available_actions`: actions the interface actually supports;
- `consequence`: what each action changes;
- `recovery`: how the person can continue, undo, retry, or get help;
- `persistence`: whether input, drafts, or progress are preserved.

If these cannot be stated, the problem is not ready for copy.

## Information Order

For most interface states:

1. essential state or outcome;
2. primary action;
3. material consequence or constraint;
4. recovery or secondary action;
5. optional detail.

People scan interfaces. Put meaning in headings, labels, and controls rather
than assuming body text will be read.

## Controls

- Use verbs that describe the result: `Save`, `Delete photo`, `Turn on
  notifications`, `Try again`.
- Keep the same action named consistently across navigation, buttons, menus,
  alerts, and accessibility labels.
- Avoid `OK`, `Yes`, `No`, `Submit`, `Continue`, and `Next` when a more specific
  result label is available.
- Distinguish closing a view from canceling work and discarding changes.
- Keep destructive labels explicit; do not soften them with a generic positive
  action.

## Titles And Headings

- State the decision, state, or user question.
- Prefer sentence case unless the product language requires otherwise.
- Avoid repeating the exact title in the first body sentence.
- Do not use a clever heading that delays comprehension.

## Helper And Instructional Text

- Place instructions before the action that needs them.
- Explain format or eligibility before input when errors are predictable.
- Give examples only when they disambiguate.
- Do not restate the control label in helper text.
- Use progressive disclosure for optional detail, not for material consequences.

## Errors

An error message should:

1. identify what could not be completed;
2. explain the cause only when known and useful;
3. preserve the user's language and mental model;
4. state whether data or progress is safe;
5. offer a specific next action or recovery;
6. avoid blame and internal codes.

Do not claim a cause that telemetry cannot support. If the cause is unknown,
say what failed and what the person can safely do next.

Prevent errors in the interaction when possible. Copy is not a substitute for
validation, undo, confirmation, saved input, or a better default.

## Empty And Zero States

Distinguish:

- first use;
- no user-created content;
- no results for the current query or filters;
- unavailable or offline content;
- permissions or account state preventing content;
- content removed or expired.

State why the space is empty and offer the next meaningful action. Do not
promote an unrelated feature merely because the screen has room.

## Permissions And Privacy

- Explain the user benefit before the system prompt when context is needed.
- Ask at the moment the capability is used.
- State what data is accessed and what the app does with it when material.
- Do not promise that data never leaves the device unless current architecture
  and behavior prove it.
- Explain denial and settings recovery without punishing the user.
- Avoid coercive language that implies the app cannot work when a reduced mode
  actually exists.

## Confirmations And Destructive Actions

- Use confirmation only when consequences are meaningful and not easily undone.
- Name the object and consequence.
- State what is retained, deleted, charged, shared, or published.
- Prefer undo for low-risk reversible actions.
- Preserve a safe escape and keep the destructive action visually and verbally
  distinct.

## Success And Progress

- Confirm only outcomes the system has completed.
- Distinguish queued, processing, uploaded, sent, published, and verified.
- Do not celebrate routine actions so loudly that the interface becomes noisy.
- For long operations, state what is happening, whether the user can leave, and
  how completion will be signaled.

## Accessibility Checks

- A visible label and assistive-technology name should identify the same action.
- Link text should describe purpose or destination without surrounding context.
- Instructions must not depend only on color, shape, position, gesture, or
  sound.
- Error text must identify the field or item and provide correction guidance
  when known.
- Announced status messages should communicate the state change without moving
  focus unnecessarily.
- Test the copy with large text, screen reader order, truncation, and repeated
  components.

## Copy As Design Evidence

Escalate to Design when:

- the title needs several sentences to explain the current state;
- a control cannot be labeled without ambiguity;
- the same state exposes competing primary actions;
- a warning appears after rather than before commitment;
- recovery is absent;
- the flow depends on the user reading every word;
- copy length is caused by unresolved hierarchy or navigation.
