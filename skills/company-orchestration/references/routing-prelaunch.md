# Routing prelaunch prototype

`record_check.py routing-check` applies the fresh prelaunch check. Historical
records remain readable through `check` and the historical case suite; their
successful validation does not certify a past prelaunch check.

An unpinned fresh decision supplies `price_selection.inventory_evidence`. The
referenced host evidence includes `candidate_inventory`, a list of route,
family, model and effort objects. Real evidence must pin the current host's
canonical Codex home's `models_cache.json`. For an unpinned Codex selection, the checker
independently intersects its models and supported efforts with the packaged
table and requires each non-excluded known model at the selected effort and
every known pair that dominates the selection on the benchmark prior in the
candidate list. It does not infer that those models are authenticated, have the
necessary tools or are adequate. The file's freshness and provenance are
supplied evidence, not independently certified by this check. The evidence must
provide timezone-aware `observed_at` and `valid_until`; expired bounds fail.
A quality exclusion requires a task- and
candidate-bound `task_failure` with a separate support reference; unknown
quality does not justify exclusion. An unavailable runtime candidate needs a
candidate entry in its host evidence's `unavailable_candidates` list.
Benchmark scores and prices are directional priors, not actual task outcomes or
charges. A candidate dominated on score and cost is rejected; a nondominated
choice is allowed. A fresh user pin binds task, scope, revision, attempt and
the selected pair. A real pin requires human evidence and host support evidence.

`routing_launch.py` supports new Codex workers and evidence-bound reuse. It requires the current
record, a decision whose binding contains the SHA-256 of the exact UTF-8
`--spec`, and unused prelaunch and host-result receipt paths. It checks before writing the receipt and
invoking `orca orchestration worker-start`, using only the checked model and
effort. An optional `--parent` must match `binding.parent_task` in the decision.
The host result retains the original stdout, stderr and exit status,
bound to the prelaunch receipt; actual Task and Dispatch IDs are host output.
Missing IDs or effective settings leave the readback unverified, and different
effective settings fail it even if the host exits zero. Preserve the host result
and inspect its resource effects before any recovery; never retry automatically.
For reuse, supply the original launch receipt, its dispatch and terminal. The
decision binds the original hash and a pinned host observation that settings
were unchanged, including `observed_at` and `valid_until` UTC timestamps. The
launcher checks those supplied bounds; it cannot independently prove that the
settings stayed unchanged. It compares the original `launch.effective` model
and effort with the selected pair, plus a current `worker-show`, live agent
projection and the same terminal incarnation. This is not a fresh provider
model/effort readback.
Unknown or changed evidence denies reuse without starting a replacement. Orca
still owns Task and Dispatch lifecycle and recovery.

For a precreated Task, use `--task <id> --run <id>` instead of `--spec`.
The record's `run` and decision's `binding.run` must equal that Run, and
`binding.task`, `binding.parent_task` and `binding.spec_sha256` must match the
current host Task and its exact UTF-8 specification. A first dispatch uses a
planned binding and a current record attempt `planned:<id>`. A retry additionally
uses `--retry-of <dispatch>`; the record must bind that settled failed attempt,
and the current host Task, latest Dispatch and worker observation must agree.
Read-only host checks precede the single worker-start call. Pass placement again.
An explicit Run on a new-spec launch also requires the record and decision Run
binding; it does not change the coordinator's session binding. The resulting
host receipt must identify that Run and, for an existing Task, the same Task
and a different retry Dispatch. Missing identities are unverified; mismatches
fail. All host output and effects remain in the result receipt.

For a recorded decision with inventory evidence, record checking uses the
archived, hash-pinned inventory and prelaunch receipt to recheck the selected
pair and its comparison. It verifies the receipt's scope, revision, exact
specification hash, selected pair, table and comparison. It does not require
the old inventory still to be fresh, or claim a new launch is authorized.
Historical records without inventory evidence retain their previous check.

`routing_hook.py` is an opt-in Codex PreToolUse adapter. Its
`bind --session ... --decision ... --record ... --receipt-dir ...` creates
exclusive session metadata under the Company state directory. The optional
`COMPANY_ROUTING_SCOPE` environment variable can point to equivalent JSON.
Each contains the session ID, decision and record paths, and receipt directory.
An existing binding can be replaced only with its exact prior SHA-256 via
`--expected-sha256`. Unrelated
sessions and unrecognized tools are unchanged. For recognized raw Orca
worker-start commands it checks the decision and denies the direct command,
requiring the checked launcher. It checks recognized native `spawn_agent`
calls against an existing current parent Task and Dispatch, the selected model,
effort and exact message hash and writes a
receipt keyed by the tool-use ID; that ID is not an Orca Task ID.

The source installer has a separately owned registration and rollback entry;
source definition and tests do not prove installed registration, trusted load
or actual coverage.
Hooks do not intercept `write_stdin` again, hidden scripts, unsupported tool
paths, unloaded hooks or other providers. Shell recognition is intentionally
limited to recognized shell command segments and literal JSON-style `cmd`
strings in `functions.exec`; it is not an OS or server enforcement boundary.
Do not activate the
adapter before independent review and verified transactional installation.
The installer registers the canonical home. Each separate execution home needs
its own verified supported hook registration and fresh trust/load observation;
canonical registration alone does not prove that runtime home is protected.
The existing `scripts/repair_runtime_hook.py --runtime-home <path>` plans the
shared-home registration and preserves unrelated hooks. Its `--apply` mode uses
the transaction and verifies the fresh target hook list; it requires the
canonical commands to be enabled and trusted first. It does not prove that a
previously running Codex session loaded the new hook.
