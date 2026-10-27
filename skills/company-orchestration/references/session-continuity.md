# Durable work and replaceable sessions

Keep the accepted goal and role responsibility separate from a model's current
conversation. All roles, including the goal head, can lose detail under context
pressure. A permanent higher head adds the same problem and briefing overhead.
Do not impose a fixed compaction count, age, context percentage or role hierarchy.
Consider a fresh session when important corrections disappear, stale decisions
recur, repeated confusion costs more than a new brief, or the work/independent
review boundary changes. Healthy relevant context remains reusable.

## Record at the event, read at the boundary

After a material user correction, decision, failure or observed result, update a
small work note with its original source. Do not wait until termination or copy a
whole transcript. Preserve the intended experience and done criteria, accepted
scope, corrections, kept/retired decisions and reasons, known/inferred/unknown,
questions, next owner/action, original evidence, exact Task/Dispatch, active side
effects and leases. Empty arrays explicitly mean none reported, not checked none.
Keep large artifacts at their existing owned location with a hash/reference.

The authoritative source for claimed goal/revision/scope/accepted ownership is the
existing supplementary Company record; actual execution authority and lifecycle
remain Orca's. [continuity.py](../scripts/continuity.py) checks a hash-bound local
work note against that record using [record_check.py](../scripts/record_check.py).
Neither tool authenticates actors, verifies understanding, reads the live fleet,
stops a process, grants permission or transfers ownership. They check supplied
claims. Obtain current original Orca receipts before claiming settlement.

Store these operational notes in the owning Run/goal's private directory, outside
the reusable knowledge repository. `--root` is mandatory. Use immutable record
snapshots and small local originals with explicit path/hash refs. Do not overwrite
a pinned record in place or interpret a proposed successor as an accepted owner.
A work note is not a second ownership ledger; changing Company ownership happens
through the existing record and supported host workflow first.

## Compact direction and report

For a paired or cross-domain handoff, use one existing private workload note as
the shared index. Keep the approved goal, exact source revision, design/contracts,
files and single writer, acceptance checks, current decisions with reasons,
open blockers and next owner/action together. Link originals and changed artifacts;
do not relay full transcripts or copy a separate state store. Update it at a
material decision or result. A note cannot grant authority or independent approval.

The direction names the bounded change, target files, constraints, required checks
and when to stop/escalate. The report names the exact artifact/diff, checks and
their results, failure or question, and decision needed (or none). Use existing
Task/work-note/bounded-handoff fields. The successor reads current originals,
accepts the exact scope and next action, and raises mismatches before writing.
For active ownership transfer, the existing live-work restrictions below apply.
The navigator reviews ambiguity, contract changes, meaningful milestones and
repeated failures; settled local edits stay with the executor. Independent QA
receives the candidate and original evidence separately.

Example, inside an already approved slice:

> Direction: On source REV, keep contract C; implement change X in files A/B.
> Executor E is the only writer. Run checks T/U. Stop for a contract mismatch.
> Report: Candidate DIFF at REV+patch; T passed, U failed with original log L.
> Blocker is Q; navigator N decides Q next. E retains the slice until a successor
> accepts. Independent verifier V checks the final candidate after the fix.

REV, C, X, A/B and the named people/checks are illustrative placeholders, not a
claim that an assignment or check occurred. Small exact work may keep the current
owner without pairing when a handoff adds more burden than value.

Apply this same direction/report to bounded provider-native helpers. Keep one
existing work note as the index, not a helper ledger. The direction identifies
the owning Orca Task/Dispatch, helper role/task name, exact source inputs,
read-only or exclusive file scope, required checks and return/stop conditions.
The report preserves the native identifier and original result, artifacts/checks,
unresolved decisions, requested versus observed settings or unknowns, usage coverage
and resource state. The parent records what it integrated or rejected and why.
Keep completed and released distinct. A native identifier is not an Orca
Task/Dispatch ID, and this note creates no automatic bridge or independent approval.

## Tool contract

Use `uv run --no-project --python 3.13 python` for these stdlib tools.

- `write --note note.json --record record.json --expect-record-sha256 HASH
  --actor ACCEPTED_OWNER [--expect-state-sha256 HASH]`: initialize/update a note.
  Updates use compare-and-swap under a shared note lock and preserve prior state.
- Add `--receipt-only` to `write` when the caller already has the note and needs
  only confirmation. The result contains goal/Run/record bindings, revision,
  content hash and `state_ref` (path and SHA-256 of the exact bytes saved under
  the lock). It omits the echoed note, not stored content or validation. Default
  output remains the full state. The path can change after the write: verify its
  hash before reading it and obtain current state on mismatch. This receipt does
  not replace original-source reads, successor readback or independent review;
  no cached authority, deduplication of retries, or new permission is introduced.
- A note has `intent` and `authorized_scope` strings; `corrections`, `decisions`,
  `known`, `inferred`, `unknown`, `questions`, `next_actions` arrays of short strings;
  `sources` as original `{path, sha256}` refs; and `work` for every current record
  Task: `{task, dispatch, side_effects, leases}`. Each effect/lease has
  `{id, status: active|uncertain|settled, evidence}` naming readable evidence in
  the existing record. Keep retained/retired decisions explicit in the text.
  `run: {id, evidence}` binds the exact Orca Run id to readable host evidence in
  that same record. A goal id is not silently substituted for a Run id.
- `prepare --expect-state-sha256 HASH --successor OWNER --session SESSION
  --reason REASON`: produce a proposed handoff with exact state/source binding.
  An active task can prepare evidence, but cannot accept it as a settled transfer.
- `accept --handoff handoff.json --expect-handoff-sha256 HASH --record
  successor-record.json --expect-record-sha256 HASH --actor OWNER --session
  SESSION --reads reads.json`: successor explicitly attests reading the note,
  old/current Company record and original sources by listing their path/hash refs.
  The existing record must already accept that owner for the exact goal/scope/
  revision and preserve the ownership chain and Task/Dispatch identities.
  The read ledger includes the raw host observations referenced by those records.

A missing/stale handoff, changed source/scope/Dispatch, live/unknown execution,
unsettled effect/lease or competing acceptance refuses readback. Positive exit
is distinct from product success; settled outcomes need host evidence. An active
Dispatch marked `exited` needs a readable host evidence key in
`execution.observation`; a status label alone is insufficient. An active
or uncertain effect cannot disappear from a later note. Reconcile or obtain fresh
settlement evidence, update the note, then prepare a new handoff. A changed scope
needs its accepted record and a separately linked work-note boundary. Reference
the preceding note so current corrections and unresolved obligations survive.

## A new session while work is active

`write` and `prepare` support an active checkpoint. `accept` supports a settled
handoff: even the same accepted owner in a new session is refused while any Task
is live/unknown or any effect/lease is unsettled. The existing owner keeps the
single coordination authority. A successor may read originals and current host
receipts, organize the note and propose next actions; preparation/readback claims
alone do not permit new dispatch, stop/retry or source ownership changes. After
natural settlement, obtain positive host evidence, update the note and prepare a
fresh handoff for exact-scope acceptance. If transfer is essential before then,
the coordinator must separately verify the current Orca-supported ownership
transfer on the real Run/Task/Dispatch; this tool has no active-transfer path.
Do not label live/unknown work settled to satisfy `accept`. Host-tagged files and
successful structural checks are not actor authentication, actual transfer or
proof of successor understanding; compare the original host bodies and identities.

A fresh reviewer receives only the goal, candidate, raw evidence and relevant
constraints. Keep a producer's expected answer and another reviewer's conclusion
out of an independent first judgment. Successor readback and independent outcome
acceptance are separate. A read ledger proves an attestation, not comprehension
or an improvement in tokens/quality.

All note mutations use one lock and atomic individual files. There is no automatic
session replacement, scheduler or crash recovery across multiple files. Refuse
integrity mismatch and preserve conflicting originals. Parent integration remains
responsible for live observations, meaningful acceptance and resource settlement.
