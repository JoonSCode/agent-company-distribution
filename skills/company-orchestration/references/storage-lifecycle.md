# Native storage enrollment and closeout

This is a Company-native CLI, not a global `/storage` interceptor. It uses
[existing lifecycle primitives](../scripts/run_completion.py),
[native storage adapters](../scripts/native_storage.py) and the
[separate current maintenance adapter](../scripts/native_maintenance.py).
Stdlib Python 3.13+, no model/provider call, daemon or automatic sweep.
Source/package/installed/effectively loaded are separate observations.

## New work

Create an empty owned directory strictly below the resolved Company `home/runs`.
Keep the original intake and identity observation outside that Run. Use the
installed lifecycle's `default_home` resolver; never derive a second store from
CODEX_HOME alone. `codex_stop` enrollment refuses producer/callback disagreement.
Do not supply a Task/Dispatch id or a guessed native session.

```
python3 -B scripts/native_operations.py storage enroll --request ENROLLMENT
python3 -B scripts/native_operations.py storage classify --request RESERVATION
# Only now create the exact declared files; close their writers/consumers.
# Checked launches need separate exact terminal Dispatch/consumer readback:
python3 -B scripts/native_operations.py storage settle-launch --request SETTLEMENT
python3 -B scripts/native_operations.py storage classify --request FREEZE
# Freeze accepted record after the final manifest, then explicit plan/apply.
python3 -B scripts/native_operations.py storage plan --request STORAGE_REQUEST
python3 -B scripts/native_operations.py storage apply --plan PLAN --expect-plan-sha256 SHA
python3 -B scripts/native_operations.py storage closeout --request CLOSEOUT
```

Strict `company-native-storage-enrollment/v1` fields:
`schema,sejong_home,run,run_id,owner,record,host,session_id,cwd,consumers,expect_session_binding_sha256,identity_evidence`.
`sejong_home` may be null for the existing resolver; other namespace paths and cwd
are absolute lexical paths. `record` is Run-relative. `host` is `codex_stop` or
`explicit_lead`. Identity evidence is a `{path,sha256}` pin of an original object
with exact `host,session_id,cwd`. It is a supplied observation, not authenticated
caller identity. Existing unrelated files/old manifests cannot be adopted.
Interrupted bootstrap may resume only against the same request and metadata.
Session rebinding retains existing prior-completed and exact-CAS checks.

Strict `company-native-storage-classification/v1` fields:
`schema,enrollment,expect_manifest_sha256,phase,artifacts`. `enrollment` pins the
original enrollment request, phase is `reserve`, `freeze`, or explicit `absent`. Each artifact has
exact `path,class,owner,consumers,reason,origin,regeneration,next_use_or_recheck`.
Class is preserve/recreatable/unknown; consumers are an explicit subset of the
Run consumers. Unknown requires a recheck. Recreatable requires a pinned
regeneration original. Reserve precedes file allocation, never snapshots live
bytes. Freeze requires no remaining artifact consumers and an actual open-path
probe before reusing register/snapshot semantics. Unknown is retained, never
disposable. Preserve/unknown cannot be downgraded. Promotion of recreatable to
preserve retains original provenance and checks already frozen bytes. The
accepted record and manifest cannot self-hash. Acceptance/completion freezes
classification; stale CAS, pending outputs and unsafe paths fail closed.

The checked launcher requires `--enrollment-request PATH
--expect-enrollment-sha256 SHA` before result lock/state or measurement work.
New enrolled work pins the existing Run `.completion.lock` inode and shares its
held descriptor capability across launch/reserve/measurement/freeze/complete/Stop.
No prospective result/ledger lock is allocated; every old result/ledger lock stays
protected, never renamed, removed or exempted. Pending/unknown survives a crash
and blocks replay, including another result name for the same attempt.

It reserves exact result/receipt and known reprepare/catalog/measurement evidence
before allocation, and rechecks before the sole host start. A synchronous start
return is not exit. `company-native-storage-launch-settlement/v1` has exactly
`schema,enrollment,result,expect_result_sha256,orca`: enrollment is the original
pin, result is Run-relative, and orca is the explicit absolute executable. The
readback must identify the same Task/Dispatch/process incarnation, terminal host
status and exact exited worker; unknown/live readback cannot settle or freeze.
The result CAS remains reserved until that observation is durably bound.

`absent` is only for a previously reserved supported optional launch output (or
an unused pre-host receipt with demonstrable not_started). It is not a generic
missing-evidence waiver. Absent paths must remain absent at final acceptance.
Every other reservation must be frozen with original retained bytes. Unmanaged
writers/raw Orca calls are outside this supported producer boundary.

## Read-only result

Strict `company-native-storage-closeout-request/v1` fields:
`schema,enrollment,sejong_home,session_id,cwd,run,run_id,owner,record,trigger`.
Enrollment may be null only for non-authorizing unenrolled observation. Trigger
is null or a pin to exact `mode,host,event,session_id,cwd`; mode automatic/explicit.
The reader also consumes actual completion/hook/rejection receipts. It never
invokes cleanup or writes a new closeout ledger.

Statuses: `not_enrolled`, `unknown` (result not observed), `skipped`, `blocked`,
`removed`. Unproved counts/bytes are null. Valid empty completion is
`skipped/no_disposable`, zero files/bytes; nonempty verified completion counts
only exact removed bindings, verifies current absence and preserved originals.
Newer rejection/reappearance is not discarded. Partial action is owner recovery,
not rollback or a new-id retry. Codex Stop is only wakeup, keeps `{}` stdout, and
cannot approve a goal. Explicit-lead enrollment does not enable an automatic
Hermes/Claude hook; those leads use accepted native plan/apply then closeout.

The ordinary final line must state resolved home, enrolled/not_enrolled, actual
trigger, status/reason, verified file/logical-byte count or unknown, exact receipt
reference and pending owner/recheck. Receipt proves an observed action, not
necessarily a new action by this turn or guaranteed APFS free-space savings.

## Separately authorized current legacy maintenance

`storage maintenance-plan --request REQUEST` is read-only. Strict request schema
`company-native-storage-maintenance-request/v1` fields:
`schema,operation_id,owner,sejong_home,root,targets,preserve,historical_metadata,classification_evidence,consumer_evidence,preservation_evidence`.
Each exact regular-file target has `path,sha256,identity,uid,mode,origin,unnecessary_proof,remaining_consumers`.
Identity is `[dev,inode,size,mtime_ns,ctime_ns]`; remaining consumers must explicitly
be empty. Preserve/historical entries use `path,sha256,identity` and explicit
null/null absence pins. All native metadata except the existing lock must have
historical presence/absence pins. No historical init/register/status rewrite.
No recursive directory, Git worktree/source, unknown owner/value or unresolved
native/tool/host denial is eligible.

`storage maintenance-apply --plan P --expect-plan-sha256 H --authorization A
--review R` requires current owner exact-target authorization and a different
independent assessor, exact final plan/host/operation/candidate, original consent,
valid timezone-aware current intervals and preservation originals. Candidate is
`{revision,dirty_manifest:{path,sha256}}`; its manifest contains exact
`revision,package_sha256` of the current package payload. Authorization fields:
`schema,operation_id,plan_sha256,owner,host,approved_by,approved_at,valid_until,scope,authority_evidence`.
Review fields:
`schema,operation_id,plan_sha256,owner,host,assessor,executor,candidate,verdict,reviewed_at,valid_until,inventory_evidence,preservation_evidence,consent_evidence,prior_denial_resolution`.
Use the distinct authorization/review v1 schemas and `verdict:approved`.
Prior denial resolution is null only when none exists, else pins `denial,resolution`.
Hashes/actor strings cannot authenticate actual independent approval; the parent
reads originals. Consumer evidence requires `quiescent:true,consumers:[]`.
Preservation evidence requires `copies:[{original,copy:{path,sha256}}]`, with each
preserved original recoverable byte-for-byte outside the historical root.

Apply repeats shared source/UID/namespace/pin/open-file/identity/CAS guards and the
same descriptor-relative quarantine/unlink engine, using an external private
current-operation bundle under `home/state/company-storage-maintenance` keyed by
the exact root dev/inode, not operation id or path spelling. APPLY requires the
existing historical lifecycle lock and fails closed if absent; it never creates
that resource in old metadata. The root lock is held before external sink locking.
Both namespaces and lock identities are rewalked before each action/readback.
An exclusively created durable bundle also blocks retry after pre-intent crash.
Durable intent/pending/action receipts prevent a changed operation id
from blindly retrying that root. Old records/manifests/bindings/receipts are never
rewritten. A fixture action is not real old-data cleanup. If no independently
reviewed eligible exact target exists, report BLOCKED/retained and its owner;
never use raw rm, weaken Git protection or repair historical acceptance.
