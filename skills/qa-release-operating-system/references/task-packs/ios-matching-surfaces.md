# iOS Matching Surfaces

- Reference ID: `task-pack:qa-release:ios-matching-surfaces`
- Role: `qa-release`
- Required kernel: `role-kernel:qa-release`
- Task type: `ios-matching-surfaces`
- Decision: which iOS runtime and external surfaces directly observe each
  acceptance claim for the exact candidate, and which substitutions are invalid?

This pack binds iOS evidence to the surface that can actually exhibit the named
behavior. Simulator, physical device, permissions, StoreKit, deep-link source,
and external account or service observations are separate evidence lanes. A
pass in one lane cannot silently fill another.

Supporting facts retain IDs and claim scope but never set terminal criterion
status; every named device, surface, channel, state, artifact, and risk closes
in its own row.

## Exact Triggers And Non-Triggers

Use this pack when:

- acceptance names iOS UI, lifecycle, accessibility, interruption, restoration,
  hardware, performance, or a specific device;
- permission or privacy behavior must be observed across denied, limited,
  granted, revoked, Settings, or relaunch states;
- purchase, cancellation, restore, entitlement, storefront, or account state
  requires StoreKit observation;
- a custom URL, universal link, notification, widget, share extension, browser,
  email, authentication callback, or other external entry must reach the app;
- Simulator evidence may be useful but physical-device or external-surface
  equivalence is in question.

Do not use it when:

- the claim is pure logic with no iOS runtime dependency; use
  `task-pack:qa-release:test-strategy`;
- the main decision is signing, archive lineage, App Store Connect review, or
  distribution readiness; use `task-pack:qa-release:release-readiness`;
- only a screenshot, preview, build log, worker receipt, or mocked callback is
  available for a claim that names interaction or an external surface;
- the requested observation requires a personal account, purchase, device
  mutation, or production action without approved safe access;
- product performance, store conversion, or user success is being inferred
  from functional QA.

## Required Inputs And Verification Evidence

Require:

1. criterion IDs with observable states, device or form-factor requirements,
   orientation, appearance, locale, accessibility settings, lifecycle entry,
   and pass/fail oracle;
2. exact candidate identity: `app_id`, `version`, `build`, full `git_commit`,
   `source_state_sha256`, and `configuration`, plus bundle identifiers, scheme,
   target, feature flags, backend environment, and content fixture;
3. Xcode, SDK and target OS identity; Simulator model and runtime; physical
   device model and OS when required; installation source and app data state;
4. permission preconditions and transitions, privacy-safe fixtures, Settings
   steps, relaunch behavior, and expected degradation or recovery;
5. StoreKit environment, product and entitlement identifiers, storefront,
   account class, prior transaction state, cancellation and restore oracle;
6. deep-link form, source surface, associated external configuration, cold,
   warm, foreground and invalid-link expectations, fallback and routing oracle;
7. allowed accounts and devices, reversible setup, network and service
   dependencies, artifact redaction, cleanup, stop condition, and verifier.

For each observation use the v0.2 ledgers from `qa-release-contract.json`:
direct or reported provenance, exact/partial/unknown candidate binding, surface
and qualifier, full/partial coverage, availability, terminal result, permission
states, evidence-fact IDs, and normalized reference IDs. Sanitize screenshots
and logs; never retain personal media, tokens, receipts, account payloads, or
raw device paths.

Keep four facts separate for every lane: surface availability, action
execution, observed outcome, and criterion status. Words such as `available`,
`installed`, `opened`, `completed`, `checked`, or `manually observed` prove
only the fact they explicitly describe. They are not synonyms for `passed`.
When evidence says a flow was observed but supplies no expected-versus-actual
outcome, retain the observation and classify the criterion `unverified`; do not
invent safe degradation, recovery, legibility, correctness, or success.

## Matching-Surface And Evidence Boundaries

| Claim | Required observation | Invalid substitute |
|---|---|---|
| Supported UI flow on a named simulated size | Installed exact candidate on that Simulator runtime; manual observation when appearance matters | Build, preview, or snapshot generation |
| Hardware or named physical-device behavior | Interaction on the named real device | Simulator, generic device, or availability check |
| Permission/privacy transition | Actual named state transitions and relaunch or Settings path | Usage-description strings or mocked authorization |
| Purchase, cancellation, restore, entitlement | Named StoreKit environment, account/storefront state, and transaction path | Unit test, product metadata, or another environment |
| Custom URL or universal link | Exact source, link form, lifecycle state, routing result, and fallback | Direct internal router call |
| Notification, extension, browser, email, or auth callback | Entry from that external surface with sanitized resulting state | Simulator command that bypasses the source |
| App Store Connect app/version/build state | Exact external record | Local archive, upload command, or transport success |

Simulator can prove supported deterministic UI and lifecycle behavior. It does
not prove radio, camera, thermal, memory, biometric, storefront, notification
delivery, or named-device behavior unless the criterion and current source set
explicitly establish a valid simulated equivalent. For `real_device`, passed or
failed behavior requires `device_interaction`; `availability_check` supports
only `blocked` or `unverified`.

Keep StoreKit configuration, sandbox, TestFlight, and production observations
distinct. Keep direct router invocation, simulator URL opening, browser tap,
email tap, notification tap, and authentication-provider callback distinct.
Each proves only the path actually exercised.

## Evidence Priority

Rank evidence from strongest to weakest:

1. direct, repeatable observation of the exact candidate on the exact named
   device, OS, lifecycle, account, storefront, permission, or external source;
2. matching Simulator observation for behavior the criterion permits Simulator
   to represent, with deterministic initial state and cleanup;
3. transaction, Settings, external-service, and app-state records correlated by
   sanitized timestamps or test identifiers;
4. focused automated assertions and logs that explain the observed runtime path;
5. build, install, entitlement inspection, static configuration, and official
   current contracts, limited to their direct assertions;
6. previews, internal router calls, mocks, prior builds, screenshots without
   interaction context, worker summaries, and undocumented assumptions.

## Current Source Set Recheck Conditions

Refresh stale, conflicting, or inapplicable Apple/provider guidance before it
sets setup or the oracle; it never proves candidate behavior.

## Step-By-Step Method

1. **Bind candidate and criterion.** Record complete candidate, build/install
   source, configuration, fixture, lifecycle state, and exact named surface.
2. **Create the surface matrix.** Map every criterion to automated, Simulator,
   real device, permissions/privacy, StoreKit, external source, or manual
   observation. Name non-substitutes before execution.
3. **Check availability safely.** Confirm runtimes, named devices, test accounts,
   storefronts, external services, and reversible fixtures. Availability alone
   is never behavioral proof.
4. **Capture initial state.** Record install and data state, login class, network,
   locale, appearance, accessibility settings, permission state, transaction
   history, link source, and cold/warm/foreground state as material.
5. **Run focused automated checks.** Use them to catch logic and build failures
   before expensive surfaces, while retaining their narrower evidence boundary.
6. **Exercise Simulator claims.** Install the exact candidate, perform the user
   path, observe visible and stored state, interruptions and relaunch where
   required, and capture only sanitized artifacts.
7. **Exercise physical-device claims.** Use the named model and OS. Record actual
   `device_interaction`; if unavailable, classify the criterion `blocked` or
   `unverified` rather than substituting Simulator.
8. **Traverse permission states.** Establish and observe every state named by the
   criterion, including denial, limited access, grant, revocation, Settings,
   and relaunch only when required. Verify both capability and degraded UX.
9. **Traverse StoreKit states.** Bind product, environment, account/storefront,
   prior entitlement, and expected result. Observe only the purchase,
   cancellation, restore, renewal, or entitlement paths in scope; record
   incomplete or unavailable paths separately.
10. **Exercise deep and external entry.** Test each required link form from its
    named source in cold, warm, foreground, invalid, expired, or unauthorized
    states as applicable. Observe routing, fallback, state restoration, and
    duplicate handling.
11. **Correlate without overreaching.** Connect app-visible state to sanitized
    runtime, transaction, Settings, or external evidence. Do not infer an
    account or delivery event from the app's optimistic UI alone.
12. **Clean and classify.** Reset permissions, transactions or fixtures when
    safely possible, remove or sanitize screenshots, preserve unrelated device
    state, and classify every criterion. Require an explicit observed outcome
    against the criterion oracle before using `passed` or `failed`; an
    availability or activity record without its outcome remains `unverified`.
13. **Report partial success.** Keep passes even when another device or account
    lane blocks. Name residual risk and the smallest missing matching-surface
    check, then hand off to the assigning lead.

## Options And Tradeoffs

Simulator and local StoreKit are reproducible but not physical, account,
storefront, or provider proof; real devices and approved test accounts add
fidelity at setup, privacy, and cleanup cost. Direct injection bypasses its
named source; manual observation records only what was seen.

## Common Failure Patterns

- calling a green build, install, preview, or screenshot an iOS flow pass;
- treating Simulator as evidence for a named iPhone, camera, biometric,
  notification delivery, thermal, memory, or other physical criterion;
- reporting a real-device pass after only checking that the device exists;
- testing only the granted permission state and skipping denial, limitation,
  revocation, Settings, degradation, or relaunch named by the criterion;
- conflating StoreKit configuration, sandbox, TestFlight, and production;
- invoking an internal router or `openurl` command and claiming a browser,
  email, notification, or provider callback passed;
- using optimistic app UI as proof of purchase, entitlement, account, or
  external delivery state;
- combining evidence across builds, devices, OS versions, accounts, storefronts,
  fixtures, or configurations;
- exposing personal screenshots, media, receipts, tokens, or raw paths, or
  leaving device, Simulator, permission, and purchase state dirty;
- claiming App Store readiness, product success, or final verification from
  bounded iOS observations.

## Output Contract

Return the exact candidate, distinct surface lanes, criterion statuses,
closure rows, sanitized cleanup, residual risk, smallest next check,
`next_recommended_surface: company-lead`, and `forbidden_claims`.

## Stop Or Escalate

Stop and escalate when the exact candidate or install source is unknown, a named
device/account/storefront/external source is unavailable, observation would use
personal data or unauthorized purchase/account mutation, cleanup cannot be
guaranteed, an official current-source gap changes setup or expected behavior,
or continuation would submit, release, accept an agreement, or modify production
state. Record unavailable surfaces as `blocked` or `unverified`; do not invent a
manual, purchase, account, permission, or device observation. Route final
verification to the assigning lead.

## Compression Examples

**Good:** "Build 81 of candidate digest `9f2c…` passes the seeded Simulator
navigation path after denied and granted photo access, but limited access and
post-Settings relaunch were not observed. Direct URL injection reaches the
board route; this does not prove the required Safari universal-link source.
Local StoreKit configuration proves purchase and restore only in that
configuration, not the required sandbox storefront. The named SE3 is
unavailable, so its camera criterion is blocked rather than replaced by the
Simulator. Preserve the two narrow passes, sanitize screenshots, reset the
Simulator, and send the three matching-surface gaps to the assigning lead."

**Bad:** "The Simulator link and StoreKit test worked and the app builds, so
permissions, purchases, deep links, and SE3 behavior are verified."
