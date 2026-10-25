# Workspaces, builds, devices and retained evidence

Apply when a task creates or consumes a checkout, build, test device, large
artifact or background process. This is Company operating policy, not a new
scheduler or general deletion permission. The narrowly registered current-Run
[completion callback](completion-retention.md) applies only after exact accepted
success and explicit disposable declarations. Current
host/tool safeguards and the user's preservation requirements remain binding.
Use existing Orca ownership and project tooling. The lead owns coordination and
closure; each delegated owner accounts for its resource use and handoff.

## Allocate for the work

Before an expensive operation, inspect the relevant existing resources, their
owners/live users, source and configuration, and available disk/memory when these
can constrain it. Use bounded deterministic listings and existing receipts, not
a full-disk scan or another AI inventory of the same facts. Missing ownership or
process evidence is uncertainty, not permission to reuse, stop or delete.
Use the project's existing capacity limits; when absent, start with a small
allocation and observe it rather than inventing universal disk/RAM thresholds.
If space or memory pressure makes the next step unsafe or counterproductive,
reduce new concurrency and choose a scoped recovery. Do not kill another owner's
work, erase useful state or duplicate an uncertain attempt to free capacity.

Choose the smallest sufficient arrangement:

| Resource | Reuse or share when | Separate when |
|---|---|---|
| Checkout/worktree | Reading the same frozen candidate, or sequential work on the same branch; disjoint edits only with explicit write ownership and an integration owner | Writers overlap, independent branches must evolve, generated files or setup interfere, or candidate isolation is required |
| Build outputs | Consumers need the same identified candidate and compatible build/test inputs; producer has finished and outputs are stable | Source/configuration/SDK/architecture/signing changes, a clean-build claim is needed, outputs are mutable or provenance is uncertain |
| Simulator/device | Compatible runtime/device and agreed initial app/data state; one operator at a time | Simultaneous stateful tests, clean-state/reproducibility requirements, different OS/device coverage, or preservation of an existing session requires isolation |
| Cache | Supported tool-managed cache semantics and compatible keys; likely reuse exceeds storage burden | Tool does not support concurrent use, key/ownership is uncertain, or measured invalidation requires a scoped replacement |

One worker does not require one new worktree or build directory. A fresh review
context can read the same immutable source/artifact; review independence does not
require recompilation unless the claim under review requires an independent or
clean build. Git worktrees share repository objects; they do not automatically
share dependency installs, Unity Library directories or build products.

For mutable resources record the exact resource key/path or device ID, owner,
consumer order and release/handoff condition in the existing work note and briefs.
Do not create a second authority store. A note is not an OS lock: use supported
tool locks plus owner coordination, and verify occupancy before starting. An
unrelated session using the resource remains a real conflict. If exclusive access
cannot be established, wait or choose safe isolation; never silently take it over.
Shared checkout users must serialize Git/index/branch operations, generators,
dependency installation and other mutations that exceed disjoint source files.

## Build once for compatible consumers

Use cheap static or unit checks first when they answer the question. Build or run
the product for claims that require it. Avoid having every reviewer repeat the
same build, or a broad clean build after unchanged inputs and adequate passing
evidence. New failures, changed inputs or a different claim justify another check.

Bind reuse to source commit plus dirty-file manifest when applicable, dependency
resolution, toolchain/SDK, scheme/target/configuration, architecture/platform,
relevant build flags and signing mode. Keep secrets out of the record. Record
artifact path/hash and producer completion; an old green result cannot verify a
new candidate. A compatible cache is not an accepted product artifact.

For Xcode, use supported build-for-testing/test-without-building when the test
products and matching xctestrun remain valid. Preserve their path relationships;
test execution still needs compatible destinations, test inputs and environment.
Changed test code or build-affecting settings require a new build. Installation
and test results are separately observed. Do not assume a moved product directory
or a build for another architecture can be used unchanged.
Prefer a supported prepared test package (such as xctestproducts) for transfer
when available instead of copying a whole mutable DerivedData tree. Its presence
does not prove compatibility; verify the producing/consuming tool's contract.

One owner produces a candidate; consumers then use its stable outputs. Use a
stable per-project/configuration DerivedData location for sequential compatible
work. Never point concurrent independent xcodebuild writers at one mutable
DerivedData/build-output tree. Share only supported cache mechanisms or completed
compatible products; separate concurrent mutable outputs and result-bundle paths.
For Unity, serialize Editor/import/build/test access to the same project and
Library; do not make Library writable by independent worktrees concurrently.

## Parallelize only for a concrete benefit

Parallel independent research/static checks when worthwhile. Start heavy
build/test work conservatively and account for the host's other work. Increase
concurrency only when independence, isolated mutable outputs/device state,
available capacity and a useful time/coverage benefit are clear. Record the
small bound and reason; measure failures, peak storage and elapsed time when a
comparison matters. CPU count alone is not evidence of memory or disk capacity.
Account for nested parallelism: several agents each enabling compiler jobs or
test workers can exceed a host budget. Budget the combined work, not each worker
in isolation. No fixed universal build count or per-role allocation is implied.

For routine iOS Simulator XCTest, use `-parallel-testing-enabled NO`. With
XcodeBuildMCP test_sim pass `extraArgs: ["-parallel-testing-enabled", "NO"]` or
set and verify that process's session default. Do not assume another session's
default carries over. Reuse the selected named device and record its UDID/runtime.
Selecting a base destination does not prevent XCTest worker clones when parallel
testing is enabled. Enable parallel testing only for a task that needs it, with
`-maximum-parallel-testing-workers 2` as the upper bound under the user's current
guardrail. Inspect XCTestDevices after Xcode/XCTest exit. Independent tests also
need isolated accounts, app data, ports and external side effects where relevant.
XCTest worker controls do not by themselves serialize Swift Testing's in-process
parallelism; use that runner's supported controls when the task requires it.

## Preserve what is needed; release what is finished

At assignment, choose a lifecycle category; revise it from actual evidence:

- **Durable:** source, uncommitted/untracked or unintegrated work, unreleased
  commits, user-pinned resources, active installed/rollback generations, release
  archives and matching symbols needed for delivery or crash diagnosis. Preserve.
  Preserve the content/history; this need not retain every redundant checkout.
- **Evidence:** source/configuration manifests, original receipts, meaningful
  logs/results/captures and failed-candidate diagnostics needed for acceptance,
  reproduction, independent QA, an incident or required retention. Keep the
  smallest sufficient set with its original provenance. A summary does not
  replace a required xcresult, archive, media original or failure trace.
- **Reusable:** a named device, warm compatible build/dependency cache or product
  with a credible next consumer. Retain with a reason and recheck trigger; being
  regenerable alone does not make deletion efficient.
- **Temporary:** task-owned scratch, superseded duplicate outputs and completed
  worker resources with no remaining consumer. Release or remove through the
  supported scoped path after settlement and checks below.

Age and size prioritize inspection; neither proves disposability. A clean
worktree may contain unmerged commits, ignored files or valuable local state.
Before removing one, verify owner/task completion, dirty/untracked/ignored files,
commit reachability and required remote/backup retention, active terminals/open
paths and linked evidence. Move required evidence to its durable location before
removal and verify the references. Keep branch deletion separate. Operate Orca
workspaces through its current CLI; do not bypass a guard with `--force` or raw
recursive deletion. A requested worker release does not delete its worktree.

For cleanup, determine exact owned targets, retention exceptions, supported tool,
age rule and before-size; obtain report/dry-run where provided, then recheck live
users, open files, locks and protection immediately before a permitted removal.
Record the deletion receipt and after-size; distinguish a skip from reclaimed
space. Do not attribute changing filesystem free space entirely to this cleanup.
On uncertainty preserve the target and name its owner/next check. Respect prior
cleanup authorization without re-asking, but do not expand a narrow allowlist to
all old directories. New scope needing approval must have concrete candidates
and preservation evidence ready before asking.

For XcodeBuildMCP use the installed tool's protected purge report/dry-run/delete
contract with exact workspace, classes, age and required confirmation. Its own
lifecycle sweep is workspace-scoped and does not imply DerivedData or simulator
storage was reclaimed; inspect the installed version's actual behavior. Include
DerivedData only when no build uses it. Preserve recent, active, pinned and
unrelated artifacts, including acceptance/debugging evidence. Existing local
retention helpers retain their exact allowlists; do not rewrite them into a
global cleaner.
Protect required evidence and long-lived reusable test packages from automatic
expiry before relying on them. Use a verified supported pin or a durable location
outside the automatic sweep, preserving path relationships and access controls.
A Company note is not a tool-enforced pin; a producer completion marker does not
prove that all consumers finished. Check both tool retention and consumer use.

CoreSimulator and XCTest device data are separate from XcodeBuildMCP purge.
Never remove them while Xcode, xcodebuild, xctest or Simulator is active. Simulator
erase/delete and XCTest clone cleanup require their separately approved scope,
an age threshold and before/after readings. Do not erase a shared simulator merely
to prepare one test, or shut down another owner's device to make cleanup possible.

Close with existing records: what was reused, created, released/removed, retained
(path/ID, owner, reason, next consumer or recheck trigger), and uncertain/skipped.
Settle Orca workers using the [Orca contract](orca-contract.md); do not keep a
terminal alive just to read an archived result. Avoid a new retention ledger or
scheduled sweeper when the work note and existing tool receipts suffice.

## Verification boundary

This policy can be checked with bounded decision cases and source/install checks.
Resource/time savings require comparable real workload measurements; policy
adoption, byte counts and a passing static check alone do not prove them. Use a
small actual workload when the next approved build/test task needs one. Do not
create extra builds, simulator clones or destructive cleanup just to demonstrate
an efficiency policy.

## Technical basis and limits

Reviewed 2026-10-02. These sources describe capabilities, not measured local gains:

- [Apple test build/execution separation](https://developer.apple.com/library/archive/technotes/tn2339/_index.html): archived TN2339; verify current flags and package compatibility at execution.
- [Apple prepared test products](https://developer.apple.com/documentation/xcode-release-notes/xcode-13_3-release-notes) and [parallel test execution](https://developer.apple.com/videos/play/wwdc2020/10221/): product reuse and distributed testing have different state/coverage contracts.
- [Git worktree](https://git-scm.com/docs/git-worktree): common repository data, separate checkout state, remove/prune/lock distinctions; a Git worktree lock is not a build mutex.
- [Apple matching debug symbols](https://developer.apple.com/documentation/xcode/locating-a-missing-debug-symbol-file): preserve the binary's matching dSYM, not an assumed equivalent rebuild.
- [XcodeBuildMCP 2.7.0 release](https://github.com/getsentry/MobileBuildMCP/releases/tag/v2.7.0): prepared test and protected purge interfaces. The locally inspected 2.7.0 sweep excludes DerivedData/devices; purge does not establish global process/open-file safety or arbitrary consumer/pin protection. Reinspect an updated installed version before relying on its exact behavior. The upstream project has renamed; this reference does not change the installed package.

Exclusive DerivedData writers and retention categories are Company's coordination
choices derived from mutable state and evidence risk, not claims of an Apple-wide
resource locking service. No cache setting, cleaner or parallel mode is enabled
by adding this policy.
