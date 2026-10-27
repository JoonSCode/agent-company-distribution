# Optional local status snapshot viewer

`../scripts/status_view.py` reads one supplementary [`record.json`](record-contract.md)
and its `record_check.check_record(record, base, require_routing=...)` result, then
renders a local static HTML5 snapshot and an optional compact JSON view. It requires
only Python 3.13+ and the standard library.

```sh
uv run --no-project --python 3.13 python -B skills/company-orchestration/scripts/status_view.py render \
  /path/to/record.json --output /path/to/new-status.html --json-output /path/to/new-status.json \
  --require-routing --require-resources

uv run --no-project --python 3.13 python -B skills/company-orchestration/scripts/status_view.py cases \
  skills/company-orchestration/assets/status-view-cases.json --json
```

## Input and output boundaries

- **Single input**: Reads one version-1 supplementary `record.json` via
  `record_check.read_json_snapshot(path)` and validates consistency with
  `record_check.check_record(record, path.parent, require_routing=...)`. Input bytes
  and modification times are never modified.
- **Exclusive output or stdout**: `--output` and `--json-output` use exclusive file
  creation (`open("x", encoding="utf-8")`) and refuse to overwrite an existing file
  or the input record (exit `2`). Omit `--output` to print HTML (or `--json` view)
  to stdout. There is no `--overwrite` mode.
- **No external dependencies or active controls**: The snapshot uses inline CSS,
  system fonts, keyboard-accessible `<details>` elements, light/dark color-scheme
  variables, and an inline Content-Security-Policy (`default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'`).
  It makes no network requests, loads no external fonts/CDNs, and includes no
  JavaScript action controls, live snapshot merger, scheduler, or approval engine.
- **Escaping and unsafe references**: All dynamic text and attributes are escaped
  with `html.escape(..., quote=True)`. Evidence `ref` and `file` values are rendered
  as inert `<code>` text, never as clickable `href` links. Executable or inline-data
  URI schemes (`javascript:`, `data:`, `vbscript:`) and ASCII control characters
  (`0x00-0x1F` except `\t`, `\n`, `\r`, and `0x7F`) fail consistency (`unsafe_ref_scheme`,
  `invalid_control_char`).

## Separated claims and honesty boundaries

1. **Recorded consistency vs authority**: `record_check.py` checks internal claim
   consistency and local file SHA-256 pins when `file` is supplied. It does not
   authenticate receipt authorship, verify independent judgment, or prove actual
   user/product outcomes.
2. **Captured time vs generation time**: `captured_at` is shown only when explicitly
   supplied (`--captured-at` or `record.captured_at`); otherwise it remains `null`
   (`미제공`). `generated_at` is reported separately as the snapshot generation time.
3. **Static record vs live host state**: `live_host_state` is always `"unknown"`.
   A task recorded with `execution.state == "live"` is labeled as recorded `live`
   with current host process state unknown.
4. **Owner continuity without inference**: `goal.current_owner` is checked against
   the valid `accepted` chain in `$.ownership`. Proposed transfers (`status == "proposed"`),
   `task.parent`, `execution.actor`, and embedded `receipt_projections[*].observation.executor_terminal`
   never transfer or infer goal ownership.
5. **Four-way acceptance separation**:
   - **Task execution (`execution`)**: Settlement state, declared role actor vs
     optional embedded receipt `executor_terminal` and `reported_outcome`.
   - **Independent technical acceptance (`technical`)**: Reviewer distinct from
     `execution.actor`, bound to the task's current `dispatch` and `candidate`.
   - **Parent integration (`parent_integration`)**: Integration verdict by `task.parent`,
     bound to the task's current `dispatch` and `candidate`.
   - **Overall goal acceptance (`goal.assessment` + `goal.status`)**: Kept separate
     from task columns. All task checks passing (`basis == "team_checks"`) or a
     pending/missing overall assessment cannot earn overall goal success.
6. **Invalid, missing, or stale evidence**: Stale `dispatch`/`candidate` bindings,
   scope/revision mismatches, missing/broken evidence references, or hash-less
   evidence in a `real` record remain visibly invalid/unknown and cannot earn a
   success badge.
7. **Unknown token usage**: When `usage.coverage` is `unknown` or `partial` (or any
   check error exists), `total_raw_tokens` stays `null` (`미상 — 0으로 간주하지 않음`),
   never `0`.

## Deterministic counterexamples

Run the source regression suite:

```sh
uv run --no-project --python 3.13 python -B scripts/test_company_status_view.py
```

These deterministic tests verify source preservation and rendered/model fields across
counterexamples (execution success with overall pending, wrong candidate/Dispatch,
unknown usage, missing proof, scope mismatch, hostile text, and unapproved owner
inference). They do not establish human usability, which requires independent
browser inspection.
