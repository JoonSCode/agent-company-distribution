# Release Readiness

- Reference ID: `task-pack:qa-release:release-readiness`
- Role: `qa-release`
- Required kernel: `role-kernel:qa-release`
- Task type: `release-readiness`
- Decision: what candidate-bound build, signing, review, deployment, recovery,
  and residual-risk evidence supports the authorized go/no-go decision?

Assemble release evidence without performing or approving release; each release
state remains separate and external actions stay authorized-owner only.

## Decision-First Verification Ledgers

Use separate plan, observation, evidence-fact, risk/boundary, blocker, and
decision ledgers. Facts retain IDs, provenance, and claim scope independently
from criterion status; every named dimension gets a closure row, never a
catch-all or an invented criterion.

## Exact Triggers And Non-Triggers

Use this pack when:

- an exact candidate needs pre-submission, pre-release, or rollout-readiness
  evidence;
- version, build, commit, dirty source state, archive, signing, entitlements,
  configuration, or uploaded-build lineage must be reconciled;
- App Store Connect or another distribution surface must be inspected without
  mutating it;
- submission, review, approval, release, rollout, or storefront observations
  risk being collapsed into one status;
- rollback, halt, mitigation, recovery, ownership, and go/no-go evidence must be
  tested or reported.

Do not use it when:

- acceptance criteria or acceptable release risk are undefined; return to
  the authorized decision owner or Planning;
- the task is only test-layer selection; use
  `task-pack:qa-release:test-strategy`;
- the task is only Simulator, device, permission, StoreKit, or deep-link
  behavior; use `task-pack:qa-release:ios-matching-surfaces`;
- the request assumes that a local archive, upload command, processing receipt,
  review status, approval, or visible listing proves another release state;
- submission, agreement acceptance, build selection, metadata mutation,
  phased-release change, rollout, or live deployment lacks explicit approval.

## Required Inputs And Verification Evidence

Require:

1. approved release objective, acceptance criteria, non-goals, severity limits,
   launch window, intended distribution channel and authorized decision owners;
2. exact candidate identity: `app_id`, `version`, `build`, full `git_commit`,
   `source_state_sha256` over tracked, untracked, and deleted state, and
   `configuration`;
3. source-to-artifact lineage: dependency lock state, toolchain, scheme, target,
   archive identity, bundle IDs, embedded versions, hashes, build logs, and
   reproducible export or package refs as applicable;
4. signing and capability evidence: intended team and distribution class,
   signature verification, provisioning or certificate identity and validity,
   entitlements, capabilities, embedded profiles, and environment endpoints;
5. criterion-bound automated, integration, Simulator, device, permission,
   StoreKit, privacy, accessibility, security, migration, backup, restore, and
   manual observations proportional to the change;
6. exact external records for app, version, build, processing, selection,
   submission, review, approval, agreement, rollout, and storefront state, each
   with observed timestamp and candidate binding;
7. rollback or mitigation contract: trigger, decision owner, action, access,
   tested environment, data compatibility, recovery objective, observability,
   communication, cleanup, and proof of rehearsal;
8. known incidents, flaky or waived checks, unresolved findings, current-source
   gaps, monitoring expectations, stop condition, and independent verifier.

Never copy secrets, raw profiles, personal account data, tokens, connector
payloads, receipts, or private paths into evidence.

## Release-State Ledger

Record these lanes independently:

1. **Source state:** exact commit, source-state digest, configuration, tag, and
   attestation where applicable.
2. **Archive/package:** artifact identity, embedded metadata and hashes.
3. **Signing/export:** signature, entitlements, profiles, team, and distribution
   class observed for that artifact.
4. **Distribution identity:** selected and installed artifact identity for each
   named channel, its `qa_decision`, and `evidence_fact_ids`.
5. **External progression:** upload, processing, selection, submission, review,
   approval, release, rollout, and live availability as independently observed
   states.

A later lane cannot be inferred from an earlier one. An older build's review or
live state is not evidence for the candidate. An uploaded candidate is not
selected; selected is not submitted; submitted is not approved; approved is not
released; a listing is not proof of the installed binary.

Every release blocker is one compact record: lane; owner status or unassigned;
candidate-bound next check; binary artifact; cleanup/stop; and status. A
missing field is an explicit unknown, not empty boilerplate.

## Evidence Priority

Rank evidence from strongest to weakest:

1. exact candidate and artifact identity reconciled across source, archive,
   signature, external record, and observed distribution surface;
2. fresh matching-surface acceptance, safety, migration, restore, and rollback
   observations on that candidate;
3. direct read-only records from signing tools and the named distribution,
   review, rollout, or storefront surface;
4. deterministic build, test, package, and policy-validation results with exact
   commands and environments;
5. monitoring rehearsal, operational checklist, owner confirmation, and
   documented recovery evidence;
6. upload logs, prior-candidate review state, screenshots without identity,
   assumed signing defaults, worker receipts, plans, and verbal assurances.

## Current Source Set Recheck Conditions

Refresh stale, conflicting, or inapplicable platform, provider, legal, or
Apple guidance before it sets a release requirement; it never proves candidate state.

## Step-By-Step Method

1. **Bind authority and release target.** Record objective, channel, intended
   version/build, configuration, window, owners, approved mutations, non-goals,
   cleanup, and stop conditions.
2. **Freeze candidate identity.** Calculate and record the complete source-state
   identity before evidence collection. Reject results from another commit,
   dirty worktree, build number, configuration, flag set, or artifact.
3. **Trace source to artifact.** Record toolchain and dependency lock state,
   build command, archive/package ref and hash, embedded app/version/build,
   bundle IDs, environment endpoints, and configuration. Explain any
   non-reproducible input.
4. **Inspect signing and capabilities.** Verify the artifact's actual signature,
   team, distribution class, profiles, entitlements, capabilities, and validity
   for the intended channel. Do not infer them from project settings alone.
5. **Assemble acceptance evidence.** Map every criterion to its proportional
   automated or matching surface. Preserve each `passed`, `failed`, `blocked`,
   and `unverified` result and its candidate binding.
6. **Review release-specific risks.** Check migrations, compatibility, data
   integrity, backup/restore, privacy, security, account and purchase behavior,
   accessibility, performance, interruption, observability, and support
   readiness only where material to the approved candidate.
7. **Inspect external state read-only.** Observe the exact app/version/build and
   separately record upload, processing, selection, submission, review,
   approval, agreement, rollout, and storefront lanes. Stop before any
   unapproved external mutation.
8. **Reject mixed lineage.** Quarantine screenshots, review states, receipts, or
   runtime observations tied to a different build, candidate digest, account,
   channel, configuration, or timestamp.
9. **Validate rollback and mitigation.** Define failure triggers, owner and
   access, reversible action, feature or data compatibility, monitoring,
   recovery, communication, and a bounded rehearsal. If the current platform's
   reversal semantics matter, refresh the Current Source Set.
10. **Evaluate go/no-go evidence.** QA may recommend the exact candidate only
    when named criteria have matching evidence and remaining risks are explicitly
    within the approved decision contract. QA rejects readiness for a failure,
    blocked critical surface, missing evidence, mixed candidate, invalid
    signing, or unrehearsed required recovery. Neither result authorizes release.
11. **Report partial success.** Keep local build, signing, or uploaded-state
    passes visible even when review, device, rollback, or live state blocks.
12. **Handoff for final verification.** Provide the release-state ledger,
    evidence refs, cleanup, risks, recommendation, explicit forbidden claims,
    and `next_recommended_surface: company-lead`.

## Options And Tradeoffs

Rebuild changes artifact identity; reuse preserves it only with complete lineage.
Staged rollout, mitigation, halt, or replacement require current semantics,
authorized ownership, observability, and recovery proof.

## Common Failure Patterns

- using a local build or archive to claim upload, selection, review, approval,
  release, rollout, or live availability;
- using transport or processing success to claim submission or review;
- applying an older build's selected, reviewed, approved, or live state to the
  current candidate;
- trusting project settings instead of inspecting the signed artifact;
- omitting dirty or untracked source from candidate identity;
- treating a visible product page as proof that the intended binary is live;
- calling a rollback document, untested flag, backup existence, or owner name a
  rehearsed recovery path;
- hiding failed, blocked, waived, stale, flaky, or unverified criteria behind a
  pass percentage;
- accepting agreements, selecting or submitting a build, changing metadata,
  releasing, halting rollout, or mutating accounts without approval;
- claiming App Store acceptance, business success, final verification, or
  deployment authority from QA evidence.

## Output Contract

Return:

- objective, channel, authority, owners, non-goals, exact candidate and complete
  source-to-artifact lineage;
- build, archive, signing, entitlement, capability, configuration, and
  dependency evidence with exact results and limitations;
- criterion status and matching-surface evidence, preserving all passed, failed,
  blocked, and unverified results;
- separate source, local, archive, signing, upload, processing, selection,
  submission, review, approval, release, rollout, and live-state records;
- rollback and mitigation triggers, owners, rehearsal evidence, unresolved
  recovery gaps, monitoring and communication expectations;
- QA readiness recommendation or rejection, residual risks, cleanup, smallest
  next check, `next_recommended_surface`, final verification owner, and
  `forbidden_claims`.

When a role handoff is requested, preserve every required field of
`agent_company_bounded_handoff.v0.1` and the complete report structure from
`qa-release-contract.json`.

## Stop Or Escalate

Stop and escalate when candidate or artifact lineage cannot be proven, signing
or entitlements mismatch the intended channel, a critical matching surface is
failed or unavailable, external records bind another build, required rollback
cannot be rehearsed, current platform facts are stale, or continuation requires
submission, agreement acceptance, metadata/account mutation, release, rollout,
withdrawal, or live deployment without approval. Route acceptable-risk and
external-action decisions to the authorized owner through the authorized decision owner or the assigning Company lead;
route final verification to the assigning lead. Do not convert a blocker into
approval pressure.

## Compression Examples

**Good:** "Candidate `com.example.app` 3.2.0 (204), commit `7bc1…`, digest
`6de4…`, Release-Production produced archive hash `a18f…`; embedded version,
bundle ID, distribution signature, team, and entitlements match the intended
channel. Candidate-bound automated and Simulator checks pass, while the required
real-device restore remains blocked. App Store Connect shows build 204 processed
but not selected; version 3.2.0 is in review with build 203, and the live
storefront remains 3.1.0 (198). The production rollback flag has not been
rehearsed. Preserve the local and signing passes, reject readiness for build 204,
and send the device, selection, and rollback gaps to the assigning lead. No
submission or release action was taken."

**Bad:** "Build 204 archived and uploaded successfully, and version 3.2.0 is in
review, so the candidate is approved and ready for production."
