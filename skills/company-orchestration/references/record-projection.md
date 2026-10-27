# Pinned receipt projection into a supplementary draft

Use this optional tool when copying observed Orca launch/model/result fields into
an existing [supplementary record](record-contract.md). It reuses `org_audit.py`'s
strict JSON and known-envelope normalization. It does not create a state store,
call Orca, fetch evidence, authenticate a receipt's author, or award acceptance.

The smallest supported path is one successful `worker-start` envelope with
`result.runId/taskId/dispatchId`, optional `launch.requested/effective.model/effort`
and one agent terminal effect. Optionally supply one successful `check` envelope
with `result.runId/messages` and exactly one bound `worker_done` for the selected
Task. Its structured `payload` may be a JSON string or object with `taskId`,
`dispatchId` and explicit `outcome` (`succeeded` or `failed`). Text bodies never
supply missing facts. Unrelated task messages in the supplied batch are allowed;
duplicate or mismatched `worker_done` rows for the selected Task fail instead of
silently dropping stale completions.

Use either direct CLI flags (to capture exact content hashes automatically from
the parsed bytes) or an explicit manifest with pre-computed SHA-256 pins (all
example identities are synthetic):

```json
{
  "version": 1,
  "coverage": "partial",
  "record": {"file": "record.json", "sha256": "<actual SHA-256 of original record bytes>"},
  "launch": {"file": "launch.json", "sha256": "<actual SHA-256 of receipt bytes>"},
  "done": {"file": "done.json", "sha256": "<actual SHA-256 of receipt bytes>"},
  "binding": {
    "run": "run-example",
    "task": "task-example"
  }
}
```

Manifest paths resolve relative to the manifest; direct flag paths resolve from
the current working directory. The caller supplies only `run` and `task` in
`binding`; `dispatch`, `candidate`, `revision` and `scope` are derived once from
the selected Task in the pinned original record, and the Task's goal revision and
scope must match the record's current goal. Redundant caller binding keys fail.
When `sha256` is supplied in a manifest, it must be an actual lowercase 64-digit
hash matching the file bytes; either way, the output records the exact content
hashes of the parsed bytes. `done: null` (or omitting `--done`) supports
launch-only input. Omitted model/effort, launch state and result observations
become explicit nulls. Known conflicting model values fail rather than being
replaced. Both runtime IDs, when present, must match. Missing runtime identity
is not authentication.

The record may contain multiple Tasks, and must contain the selected current
Task. An accepted-success goal, legacy single-task `receipt_projection`, an
existing projection for the same Task in `receipt_projections`, conflicting
binding, changed input bytes, duplicate JSON key, malformed payload or ambiguous
completion is refused. Declared `execution` fields (including role-owner labels
such as `source-analyst` and known lifecycle state/result), human/role judgments,
ownership, usage, technical and parent integration fields, and prior tasks'
projections and evidence provenance are preserved. Existing relative evidence
file paths are rebased to the original record's directory so moving the draft
keeps their meaning. The original record and receipts are never modified.

```sh
# Direct flags (6 user-supplied values: record, launch, optional done, run, task, output; plus optional --coverage):
uv run --no-project --python 3.13 python /path/to/company-orchestration/scripts/record_projection.py \
  --record record.json --launch launch.json --done done.json \
  --run run-example --task task-example --output draft.json

# Or explicit integrity manifest mode (9 leaf values when sha256 pins are pre-supplied):
uv run --no-project --python 3.13 python /path/to/company-orchestration/scripts/record_projection.py manifest.json --output draft.json

# Expected exit 3: a draft was created, not accepted success.
uv run --no-project --python 3.13 python /path/to/company-orchestration/scripts/record_check.py check draft.json --json
```

Use the same configuration and interpreter as the current record-check workflow.
Exit 2 means invalid input/I/O or an existing output; `--output` exclusively creates
a new file and never replaces one. The CLI prints `ok:false,status:draft` and exits
3 even when projection succeeds. `receipt_projections` is a task-keyed supplementary
annotation map; record-check ignores that annotation, as its contract specifies. A
record-check pass means only consistency of the checked claims. Independent checks
and explicit integration/overall acceptance are still required before genuine
completion.

Requested and effective model/effort populate only matching unknown (`null`) fields
on the selected Task; known non-null values are preserved when receipt settings are
omitted and rejected on conflict. Because `execution.actor` in real records often
names a role owner while launch receipts report a terminal handle, `execution` stays
untouched and the observed agent terminal is recorded separately as
`receipt_projections[task].observation.executor_terminal`. Original receipt files
and hashes are added to `evidence` under `receipt-projection:<task>:launch` and
`receipt-projection:<task>:done`; exact JSON pointers, derived bindings,
Task/Dispatch/run IDs and sender-reported result remain in
`receipt_projections[task]`. A `worker_done` report is not process-exit proof:
no retry, writer, approval, consent, technical acceptance, execution settlement
or resource/terminal release is inferred. Effective launch settings are host
receipt observations, not a separate provider probe.

`coverage: partial` describes only supplied observations and never implies absence
of other messages. `declared_complete` requires a done receipt with explicit
`result.page.hasMore:false`, no top-level/page truncation or cursor, and matching
`page.total` if supplied. It is still only a caller claim about the supplied page,
not proof of the whole Run or complete token usage. Usage is never synthesized.

A bounded comparison on the four checked `model` destination fields (`requested`,
`observed`, `effort_requested`, `effort_observed`) counts four manual destination
entries before and zero after when the launch receipt supplies them (or zero change
when a reused-terminal launch receipt omits model settings and existing declarations
are preserved). `execution.actor` remains a separate role-owner declaration and is
not overwritten by the terminal handle. Direct CLI mode requires 6 user-supplied
argument values (`--record`, `--launch`, `--done`, `--run`, `--task`, `--output`,
or 5 without `--done`; 7 with explicit `--coverage`), while manifest mode uses 9
manifest leaves (plus `--output`) when explicit SHA-256 pins are included, down
from 14 leaves when 5 task bindings were duplicated. Automated observations
(content hashes, derived task bindings, `executor_terminal`, launch state,
reported outcome, message ID and JSON pointers) are recorded without manual
hash/field typing, but argument selection, role-owner/lifecycle/review judgments
and validation remain operator work. This count measures field transcription only;
it does not measure elapsed time, model quality, tokens or end-to-end work
reduction. Revisit broader formats only when a real normal receipt cannot be
represented by this known shape.
