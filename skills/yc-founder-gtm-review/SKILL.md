---
name: yc-founder-gtm-review
description: Use when a marketing, GTM, positioning, launch, or founder-strategy agent needs a YC-style review of customer pain, wedge, positioning, distribution experiments, or market assumptions before recommending a plan.
---

# YC Founder GTM Review

Use this as a marketing-planning lens, not as final authority. It helps the
marketing agent pressure-test a product or launch direction before handing
evidence to King Sejong, Uigwe, or another bounded planning surface.

## Core Checks

Run the review against these questions:

1. Who is the specific user, and what recent behavior proves the pain exists?
2. What status quo does the user use today, including manual workarounds?
3. What is the narrowest wedge that can create visible value in one week?
4. What positioning turns the feature into a reason to care or buy?
5. Which distribution channel reaches the user before broad brand work?
6. What fast experiment can falsify the plan without building more product?

## Output Shape

Return a bounded handoff with:

- `known`: direct evidence from the repo, user notes, analytics, interviews, or sourced research
- `inferred`: plausible but unproven GTM assumptions
- `unknown`: claims that need user, market, or runtime evidence
- `wedge`: the narrowest recommended target user, pain, and promise
- `positioning`: one concise positioning draft
- `experiment`: one 1-week channel or message test with success/failure criteria
- `risks`: the strongest reasons this could be wrong
- `next_recommended_surface`: usually `jiphyeonjeon` for option judgment or `uigwe` for planning

## Guardrails

- Do not claim YC, Garry Tan, or gstack endorsement.
- Do not copy external skill text wholesale into outputs.
- Do not approve gates, completion, budgets, launches, or live account actions.
- Separate known, inferred, and unknown claims every time.
- Prefer one sharp experiment over a broad campaign plan when evidence is thin.
