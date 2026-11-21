# Host-catalog checked launch (explicit local opt-in)

The legacy canonical `models_cache.json` path and explicit timestamp reprepare
remain unchanged. The opt-in source now feeds the existing record checker, price
selector, profile/pin checks and checked launcher. See the
[first-task procedure](getting-started.md#first-worker-task-opt-in-local-catalog)
for the short user request and stop rules. Source availability and candidate live
observations do not establish publication or installed activation; check the
release's installed identity separately. The reviewed local builds are Orca
1.4.245, 1.4.261, 1.4.263 and 1.4.268.

Preparation is collector → semantic helper → real record/decision →
`record_check.py routing-check` → checked launcher. The helpers do not create
Run/session authority, resource evidence, profile/price selection or auth/billing
approval. Missing authoritative inputs block launch; no fabricated ready-to-run
command or fixture can supply them.

## Nonlaunching preparation bundle

After the manual collector/semantic preparation below, the optional convenience
CLI consumes your **existing real record and decision**, exact UTF-8 spec file
(including its newlines), and existing exact host worktree selector:

```sh
python3.13 -B skills/company-orchestration/scripts/routing_prepare.py prepare \
  --record "$PRIVATE_RECORD" --decision "$PRIVATE_DECISION" \
  --spec-file "$EXACT_SPEC_FILE" --worktree "$EXACT_HOST_WORKTREE_ID" \
  --output "$PRIVATE_UNUSED_BUNDLE"
python3.13 -B skills/company-orchestration/scripts/routing_prepare.py check \
  "$PRIVATE_UNUSED_BUNDLE"
python3.13 -B skills/company-orchestration/scripts/record_check.py routing-check \
  "$PRIVATE_UNUSED_BUNDLE/decision.json" --record "$PRIVATE_UNUSED_BUNDLE/record.json" --json
```

The parent directory must already exist without symlink components. `prepare`
reserves an unused 0700 directory exclusively and writes 0600 files. An existing
file/directory/symlink or another caller denies without overwriting; failed partial
reservations remain for review, never delete/retry them automatically. Exit 0 means
`status: prepared` for supplied inputs, not permission to start. Both commands
always emit `launch_authorized: false`; exit 1 and `missing_fields` mean stop and
resolve that evidence with its actual owner. There is no launch flag or host probe.

The versioned `company-routing-prepare/v1` manifest binds exact original
record/decision/spec snapshots, generated artifacts, approved package source,
Company configuration and supplied evidence/catalog receipt hashes. `patch.json`
contains only evidence `file` path replacements to absolute original locations;
`record.json` and `decision.json` retain every other input field. The bundle also
contains `routing-check.json` (the existing checker result) and
`missing-fields.json`. Config/auth/database contents are not copied. Evidence
references stay **live original paths**, not archived grants: this bundle is not
portable and must retain those original files. `check` is read-only and recomputes
input/artifact/source/configuration hashes and the old prelaunch checker, including
semantic observations and catalog freshness. It does not reuse a cached PASS or
repair a previously denied bundle. Malformed/missing raw inputs may leave only a
partial reserved directory plus the structured stdout denial; no manifest means
incomplete, not prepared. A manifest is a local integrity aid, not an authenticated
signature or a reservation against concurrent host changes.

The bounded convenience path supports only a fresh planned spec with an existing
local host-catalog binding and existing semantic-helper observations. Legacy
byte-only observations stay supported by the manual procedure, not promoted to
semantic preparation by this convenience tool. It neither manufactures authentication, tools, billing,
paid opt-in, user pins, Run/Task/Dispatch or resource authority nor fills missing
semantic observations. Complete those in the existing decision first. Profile
preparation, measurement lifecycle/capture readiness and completion/session
registration remain separate responsibilities. Measurement inputs always stop at
this convenience tool and use their existing lifecycle. Legacy/manual preparation,
other launch modes and the checked launcher remain unchanged. After review, the
ordinary checked launcher still independently revalidates; never use a prepared
manifest to bypass its live checks or reconcile an unknown attempt by a new name.

## Prepare

Use the exact existing worktree selector returned by the local installed host:

```sh
/Applications/Orca.app/Contents/Resources/bin/orca worktree list --json
node skills/company-orchestration/scripts/host_model_catalog.cjs \
  "$PRIVATE_UNUSED_DIRECTORY" "$EXACT_HOST_WORKTREE_ID"
```

The collector writes the full parsed RuntimeClient envelope, strict request params,
receipt times and response SHA hashes. It uses explicit local transport and the
existing auth and source fences. Orca 1.4.245, 1.4.261 and 1.4.263 use status and
one catalog request, with one follow-up if the host reports a listing in progress.
Normal host metadata probing on those builds may prepare its own home/cache.

On 1.4.268 the collector requires the coherent, model-efforts and saved-only
catalog capabilities. It uses one `savedOnly: true` request and leaves listing
to Orca. A live 1.4.268 listing returned progress and stale rows even on the
`waitForListing` follow-up. After Orca finished, the saved-only read returned a
fresh configured catalog for the exact worktree. The Python checker requires
probe origin, `modelsDifferByWorkspace: true` and
`listingNamesConfiguredModel: true` on that build. Its Codex resolver can
otherwise return a broader catalog that omits the verified configured model.
The checker also requires known model efforts, a settled response and a
`fetchedAt` no more than five minutes old.

If Orca has no fresh observation for that worktree, stop preparation or launch.
Let Orca complete an authorized model listing in that workspace before collecting
again into a fresh directory. The saved-only collector starts no listing and has
no fallback or retry on an unknown, stale or partial result.

In the existing real routing decision, set the inventory evidence `source` to
`orca_model_catalog`, its `file` to that directory's `manifest.json`, and pin that
file's SHA-256. Keep the existing `candidate_inventory` and all independent runtime,
authentication, tools, billing, suitability and price evidence. Do not label fixture
observations real. The catalog adds no price, auth, tools or capability claims.

Add `binding.host_catalog`:

```json
{
  "worktree": "id:EXACT-HOST-ID::/exact/existing/path",
  "runtime_id": "EXACT-STATUS-RUNTIME-ID",
  "configuration_sha256": "CURRENT-COMPANY-RESOLVE-HASH",
  "observed_files": [
    {"role": "config", "path": "/exact/relevant/config", "sha256": "PINNED-HASH"},
    {"role": "auth_policy", "path": "/exact/relevant/auth-policy", "sha256": "PINNED-HASH"}
  ]
}
```

These are explicit observations of relevant local files, not a completeness claim
about all host state. Use the hash-only preparation helper for the live profile
database. On 1.4.268 pass `--app-version 1.4.268` and use its semantic pin in the
decision. The earlier reviewed builds keep the helper's original default and
existing digest format. Whole-file pins of the profile database, WAL and SHM are
unsuitable for the semantic workflow.

```sh
uv run --offline --no-python-downloads --no-project --python 3.13 python -B \
  skills/company-orchestration/scripts/semantic_settings.py \
  --database "$HOME/Library/Application Support/Orca/profiles/$EXACT_ACTIVE_PROFILE_ID/profile-state.db" \
  --worktree "$EXACT_HOST_WORKTREE_ID" \
  --app-version 1.4.268
```

Put the returned array in `binding.host_catalog.observed_files`, preserving any
additional known relevant file observations. It contains one explicit
`kind: orca-profile-settings/v1`, `role: config`, canonical absolute DB `path`,
and semantic `sha256`; the worktree/version/profile/namespace are included in the
hash input, not operator-selected filters. It also includes byte/absence pins for
the profile index, canonical `.codex/config.toml` and `auth.json`, runtime-home
config/auth, and hook trust policy. These required external pins cannot be dropped
or relabeled in semantic mode. Raw DB/WAL duplicate pins are rejected, not ignored.
On older reviewed builds, no kind (or `kind: file`) retains the legacy
byte/absence behavior. The 1.4.268 catalog requires the 1.4.268 semantic digest
and all external config/auth observations. Unknown kinds deny. Old decisions
retain their original hashes.

The reader opens that exact active profile DB with `mode=ro`, never `immutable=1`,
and performs schema + settings reads in one read transaction, including committed
WAL. It hashes the **entire settings object**, so key additions/removals, account,
provider, command/args/env and permission changes deny; it does not read credential
rows or export values. UI and unrelated profile domains and settings row
revision/timestamps are not semantic inputs. Settings-internal UI preferences are
conservatively included. The narrow reviewed table has domain/payload TEXT,
domain_version/revision/updated_at INTEGER, content_hash TEXT, with the installed
NOT NULL/PK shape and settings domain version 1. Schema metadata is also pinned;
unknown columns/version, missing domain/DB, malformed/duplicate-key JSON, read
errors/locks and oversize deny. Bounds: settings <=1 MiB, schema <=256 entries and
1 MiB, SQLite value limit 2 MiB, lock timeout 0.2 seconds. Unknown schema must be
reviewed, not repinned to bypass. The same adapter runs during initial checker
validation and again after final catalog refresh. Failures have no fallback.

The 1.4.245 installed-source trace found that catalog and structured worker launch use the
same command/account/args/env dependency family; `app.asar:out/main/index.js`
SHA-256 `392e5de92a381cf35715f72b9d7cee9a7b4d50bc7bdc96ba666b406fa6f9fa9d`
binds those resolvers to `requireStore().getSettings()`. The profile preference
getter returns runtime `state.settings`; the SQLite authority persists the
`profile_state_documents` settings domain. In 1.4.268 the catalog dependency
resolver also reads `requireStore().getSettings()` and resolves the existing
worktree through the local workspace resolver. Its active profile uses the
reviewed settings table and domain version 1. Public `settings.getAgentLaunch` and
`settings.get` exist but are client projections, not assumed complete account/
provider state; this adapter deliberately observes the complete persisted domain.
It is not an atomic lock against pending in-memory or subsequent host changes.

Pin absent external files with JSON null and include every known relevant source;
no credential contents are copied. Hash the actual files, do not use placeholder
values. Company configuration is checked independently. Existing local config/
auth denials must be resolved, not overwritten to pass this path. A historical
WAL byte delta without semantic before/after evidence remains **unknown**; this
fix does not retrospectively label the prior reviewer denial harmless.

The launch command is the existing `routing_launch.py` with the exact same
`--worktree`, prepared decision/record, actual sender/spec and fresh receipt/result
paths. No extra flag or `--for-launch` metadata approval is needed. This narrow
opt-in supports a fresh, non-measurement `--spec` launch in an existing worktree;
new worktrees, remote environments, reuse and retries use their legacy contracts.
The installed Orca CLI is required, and remote/dev environment selectors are denied.

Before starting, the launcher collects a new private `.catalog-refresh` snapshot,
checks the same runtime/worktree/model/effort and all returned metadata (except
freshness-validated `fetchedAt`), rechecks the original pinned response bytes,
observed config/auth policy files, Company configuration and original decision/
record bytes. It retains both preparation and refreshed manifest SHA hashes in the
receipt. Unrelated global cache churn is not consulted by this path.

## Read-only explanation and reconciliation plan

After a denial, timeout or incomplete readback, inspect the **exact original**
result and receipt paths without running the launcher again:

```sh
python3.13 -B skills/company-orchestration/scripts/routing_explain.py explain \
  --result "$ORIGINAL_RESULT" --receipt "$ORIGINAL_RECEIPT"
python3.13 -B skills/company-orchestration/scripts/routing_explain.py reconcile-plan \
  --result "$ORIGINAL_RESULT" --receipt "$ORIGINAL_RECEIPT"
```

Both commands produce the same deterministic `company-routing-explain/v1` JSON.
They read state, receipt, fixed `.catalog-refresh` and `.reprepare` directories,
plus lock-file presence; they do not open a lock for writing or contact the host.
Output contains paths, hashes, presence, local state, the evidence-supported last
observed stage, and a blocked reconciliation plan, not artifact bodies or secrets.
Exit 0 means the bounded diagnostic is readable, **not** that launch is ready.
Malformed state/receipt, hash mismatch, unsafe paths and unreadable artifacts
return exit 1. Missing/partial artifacts remain explicitly absent or partial.
Only one directory level is listed (at most 64 entries, 4 MiB per regular file);
symlinks, special files and oversized files are not followed/read.

A refresh followed by final-check denial can leave `not_started`, no receipt and
an exclusive `.catalog-refresh` directory. This establishes refresh-directory
presence, not successful refresh completion or proof of the exact denial stage.
The old collector and receipt writer remain exclusive: same-name invocation can
fail on this residue. **Do not delete/overwrite/reset it to make a retry pass.**
The diagnostic does not change that launcher behavior or authorize its reuse.

Local `not_started`, absent receipt, matching hashes, pending/unknown/observed
state, and a lock file cannot establish trustworthy host no-start evidence.
`host_no_start` stays `unknown`, and `new_attempt_allowed`,
`same_attempt_retry_allowed` and `launch_authorized` stay false. No authenticated
host no-start importer exists here. The responsible host owner must reconcile
the exact Task/Dispatch and establish authoritative settlement or no-start;
only separately approved fresh preparation at entirely unused paths can then
proceed through the existing live gates. Renaming alone does not reconcile an
unknown attempt. A local observed state is not an independent host certification.
These observations are not an atomic snapshot against concurrent writers.
Preserve every prior result, receipt, refresh/archive and failed prepare bundle,
including when reverting the diagnostic feature.

## Existing safety contract versus new claims

The existing selector enforces all known observed table/model/effort candidates,
price priors or explicit whole-work estimates, task suitability, auth/tools/billing,
user pins, profile capabilities/modalities, configuration and resource declarations.
Those checks are retained, not replaced by catalog presence. Model-list pricing
absence does not remove the existing separate cost table or create a new gate.

The host API has no public `complete` flag; none is invented. Observed eligible
models can be considered without proving the whole provider list complete. Omitted
provider models cannot be advertised as considered. The existing known-candidate
coverage check now consumes the host's observed rows, not an unrelated shared cache.

A workspace catalog request uses the host launch account/config resolver. Worker
start resolves that exact existing workspace and the host's own launch preferences;
both retain normal host auth/config guards. Runtime and local observed changes are
checked, but equal lists do not detect an unreported backend provider change, future
entitlement/quota or remote backend behavior. No prior checker provided such a
universal guarantee. Local metadata preflight is not an atomic lock on host settings;
a change after final checks remains possible just as with legacy preflight. Effective
model/effort readback and unknown-start guards remain operative after invocation.

Standalone `host_model_catalog.py --for-launch` still denies: metadata alone is not
execution authority. This is not a permanent denial of the integrated checked path.

## Verification and maximum-two-start live recipe

Synthetic fixtures must stay separate from actual metadata evidence:

```sh
cd skills/company-orchestration/scripts
TMPDIR="$HOME/.hermes/cache/scratch" PYTHONDONTWRITEBYTECODE=1 \
 uv run --no-project --python 3.13 python -m unittest \
 test_host_model_catalog test_host_catalog_launch.HostCatalogLaunchTests \
 test_route_select test_routing_launch \
 test_inventory_reprepare.InventoryReprepareTests.test_raw_hash_drift_denies_before_fake_host \
 test_inventory_reprepare.InventoryReprepareTests.test_unknown_host_outcome_never_retries -v
```

The commands above are synthetic tests, not model starts. Subsequent candidate
acceptance observed a live writer and separate reviewer; the latter's content
verdict was HOLD, not failed worker execution or installed-release verification.
Keep those historical records immutable. For a newly authorized bounded live
check (at most two launcher invocations, failures included), prepare fresh
exact-workspace metadata and a genuine fully evidenced
routing decision. Run the checked launcher once, counting failures in the budget.
Read the exact result and effective settings. On pending/unknown/timeout or incomplete
readback STOP and reconcile; never retry automatically. Only authoritative settlement
and separately approved fresh preparation permit a second invocation. Preserve both
attempts; never a third. No install, account change, paid API switch or process kill
is part of this recipe.
