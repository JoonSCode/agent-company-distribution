# Surface Playbooks

Select only the playbook for the requested surface. Platform limits and
policies must be refreshed when their recheck trigger fires.

## Onboarding

Purpose:

- establish the product's value and mental model;
- help the person reach first value;
- request decisions only when needed.

Include:

- what the product helps with now;
- the smallest action that demonstrates value;
- progress only when it orients rather than pressures;
- skip or defer when the product supports it.

Avoid:

- a feature tour detached from the user's goal;
- asking for ratings, notifications, tracking, accounts, or payment before
  context;
- claims that cannot be demonstrated in the next experience;
- long setup disguised as education.

## Permissions

Before the system prompt, explain:

- the user benefit;
- why access is needed now;
- the scope of access when material;
- reduced-mode or later options when available.

After denial, explain what is unavailable and how to change the decision.
Mirror the actual platform prompt and current product behavior.

## Empty, Zero, And No-Result States

Classify the state first:

- first use;
- no created content;
- no search results;
- filters exclude results;
- offline or unavailable;
- access or account state prevents content;
- content was removed.

Then give one useful next action. Do not use a generic `Nothing here yet` when
the product knows why.

## Errors And Recovery

Structure:

1. what could not be completed;
2. what remains safe or saved;
3. what the person can do next;
4. optional diagnostic or help detail.

Use internal error codes only as secondary support information. Avoid humor in
repeated, costly, privacy, payment, destructive, or distressing failures.

## Search And Filters

- Keep the search field hint about searchable content, not an example that looks
  like entered data.
- Distinguish no matches from an empty collection or network failure.
- Preserve the query and filters after failure or navigation.
- Suggest a correction only when the system can support it.
- Name filter changes and clear actions consistently.

## Confirmations, Undo, And Destructive Actions

- Prefer undo for low-risk, reversible changes.
- For irreversible or high-impact actions, name the object, consequence, and
  retention behavior.
- Keep safe and destructive actions semantically distinct.
- Do not use `Are you sure?` as the only information.
- After completion, confirm the actual final state, not merely the tap.

## Paywalls And Subscriptions

Required:

- supported value and relevant capability;
- what is included now;
- price, billing period, trial, renewal, and eligibility as required;
- primary action and commitment level;
- restore and cancellation information where the platform or decision requires
  it;
- claim-evidence mapping.

Avoid:

- fake discounts, unsupported crossed-out prices, ambiguous trial language,
  hidden renewal, preselected consent, countdowns without a real expiry, or
  framing the free path as failure;
- claiming savings, productivity, health, or emotional outcomes without proof;
- testing paywall copy without downstream purchase quality and refund or
  complaint guardrails.

## App Store Product Page

Keep title, subtitle, promotional text, description, keywords, screenshots, and
preview narrative consistent with the current build.

- Lead with the primary user value and recognizable use case.
- Use screenshots as product evidence, not decorative posters.
- Do not mention unavailable features as current.
- Keep privacy, pricing, subscription, device, locale, and compatibility claims
  current.
- Recheck Apple's product-page, metadata, review, marketing identity, custom
  product page, and product page optimization guidance before submission.
- Treat page conversion as a surface metric, not causal acquisition proof.

## Landing Pages

Suggested hierarchy:

1. recognizable situation and central value;
2. mechanism or demonstration;
3. credible proof;
4. objection and terms;
5. action with next-step expectation.

Keep source-to-page message continuity. Do not repeat the same CTA after every
paragraph without new decision information.

## Ads

- Match copy to the audience, buying situation, channel role, and landing
  experience.
- Keep the message legible without relying on an image caption.
- Avoid engagement bait, disguised UI, unsupported superlatives, and urgency.
- Define the hypothesis and downstream-quality guardrail before variants.
- Recheck platform character, policy, targeting, disclosure, and destination
  requirements before use.

## Email And Lifecycle Messages

Distinguish:

- transactional: clarity, status, terms, and support first;
- onboarding or education: one next useful behavior;
- retention: value reminder based on real relationship and consent;
- promotional: offer, terms, reason, and action;
- incident or recovery: state, impact, mitigation, next update;
- re-engagement: permission, relevance, and easy opt-out.

Subject, sender, preheader, body, CTA, footer, and unsubscribe are one
experience. Do not let the subject promise what the body or product cannot
deliver.

## Notifications

- Use only for timely value or status.
- Put the meaningful event first.
- Avoid exposing sensitive content on a locked screen.
- Make the tap destination match the message.
- Do not use guilt, streak loss, or manufactured urgency as default retention.
- Respect notification permission, preference, frequency, and quiet-time
  constraints.

## Release Notes

- Describe meaningful user-visible changes.
- Use product terminology and supported behavior.
- Separate fixes, improvements, and new capabilities.
- Avoid generic `bug fixes and improvements` when useful specifics are safe.
- Do not imply external availability before the actual release state is known.

## Incident And Recovery Communication

Include:

- observed state and affected capability;
- known impact and explicit unknowns;
- safe workaround when verified;
- mitigation or recovery state;
- next update expectation;
- correction history when prior information changed.

Avoid speculative causes, blame, minimization, promotional language, and
unverified `resolved` claims. Drafting is not publication approval.
