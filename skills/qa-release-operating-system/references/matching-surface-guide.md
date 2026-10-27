# Matching-surface guide

Use the least expensive surface that can directly falsify the acceptance claim.
Record exact candidate identity for every observation. Candidate identity
includes a source_state_sha256 digest over tracked changes, untracked content,
and deletions, so observations cannot be reused for different dirty worktrees
at the same commit.

| Claim | Required surface | Non-substitutes |
|---|---|---|
| Pure logic or build integrity | Focused automated test or build | A worker completion summary |
| Supported UI flow | Simulator plus manual observation when appearance matters | Build success alone |
| SE3 or physical-device behavior | Named real device | Simulator or preview |
| Permission/privacy transition | Actual denied, limited, granted, revoked, and relaunch states named by the criterion | Static permission strings |
| Purchase or entitlement | StoreKit path and named storefront/account state | Unit test alone |
| App/version/build readiness state | Exact App Store Connect record | Local archive or upload command alone |
| Visual/accessibility behavior | Manual matching-surface observation, optionally routed to a specialist | Screenshot creation alone |

Use separate criteria and observation ledgers. A terminal pass or fail requires
all of: direct provenance, full coverage, exact matching candidate identity,
available required surface, exact qualifier, and the matching terminal result.
Reported observations, partial coverage, or partial/unknown candidate binding
remain supporting evidence. Missing evidence is `unverified`; an unavailable
required surface is `blocked`.

An observation's `result: failed`, a criterion's decision, and coverage are
separate facts. A denied-only failure does not establish that a granted state
failed to survive relaunch. Preserve the partial failure and its references,
leave that criterion `unverified`, and reject readiness when appropriate.
A universal safety claim (for example, no document loss in any named state)
can logically be falsified by one direct counterexample, unlike an unobserved
sequence or an unmet statistical sample. The current v0.2 contract does not
encode independently reviewed counterexample sufficiency, so it does not
automatically promote partial failures to terminal criterion failures.

Normalize artifact, environment, device, and cleanup references once under
`references`, using `exact`, `unresolved`, or `not_applicable`. Exact references
require a non-placeholder SHA-256. Evidence facts retain their own provenance
and claim scope even when a criterion is blocked or readiness is rejected.

For permission lifecycle checks, record every required transition explicitly:
`not_determined`, `denied`, `limited`, `granted`, `revoked`,
`settings_return`, and `relaunch` as applicable. A nearby Simulator or build
result cannot substitute for a required physical-device qualifier. Any open
blocker forces readiness to `reject`.
