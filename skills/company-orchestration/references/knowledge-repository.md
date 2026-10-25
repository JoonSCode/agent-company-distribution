# One private local knowledge repository

The existing `knowledge/research` root is the single reusable store for research,
lessons, user corrections, failures, insights and references. The historical name
stays to preserve callers and originals. Keep core role principles, stable
procedures and required distribution/evaluation resources in Company. Keep
private experience and detailed dated reference collections in the private store.
Do not move every role reference or evaluation case out of the installed package.

[research_cache.py](../scripts/research_cache.py) remains the record/index/history/
conflict/search implementation. [knowledge_repository.py](../scripts/knowledge_repository.py)
adds explicit local Git wrapping and reviewed source imports. It does not run a
network operation, create a remote, push, sync hosts, schedule work, execute Git
hooks or automatically commit on termination. Git is versioned storage, not model
weight training or a permission system. A `.git` directory alone is not adoption.

## Existing and new records

v1 records, hashes, Markdown and default CLI/root remain readable without rewrite
or Git. New `company-knowledge-record/v2` uses the same fields and adds `knowledge`:

| Field | Meaning |
| --- | --- |
| `kind` | research, lesson, correction, failure, insight, reference |
| `claim` | observation, hypothesis, preference, decision |
| `scope_level` | project, role, global; a label does not enlarge authority |
| `applicability` | Conditions and limits of application |
| `source_authority` | Who/what supplies the claim, distinct from authority to execute |
| `verification` | Observed check and remaining limits, including unverified |
| `tags` | Small search hints, not a taxonomy requirement |

`current` means current index entry, not proven truth. Storage does not promote a
record to a global command, accepted policy or independent result. Preserve
provenance/date, uncertainty, counterevidence, disposition and replacement links.
An ordinary v1 `update` of a current v2 record is refused with
`classification_required` (exit 4). The current record, index and history stay
unchanged; the rejected payload is retained under `conflicts`. Existing v1-to-v1
updates remain supported. To update v2, submit an explicit v2 payload with all
`knowledge` fields and the current CAS hash; classification changes are visible
in the payload and revision history. Use replacement links for retired claims.
A v2 reuse assessment conservatively requires exact scope text; retrieval is only
a candidate list. Apply a narrower context only after owner judgment, keeping that
judgment in the usage result. Volatile facts still need live verification.

At a consequential task start, search a relevant subset (`search --query TEXT
[--kind KIND] [--scope-level LEVEL]`), read selected originals, assess scope/date/
source and contradictions, then record actual use or non-use reason through `use`
with the current content hash. Important learning is recorded during work and
curated at a natural boundary. Do not require a retrospective for routine work.
A user decision keeps its original scope and authority; a correction should
replace/contradict the prior claim with a new id rather than silently erase it.
Raw private transcripts, prompts, connector payloads, secrets, held-out evaluation
cases and review answers do not belong here. Do not automatically ingest media.

## Reviewed source imports

Use `uv run --no-project --python 3.13 python knowledge_repository.py --root ROOT`.
All paths below are explicit; the actual private default remains the cache root.

1. Prepare a small `company-knowledge-seed/v1` manifest with `entries`, each an
   explicit `source: {path, sha256}` and curated v2 `record`. Select only small
   Markdown/JSON research sources that the owner has reviewed. Keep classification,
   date, scope, counterevidence and source limits. Do not feed evaluation answers.
2. `seed-plan --manifest manifest.json` verifies sources and existing records,
   returns `plan` with exact destination/source hashes and expected index digest.
   Save that plan object outside the root and independently review privacy/scope.
3. `seed-apply --plan seed-plan.json --expect-plan-sha256 HASH` archives selected
   originals byte-for-byte under `origins/<source-hash>.md|json` and inserts curated
   v2 records with both original and archive provenance. It never rewrites a
   source file. Changed source/index or divergent existing id refuses the import;
   a divergent record keeps its rejected body under existing `conflicts`. An exact
   repeat is idempotent. Before the first import write, the tool preserves a
   hash-bound journal under `.knowledge-seeds/<plan-hash>.json` with the exact
   approved plan, baseline index and file inventory. These are private recovery
   evidence, excluded from Git snapshots; they are not execution authority.
4. Verify archive bytes and record retrieval before reducing a source reference
   to its small maintained procedure or dated starting prior. Company Git history
   alone is not proof that the private copy was preserved or used.

After an interrupted import, rerun the **same** `seed-apply --plan seed-plan.json
--expect-plan-sha256 HASH`. It verifies all original sources, the journal, every
baseline file, partial archive/JSON/Markdown byte and current index before filling
missing outputs. The index may contain only the original rows plus this plan's
exact completed insertions. An interrupted archive, record file, index write or
entry boundary can therefore resume without overwriting partial evidence. An
indexed entry must still have all its outputs. Source changes, divergent outputs,
other writer/index changes, unknown files or unindexed records without the original
journal refuse recovery and preserve the evidence. A fresh plan cannot certify an
unowned partial record; preserve it and assign explicit review instead of deleting
it or treating a changed original as already imported. This bounded resume does
not repair unrelated cache update/history corruption or authenticate the operator.

## Local Git plan, apply and snapshot

- `plan` verifies the cache and returns a `plan` object binding exact files/hashes,
  exclusions and root. Save just that object outside the root. Review curated
  text and excluded paths; secret-pattern rejection is incomplete privacy screening.
- `apply --plan plan.json --expect-plan-sha256 HASH` initializes local Git in that
  same root and records the reviewed inventory. Existing records stay unchanged.
  Identical application is idempotent; changed inventories or unrelated repos
  are preserved and refused. No automatic initial commit or add-all occurs.
  Git is first initialized in `.knowledge-git-init/`; `.knowledge-init.json`
  records its expected pristine metadata bytes (from a temporary restricted Git
  template), directory identity and approved plan before staged initialization.
  The exact initialized directory is then moved to `.git`. These controls are excluded
  from snapshots and remain available as recovery evidence.
- Refresh `plan` after approved records/imports. `snapshot --plan plan.json
  --expect-plan-sha256 HASH --owner OWNER --message TEXT` explicitly stages only
  validated records/index/history/conflicts/origins and the migration receipt,
  then makes a local commit. Its one-command identity does not change global Git
  configuration. A repeat without changes returns the current commit.

The cache lock also covers seed/index/Git snapshot. Every participating writer
must use it. Existing Git locks/pre-staged work or unexpected tracked paths block
snapshot rather than absorb another owner's changes. Plain external Git writers
can bypass this lock; coordinate quiescence and one commit owner before a snapshot.
For interruption after the initialization evidence is saved or after `.git` is
moved but before the migration receipt is saved, rerun the **same** `apply --plan
plan.json --expect-plan-sha256 HASH`. The source inventory, owned Git directory
identity and every Git metadata byte must match. The tool finishes only the move
or missing receipt; it does not reinitialize an unrelated repo, stage, commit or
push. Missing initialization evidence, unverified staging, modified metadata or
changed inventory blocks recovery with `recovery_conflict` or
`migration_conflict`. Preserve the staging/metadata and assign review; do not
invent a receipt or remove an existing repo. An owned, still-empty staged Git
directory can resume initialization. Staging without ownership evidence or a
partly initialized Git whose metadata differs from the expected pristine state
requires review. Individual writes are atomic; this is bounded
resume, not general rollback, filesystem durability certification or recovery of
partially staged snapshots. A record/index mismatch from other cache operations
still blocks mutations. Keep partially staged work and investigate I/O failures.

Only curated allowlisted regular files are committed. Unknown files are listed
without loading their bodies. Per-file limits reject oversized curated bodies;
large artifacts stay with their existing owner and a reference/hash. Known
credential-shaped text, symlinks and Git attributes are refused; human privacy and
rights review is still necessary. Lock files, temporary files and unrelated media
are excluded. Originals/history/conflicts have no automatic delete operation.

## Hosts and later policy adoption

Use the existing private fleet checkpoint, not a public remote or a daemon.
Compare id/revision/content hash on each host; preserve newer/divergent records
and record offline work with last observation, change reference and next owner.
Git commits do not establish policy equivalence or settle conflicts. Source-policy
promotion is a separate reviewed change with its scope, evidence, counterevidence,
source/version and independent verification. Existing sessions retain their
accepted version until a natural boundary. No automatic global rule or weight
learning follows from recording a lesson.
