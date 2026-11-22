# Audit saved role context

Run the opt-in tool with the selected Python 3.13 interpreter. It reads the
named files and emits JSON to stdout.

```sh
python3.13 -B "$COMPANY_SKILL/scripts/role_context_audit.py" --request audit.json
```

A pin is `{"path":"relative/file","sha256":"<lowercase SHA-256 of the exact bytes>"}`.
Use these three JSON objects with the exact fields shown. Files named by the
request resolve beside the request. Source paths resolve beside the frozen
context and must be canonical relative paths, without links or parent traversal.

| Object | Fields |
|---|---|
| Request | `schema: "company-role-context-audit-request/v1"`, `scope`, `context` (pin), `capture` (pin or null) |
| Frozen context | `schema: "company-role-context/v1"`, `candidate`, `role`, `pack` (pin), `references` (nonempty array of pins) |
| Saved capture | `schema: "company-role-context-capture/v1"`, `scope`, `context_sha256` (frozen context pin's digest), `events` (ordered array) |

`scope` has `candidate` (full 40-character Git SHA), `role`, `session_id` and
`turn_id`. Use the expected identity from the assignment, the frozen pack and
reference inventory from before the turn, and the saved capture from the
specified session and turn. Retain the originals and their locators with the
capture so a reviewer can check its origin and ordering independently.

Each event has `kind`, `source` (the exact frozen path and SHA-256) and `text`.
Use `delivered` for full source text present in saved model-visible input and
`read` for full source text present in a saved read result. Preserve UTF-8 bytes,
including line endings. Use `citation` for an explicit path, digest and verbatim
quote emitted by the role. The citation must follow a matching delivery or read
and the quote must occur in those source bytes. Omit evidence that the capture
cannot substantiate, including partial previews, planned reads and prior
read-ledger attestations. The generic [CLI tests](../scripts/test_role_context_audit.py)
provide synthetic inputs.

Exit 0 reports verified readable files and saved event positions (one-based).
Exposure stays `unobserved` where neither event was supplied. Exit 2 rejects
invalid input, missing or stale pins, scope mismatches or unsupported citations.
The operator supplies the capture. A reviewer still checks its native provenance,
the inventory's coverage of the assigned role, and the role's decision and
counterexample reasoning. The tool leaves `independent_judgment` null and grants
no authority. Existing briefs and ledgers continue through their original paths.
