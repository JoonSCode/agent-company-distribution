# Skills

Private skill contracts are installed under `${CODEX_HOME}/skills` only when
the managed ownership marker and digest agree. An existing user-owned skill
with the same name blocks installation instead of being overwritten.

See the [Expertise Orchestration v1 operating runbook](../docs/expertise-orchestration-v1.md)
for task-pack selection, specialist eligibility, knowledge receipts, evaluation,
and demotion procedures.

The main `agent-company` skill is the explicit app-studio front door. It
projects a King Sejong Core decision into the smallest valid Direct, Role, or
Squad lane. It does not own Core routing, worker lifecycle, approval, or final
verification.

Role operating systems include:

- `founder-operating-system` for portfolio choice, opportunity cost, and
  falsifiable continue, change, pause, or stop recommendations;
- `planning-operating-system` for goal-faithful decomposition, dependencies,
  acceptance criteria, and verification design;
- `development-operating-system` for bounded implementation evidence;
- `design-operating-system` for proportional design paths;
- `marketing-operating-system` for demand and distribution evidence;
- `qa-release-operating-system` for matching-surface, Simulator, real-device,
  privacy, StoreKit, App Store Connect, and release-candidate evidence.

The shared `copywriting-operating-system` specialist handles knowledge-backed
UX writing, conversion copy, brand voice, localization, and copy review after
Marketing strategy or Design interaction decisions are settled. It returns to
the requesting role and never becomes an ordinary lane role.

All six roles expose one canonical machine-readable operating contract. A role
plan and current execution handoff carry both the repository-relative contract
path and its pinned SHA-256.

`policies/expertise-registry.json` maps each role OS to bounded optional
specialists, and `policies/reference-manifest.json` pins its Role Kernel and
reference metadata. `policies/expertise-routing.json` selects exactly one
decision-relevant Task Pack and only trigger-backed specialists. Parent-issued
runtime reference sets admit fresh Current Sources and Job Evidence; the
content-hash cache and read ledger retain hits, misses, used reads, and unused
reads without exposing Evaluation Sets. Current execution handoffs require a
verified Knowledge Usage Receipt. Logical role sessions bind the context,
receipt, read ledger, and handoff at maximum concurrency one; they never
require persistent or background workers.

Platform, iOS, Figma, product-design, data, founder-lens, and security
specialists are optional routes, not copied hard dependencies. The default
combination is one Role OS, zero to two specialists, and one independent
verifier. A role may report evidence or reject readiness, but Seungjeongwon
retains independent final verification authority.

Internal decision skills remain narrow: `evidence-debate` is single-pass by
default and escalates unsettled evidence to Jiphyeonjeon;
`problem-discovery`, `commercial-fit`, and `problem-business-loop` preserve
their separate discovery, validation, and loop contracts.

Validate the installed skill shapes without mutating user state:

```bash
# docs-audit: execute expected-exit=0
python3 scripts/test_qa_release_operating_system.py --case complete-matching-surface
# docs-audit: execute expected-exit=0
uv run scripts/test_agent_company_policy_suite.py --case existing-and-front-door
```
