# Optional saved Codex usage reader

`../scripts/provider_usage.py` reads only an explicitly supplied local JSONL file.
It does not launch providers, discover sessions, write files, or certify identity.
It supports the observed Codex `token_usage_record` schema, not a generic provider
adapter. Python 3.13+ and the standard library are sufficient.

```sh
uv run --no-project --python 3.13 python -B skills/company-orchestration/scripts/provider_usage.py \
  --trace /private/captured.jsonl --sha256 CAPTURED_SHA256 \
  --scope executor:DISPATCH_ID --turn-id OBSERVED_TURN_ID --format provenance
```

Replace the example values with observed values. The default provenance output
contains the exact trace hash, selected session/turn and response identities,
source line numbers, counts and coverage reasons. It excludes prompt text,
account metadata and rate limits. Store this output privately. Hashes bind bytes;
launch/done/session matching and independent provenance review remain necessary.

Repeat with `--format usage` to produce the exact five-field JSON accepted by
`outcome_eval.py collect --usage`: `coverage`, `raw_total`, `tokenizer`, `scope`,
`source`. Preserve provenance separately. Both commands print to stdout; choose
fresh destination paths if redirecting. Never redirect onto an input trace.

A reused session requires explicit `--turn-id`. The reader charges only that
turn's unique response IDs, never the entire session cumulative total. Identical
response records are counted once; conflicting duplicates are invalid. Cumulative
turn/thread counts and `token_count` mirrors are checks, not extra tokens.
Cached/cache-write input and reasoning output are included subsets, not additions.
Missing counts do not become zero. Only the exact observed six numeric fields
are supported; a changed provider schema requires review.

`complete` means complete reported usage for the selected captured turn: start,
completion, response prefix totals, final usage and cumulative mirrors agree.
It does not mean complete Company cost or proof that the provider reported every
internal operation. Missing boundaries, final usage, mirrors, prefix coverage or
final newline yield partial/unknown. Malformed JSON, a wrong hash, invalid counts,
identity or contradictory mirrors exit 2 without a usable total. Missing usage
has `raw_total: null`; partial usage is an observed subtotal, never an estimate.
Duplicate JSON keys are invalid even when their values match. A `turn_context`
inside the selected turn boundaries must identify that turn. A trailing
`response_item`, `agent_message`, or `item_completed` carrying an `AgentMessage`
without subsequent response usage makes the selected subtotal partial. These are
checks of the observed event formats, not proof of coverage for unknown formats.

The declared scope is caller-owned. Verify its Task/Dispatch and turn binding
against raw launch/done receipts before aggregation. For multiple reports,
union `(provider, response_id)` identities once and reject conflicting identities
or values. Never sum overlapping exports. Shared multi-task responses stay
unallocated; do not divide them by time or output length. Lead, verification,
integration and failed/retry scopes need their own observed intervals. If any
required scope is absent, end-to-end usage remains unknown. The reader does not
infer tokenizers, costs or tokens from prices, credits, quotas or text length.

Focused validation:

```sh
uv run --no-project --python 3.13 python -B scripts/test_company_provider_usage.py
```

Tests use synthetic traces. Replay of private real traces is separate evidence,
not a public fixture or an assertion about future provider behavior.
