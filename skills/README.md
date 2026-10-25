# Skills

Private skill contracts are installed under `${CODEX_HOME}/skills` only when
the managed ownership marker and digest agree. An existing user-owned skill
with the same name blocks installation instead of being overwritten.

See the [Expertise Orchestration v1 operating runbook](../docs/expertise-orchestration-v1.md)
for task-pack selection, specialist eligibility, knowledge receipts, evaluation,
and demotion procedures.

The main `agent-company` skill remains the explicit app-studio front door.
In this Orca fork it routes to [company-orchestration](company-orchestration/SKILL.md):
the Company-owned organization, model/subscription/effort, context/token, evidence
and lifecycle policy. The entire skill directory can travel together; it requires
no global orchestration, ultrawork or Core skill files. Orca itself remains the
execution host. Unused Core execution launchers and exposed entrypoints are
removed after tracing consumers; pure Company record/classification/report/state
functions remain local. Historical source and schemas are not execution authority.

Use the package's [update policy](company-orchestration/references/update-policy.md)
for source checks, read-only runtime observations and selective upstream changes,
and its [record contract](company-orchestration/references/record-contract.md) for
supplementary goal/owner/attempt/usage checks. These tools neither execute work
nor grant approval. Source, synthetic and actual host evidence stay separate.

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

The shared `research-methods` skill is the cache-first method procedure and the
on-demand researcher profile. It is not an ordinary lane role. Private research
records stay outside this repository.

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
specialists are optional routes, not copied hard dependencies. For the Orca fork,
staffing and verification depth follow the goal and claim rather than a fixed
roster. Roles may report evidence or reject readiness; important technical and
overall acceptance remains independent of the author.

Internal decision skills remain narrow: `evidence-debate` is single-pass by
default and returns unresolved material evidence to the assigning lead;
`problem-discovery`, `commercial-fit`, and `problem-business-loop` preserve
their separate discovery, validation, and loop contracts.

Validate the installed skill shapes without mutating user state:

```bash
# docs-audit: execute expected-exit=0
python3 scripts/test_qa_release_operating_system.py --case complete-matching-surface
# docs-audit: execute expected-exit=0
uv run scripts/test_agent_company_policy_suite.py --case existing-and-front-door
```
