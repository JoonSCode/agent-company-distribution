# Timeline from pinned receipts

Use the local timeline to inspect which routing, launch, worker report, and
settlement observations survive in saved receipts. Supply the exact bytes you want
to replay. The timeline preserves prior attempts and flags the attempt you select
as current.

```sh
uv run --no-project --python 3.13 python -B /path/to/company-orchestration/scripts/stage_timeline.py manifest.json
```

The CLI prints JSON to stdout. Exit 0 means a projection was produced, including
when it contains a failure or unknown. Exit 2 returns a fixed error code for
invalid, unavailable, or conflicting input. Local replay consumers can import
`stage_timeline.project(manifest, base)` from the packaged scripts directory with
the same Python and an explicit absolute base directory. Input errors raise
`TimelineError`.

## Manifest v1

Use original receipts and replace example hashes with their SHA-256 digests.
Relative receipt paths are relative to the manifest directory for the CLI, or
the supplied base for the callable. Each receipt is read as a bounded regular
JSON file through a physical path. The input can stay in private storage.

```json
{
  "version": 1,
  "current": "attempt-b",
  "attempts": [
    {
      "id": "attempt-a",
      "run": "run_example",
      "task": "task_example",
      "revision": "0123456789abcdef0123456789abcdef01234567",
      "precheck": {"file": "denied.json", "sha256": "<64 lowercase hex digits>"}
    },
    {
      "id": "attempt-b",
      "run": "run_example",
      "task": "task_example",
      "revision": "0123456789abcdef0123456789abcdef01234567",
      "launch": {"file": "launch-state.json", "sha256": "<64 lowercase hex digits>"},
      "worker_done": {"file": "check.json", "sha256": "<64 lowercase hex digits>"},
      "settlement": {"file": "worker-show.json", "sha256": "<64 lowercase hex digits>"}
    }
  ]
}
```

Each attempt supplies at least one receipt. Source keys accept omission or
`null` for missing receipts.

| Key | Saved receipt shape |
| --- | --- |
| `precheck` | Routing check report with a `company-routing-decision/v1` receipt, including a rejected check. A planned spec launch can refer to a local alias before the host assigns a Task ID. |
| `launch` | The checked launcher's v1 state file. Observed states include the original successful Orca envelope in the JSON string at `/stdout`. A pending invocation, timeout, or failed readback leaves the host outcome unknown. |
| `worker_done` | Successful Orca inbox check envelope. Match structured payload, Task, Dispatch, and sender. An envelope that includes several known attempts can be supplied to each one. An ambiguous or unaccounted-for completion for the selected Task fails the projection. |
| `settlement` | Successful Orca worker-show envelope with a matching `result.dispatch`. A terminal Dispatch status records that host's saved observation. |
| `usage` | Saved `company-native-usage/v1` report. Use only a bound task breakdown row for the exact Run, Task, and Dispatch. Partial coverage can retain an observed subtotal. |
| Top-level `installer` | A saved installer transaction journal `agent-company.install-transaction/v0.2`. The journal phase is independent context with no Orca attempt binding. |

There is no fallback search for a receipt. Report paths, transcripts, caches,
configuration, ambient run state, Orca and providers are outside the projection.

## Projection v1

The output has `format: "company-stage-timeline/v1"`,
`coverage: "supplied_receipts"`, and attempts in manifest order. Ordering across
attempts follows the caller's list and makes no claim about chronology. The
attempt ID, Run, Task, Dispatch and known predecessor use SHA-256 identifiers.
The caller's revision is checked against the precheck when supplied. Without a
checked observed launch, the Dispatch remains unknown and settlement or usage
cannot attach to the attempt. A precheck and launch supplied together must agree
on available decision and precheck hashes. The binding shows `precheck_link` as
`receipt_sha256` for an exact byte link, `decision_sha256` for a shared decision
pin without a receipt pin, or `unknown`. `revision_source` names the precheck or
the manifest.

The stages, in display order, are `routing_precheck`, `launch`, `worker_report`,
`worker_settlement`, `independent_review`, and `tool_execution`. Each carries
`status`, `reason`, `occurred_at`, `observed_at`, `duration_ms`, and
`evidence`. An exact evidence reference is a receipt `sha256` and JSON
`pointer`. The launch reference also has an `embedded_pointer` for the
separately parsed host envelope. A rejected check may include allowlisted
`reason_codes`. Free-form diagnostics never enter the output.

`occurred_at` uses only an explicit-offset receipt timestamp, normalized to UTC.
Naive, missing, or reversed Dispatch timestamps leave the affected time unknown.
Capture time and elapsed durations are `null`. The projection never adds
overlapping stages, fills stage gaps from file timestamps, or infers latency from
wall clock differences.

An explicit zero in a bound usage row is preserved. Missing or unbound counts
are `null`. `whole_run_total_raw_tokens` stays `null`, as do
`technical_acceptance` and `overall_acceptance`. A sender report supplies no
independent review, and an installer journal supplies no deployment verdict.
SHA-256 pins establish consistency with the supplied bytes. Current host state,
receipt authorship, authority, and operational gains require their own evidence.

## Optional launcher timing

Add `--record-timing` to an enrolled checked launch to retain timings in its
existing private result. Include that exact result under `launch` in the
manifest above. For an observed launch, use the Task ID returned by Orca. The
projection adds `launch_timing` with the local process epoch, individual
spans, clock reversals and attribution.

The spans measure enrollment preparation, lock acquisition, preparation while
holding the lock, the local worker-start subprocess, and response readback.
The lock span includes acquiring and validating the protected namespace. The
worker-start span includes local transport and may include timeout handling.
Each duration comes from the same launcher's monotonic clock. Keep request and
provider work, time between recorded spans, and the lifetime of the worker
outside these spans. These values describe observations by the launcher process.
Use observed host readback to attach them to a Dispatch. If a stage was missed
or the operation stopped, the projection reports the gap from the saved state.

## Offline outcome replay

Pass the same manifest and an explicit assessment JSON to
[`offline_replay.py`](../scripts/offline_replay.py).

```sh
uv run --no-project --python 3.13 python -B /path/to/company-orchestration/scripts/offline_replay.py manifest.json assessment.json
```

The assessment object has `candidate` (`revision` and `sha256`), `outcome`
(`candidate_sha256`, `reported`, `execution`, `checks`, and `trace_present`),
`review` (`candidate`, `assessor`, `executor`, and `critical_failure`),
`consent`, and `release`. Use saved evidence for the same candidate. The result
reports an offline status and coverage on stdout. It performs no launch,
provider call or approval. Exit 2 reports refused or invalid evidence.
