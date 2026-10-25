# Current Run completion and declared retention

Company owns `scripts/run_completion.py` and `scripts/completion_hook.py`. The
official installer registers a separate Codex `Stop` command in the supported
host `hooks.json` array, preserving Orca/user hooks and Core's plugin. Installer
and Doctor evidence must prove registration; source tests cannot. No Core change,
timer, historical sweep or worker completion trigger is involved. Stop is only a
wakeup. It never supplies an acceptance decision.

## Ordinary producer and callback

For each fresh Company Run, the lead creates its small directory under the
same record home used by `run_completion.py` and the installed Stop callback,
then calls `init` once. Explicit `SEJONG_HOME` or `--sejong-home` takes priority.
When Orca shares an installed Company skills directory, or its standard runtime
home invokes the canonical installed callback without mirrored Company skills,
the default is that installation's `sejong/runs`. For another unshared/standalone
package the default remains `CODEX_HOME/sejong/runs`.
Do not derive a second record home from the terminal's CODEX_HOME alone.
Use the actual host hook `session_id` and exact `cwd`; never substitute Orca
Task/Dispatch IDs or a guessed session. Flat and nested Run layouts work.
Namespace links are rejected. All commands use stdlib Python 3.13+.

```sh
uv run --no-project --python 3.13 python /path/to/company-orchestration/scripts/run_completion.py init \
  --run /exact/sejong/runs/current-run --run-id overall-goal-id --owner accepted-lead \
  --session-id exact-host-session --repo-root /exact/hook/cwd --record record.json \
  --consumer qa --consumer final-reader
```

`init` produces `retention-manifest.json` with `routing_accounting: "required"`
and an exact session registration under
`state/company-completion/<sha256(session_id)>.json`. There is no repo-latest or
inherited-session fallback. During work the owner declares exact singly linked
regular files. `register` hashes bytes and records device/inode/size/mtime/ctime;
it never expands directories or infers disposability from names. Directories
and undeclared contents remain. Never register source, required outputs/logs or
evidence, unique inputs, device data or another installation as disposable.

```sh
uv run --no-project --python 3.13 python /path/to/company-orchestration/scripts/run_completion.py register \
  --run /exact/sejong/runs/current-run --expect-manifest-sha256 exact-current-hash \
  --disposable scratch/raw.txt --preserve report.md --preserve acceptance.json
```

The lead writes the ordinary version-1 `record.json` after actual overall
acceptance. It must be real and resource-accounted. A fresh manifest also
requires a valid routing decision on every current task even when the record
omits `routing_accounting`. A manifest written without that field keeps the
previous completion gate and does not claim routing coverage. Re-init does not
rewrite an older manifest, and launches from before the checker are not
backfilled. Completion still requires this manifest's exact
goal ID/owner, succeeded overall goal, human/independent assessment with readable
hash-bound evidence, settled successful tasks, independent technical checks and
passed parent integration. Acceptance covers the retention declarations too.
Every consumer declared at init must be settled. An empty inventory explicitly
asserts no other consumers; it is never inferred from silence. The accepted record
must attest producer/writer quiescence and contain this checked extension:

```json
{
  "artifact_retention": {
    "run_id": "overall-goal-id",
    "manifest_sha256": "exact-current-manifest-sha256",
    "quiescent": true,
    "consumers": [
      {"id": "qa", "state": "settled"},
      {"id": "final-reader", "state": "settled"}
    ]
  }
}
```

The next actual Stop callback in this registered session invokes `complete`
**in executable code**. It takes an exclusive Run lock, verifies acceptance,
manifest identity/content and compact preserved evidence, protects all local
record evidence (including aliases), checks pins/open activity, then removes only
declared temporary files. Missing, unfinished or failed records skip cleanup;
invalid/stale success metadata fails closed. Unregistered sessions write nothing.
`completion_hook.py Stop` consumes stdin JSON `hook_event_name`, `session_id`,
`cwd` and emits `{}`. It does not alter other hooks' gates or approve success.

Manual replay uses `run_completion.py complete --record record.json
--expect-manifest-sha256 <exact hash>` with the same Run/home arguments and guards.
Automatic closure uses the installed callback. Repeated successful callbacks are
idempotent; reappeared deleted paths are preserved. A later Run in the same session
uses init's `--expect-session-binding-sha256 <exact prior binding hash>`; rebinding
also verifies the prior accepted completion receipt/record. Active/unknown Runs
cannot be replaced. Failed registration can resume against the same untouched
init declaration, never by overwriting a changed manifest.

## Preservation and failures

- `completion-receipt.json` preserves hashes and exact removed file bindings.
  `completion-rejection.json` reports failed checks without replacing prior
  successful/partial deletion evidence. `completion-hook-receipt.json` records
  registered callback skips/errors and actual results.
- Root/path-local `.pin`, `.keep`, `.active`, `PIN`, `KEEP`, `.lock`, `.pid`
  markers stop deletion; only the checker's own lock is exempt. External open
  files/directories stop deletion. Missing `lsof`, warnings, timeouts or read
  errors preserve data. The macOS observer has no silent portability bypass.
- Descriptor-relative no-follow traversal rejects parent/file links, hardlinks,
  special files and escapes. A unique same-parent quarantine rename is checked
  before unlink. A write-ahead receipt records pending unlink. Crash/unlink error
  preserves exact recovery evidence and blocks retry. Restoration never
  overwrites a replacement created by another writer.
- No cooperating writer may start after quiescence. Rechecks, locks and probes
  reduce races; they cannot make an uncooperative external writer obey. Interrupted
  quarantine needs owner recovery, not an automatic recursive retry.
- Required outputs, sources, evidence, pins, device data, other installations and
  unknown Runs stay protected. Do not use this mechanism to sweep old real data.

The checker validates recorded assertions and bytes. It cannot authenticate human
intent or prove that a self-authored assessment is independent. The lead and actual
assessor own that evidence/authority. Do not claim installed callback invocation,
space savings, quality or fleet agreement from deterministic fixture checks.
