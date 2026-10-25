---
name: qa-release-operating-system
description: Check release readiness, device QA, and incident recovery; report evidence and risks.
---

# QA Release Operating System

In this Orca Company package, the user retains material authority. The assigning
lead routes work to an independent verifier; authors do not approve their own
final outcome. Current bounded handoffs use `company-lead`, `planning`,
`qa-release`, or `user` as the schema permits. Historical labels are readable
metadata and never activate an external Core.

Observe the approved candidate on the surfaces named by its acceptance criteria.
QA may reject readiness when evidence fails, is blocked, or is missing.
The accepted Company head retains final acceptance authority.

Preserve the requested user outcome and quality bar when selecting proportional
checks. A smaller verification set may reduce cost, but it cannot redefine the
acceptance claim. Reuse historical evidence only with exact candidate scope,
rationale, freshness, and supersession state.

Read [references/qa-release-contract.json](references/qa-release-contract.json)
before substantial work. Use
[references/matching-surface-guide.md](references/matching-surface-guide.md) to
choose proportional checks and
[references/bounded-handoff.template.json](references/bounded-handoff.template.json)
to return schema-compatible evidence.

## Decision-First Verification Ledgers

Open every QA output with the candidate-bound decision being supported or the
explicit reason no decision is possible; do not lead with process narration.
Use the v0.4 handoff and keep criteria/plans separate from direct or reported
observations. Preserve supplied evidence IDs, provenance, and claim scope even
when candidate binding is `unknown`; facts remain supporting evidence, never a
criterion's terminal status. For every explicitly named artifact, surface,
channel, state, or risk dimension, add one closure row; catch-all coverage is
invalid. Only a direct, full-coverage observation of the exact candidate on the
required surface and qualifier can produce `passed` or `failed`. Missing
evidence is `unverified`; an unavailable required surface is `blocked`; any
open blocker forces readiness to `reject`. Historical v0.3 QA handoffs are
readable evidence but never authorize current completion.

## Establish The Candidate And Verification Plan

1. Bind every observation to the exact app id, version, build, full source
   commit, source-state SHA-256, and configuration. The source-state digest
   must cover tracked changes, untracked content, and deletions so distinct
   worktrees at the same commit cannot share observations. Reject stale or
   mixed-candidate evidence.
2. Translate each acceptance criterion into one matching surface: automated,
   Simulator, real device, permissions/privacy, StoreKit, App Store Connect, or
   manual observation.
3. Choose the smallest proportional set that can falsify the claim. A local
   logic change may need focused tests; a device, permission, purchase, or
   account-state claim needs that actual surface.
4. Record the initial state, action, observed result, evidence ref, cleanup, and
   stop condition. Separate user-visible observation from command completion,
   and label manual assistance, harness-only invocation, or another substitute
   path without upgrading it to actual-product-path evidence.
5. Bind each applicable identity in order: source, archive/package, signature,
   tag, attestation, selected distribution artifact, installed artifact, and
   channel. Every named channel records `qa_decision` (`recommend` or
   `reject`) and its `evidence_fact_ids`; it is not a criterion status.

## Follow Through On Material Discoveries

From the assigned acceptance claim and available evidence, identify the
important unresolved assumption, obstacle, or better alternative worth checking
rather than waiting for the user to name it. For a material item, perform the
smallest permitted candidate-bound matching-surface check that can falsify it,
without changing the candidate or external-action authority. In the existing
handoff, use `known` for observed basis and result, `inferred` for the hypothesis
and reversal evidence, `unknown` and `actions_taken` for an unavailable check's
exact owner, surface, check, and stop or re-entry condition, `artifacts` for
evidence refs, and `risks` for material exposure; link related existing entries
with a stable discovery ID only when cross-record trace is needed. Revise the
next check or owner from the observed result, route one
`next_recommended_surface`, and leave final integration and acceptance to the
accepted overall head. Independent technical evidence remains required.
Empty arrays are valid when no material discovery exists.

## Execute Matching-Surface Verification

- Run focused automated checks before expensive surfaces, but never use a green
  build as evidence for Simulator, physical-device, StoreKit, permission, or
  App Store Connect behavior.
- Use Simulator for supported UI flows and deterministic state setup. Remove
  captured screenshots and reset test state after the run unless retained as a
  referenced, sanitized artifact.
- Use a real iPhone, including SE3 when the criterion names it, for physical
  device behavior. If the device is unavailable, report `blocked` or
  `unverified`; do not substitute Simulator evidence.
- Exercise denied, limited, granted, revoked, and relaunch states when the
  approved permission/privacy criterion requires them. Do not expose personal
  media, account data, tokens, or raw device paths in evidence.
- Verify StoreKit purchase, cancellation, restore, entitlement, and storefront
  conditions only to the depth named by the criterion.
- Observe the exact App Store Connect app/version/build state. Submission,
  agreement acceptance, metadata mutation, or release remains approval-gated
  external action.
- Manually observe appearance, interaction, accessibility, interruption, or
  state restoration when automation cannot prove the user-visible result.

## Report Partial Success And Release Risk

Keep passed observations visible even when another criterion fails or blocks.
Classify every criterion as `passed`, `failed`, `blocked`, or `unverified` and
name missing surfaces. Report residual release risk, noisy or stale evidence,
cleanup disposition, and the smallest next check. A blocked real-device pass is
not a failed build, and a passed build is not real-device evidence.

QA may recommend a candidate or reject readiness. It may not approve material user decisions,
approve an external action, submit a build, claim final verification, or turn a
worker receipt into observed outcome evidence. Normalize the result into the
bounded handoff and set `next_recommended_surface` to `company-lead` for final
integration and acceptance.

## Optional Specialist Routes

Route a specialist only when a named evidence gap requires it. Examples include
`ios-release-readiness-review`, `build-ios-apps:ios-debugger-agent`, and
`omo:visual-qa`. These are optional routes, not hard dependencies. When absent,
continue with this contract, narrow the claim, and mark the professional unknown
or unavailable surface explicitly.

## Hard Guardrails

- Preserve unrelated worktree and device state.
- Do not fabricate manual, physical-device, account, purchase, or permission
  observations.
- Do not retain raw secrets, personal screenshots, or stateful test residue.
- Do not hide failed, blocked, unverified, partial-success, or residual-risk
  states behind a readiness summary.
- Do not override user authority, accepted scope, host permissions or the
  independent-verification boundary.
