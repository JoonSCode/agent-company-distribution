# Task candidates

Apply [routing policy](model-routing.md), [configuration](configuration.md) and
[evidence freshness](model-evidence.md). This is a human decision aid, not a
router, certified equivalence table or automatic model assignment.

## Select by the task

Compare only supported, authenticated service/model/effort/tool/billing
combinations allowed by resolved configuration and explicit current-task pins.
Model and effort IDs are opaque route-specific labels. No public provider order,
model exclusion, head-model pin or effort floor applies.

| Task | Starting approach | Evidence needed |
|---|---|---|
| Exact lookup, formatting or deterministic validation | Use an existing tool directly | Exact input and output checks |
| Small clear edit or extraction | A supported candidate with reliable verification | Scope, acceptance and applied setting |
| Interacting code or unexplained failure | Compare candidates suited to causal diagnosis | Failure evidence and meaningful regression checks |
| Consequential judgment or integrated review | Compare reasoning, tool and context fit | Original evidence, counterevidence and independent acceptance |
| Coordination across owned tasks | Smallest sufficient team | Briefing/integration burden, lifecycle and independent review |

First meet quality, authority, tools and billing requirements. Then compare
complete observed raw tokens within the deadline; keep time separate. Count
context transfer, failed attempts, retries, integration and review. Different
provider tokenizers limit cross-provider comparisons. Unknown usage stays unknown;
price, quota or speed does not prove fewer total tokens.

A stronger model at lower effort may outperform another at higher effort, or the
reverse. Do not impose a mandatory cheap-first ladder or fixed role-to-model map.
Reassess after a material scope/acceptance change, failure or relevant new evidence.

## Route and selection receipt

Codex, Claude Code direct, Antigravity, Grok and Cursor are separate execution
routes. A model available through one route does not prove another route's
subscription, tools, native effort, authentication or billing. Verify the actual
host and keep shared quota counted once. API-paid execution requires explicit
opt-in and never becomes an automatic fallback.

Keep the dated task/risk, candidates, exclusions, source limits, requested and
observed model/effort, billing, context/reuse rationale, usage unknowns and
independent review owner in a private work note. A synthetic receipt proves only
its own structure. The host's Task/Dispatch contract remains authoritative.
