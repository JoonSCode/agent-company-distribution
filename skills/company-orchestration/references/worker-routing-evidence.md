# Default worker-routing evidence and policy

This source-distributed note configures a practical **proposal** table, not a
universal capability certificate. No raw private prompts, CLI logs or account
metadata are distributed. The standalone pilot is not a Company-authorized
launch and does not open the measurement-required I05 gate.

## Orders

All ten families have explicit easy, medium and hard rows, each with three
distinct local candidates. Media-generation rows remain disabled. Priorities
0–2 mean primary, fallback1 and fallback2, not runtime retries.

| difficulty | primary | fallback 1 | fallback 2 | local effort |
|---|---|---|---|---|
| easy | gpt-6.1-terra | gpt-6-luna | gpt-6.1-sol | low |
| medium | gpt-6.1-terra | gpt-6.1-sol | gpt-6-astra | medium |
| hard | gpt-6.1-sol | gpt-6-astra | gpt-6.1-terra | high |

The original general primary/effort choices and first two backups are preserved.
The former third backup is removed, not renamed as the common default. These
orders are editorial task-fit policy, not pilot-derived quality rankings.
No measured low/high effort or medium/hard task performance, statistical
superiority, universal ranking or subscription-cost advantage is claimed.

### Shared default

Table v2 separately configures `common_default` as codex/gpt-6.1-terra/medium.
The explicit medium effort is a shared policy setting, not an inferred quality
ranking or a per-row effort override. Its capabilities are the union of the
existing non-generation Terra editorial assertions below; the same observation
limits (including design strict fail) apply. It advertises no named tools,
constraints, positive context capacity, image/audio/video generation or edits.

It is consulted only after an existing row has no eligible local candidates;
all filters and exact pins still apply. A route/model already present locally
is skipped even at a different effort. Thus the stock rows, which already
contain Terra, do not attempt Terra again after local exhaustion. Distinct-model
external rows can reach the separate default; this is tested with synthetic
fixtures, not represented as observed runtime failover. Missing rows stay
NO_MATCH. The schema requires explicit migration from table v1 and the checker
requires newly prepared binding v3; old bindings cannot discard provenance.
See [prelaunch semantics](routing-prelaunch.md#local-backups-and-shared-final-default-table-v2).

## Migration

Sources: repository `policies/model-profile-registry.json` (separate legacy
semantic dispatcher), packaged `assets/model-choice-priors.json` checked
2026-10-27, and `references/model-routing.md` / `references/model-evidence.md`.
The registry is not silently rewritten and its rate-card, authority, concurrency
and task restrictions are not migrated into profile capabilities.

| source semantic seed | source identity | explicit profile-table successor | retained rationale |
|---|---|---|---|
| mechanical | gpt-5.6-luna/low | gpt-6-luna/low | bounded repetitive/fixture work; easy alternative |
| standard-implementation | gpt-5.6-terra/medium | gpt-6.1-terra/medium | clear existing-pattern implementation; medium primary |
| bounded-deep | gpt-5.6-luna/high | gpt-6-luna/high | bounded fully-verifiable hard alternative, not general integration parity |
| integration | gpt-5.6-sol/high | gpt-6.1-sol/high | multi-module/integration; hard primary |
| specialist-reasoning | gpt-6-astra/high | gpt-6-astra/high | uncertain reasoning; hard fallback |
| role-lead/company-judgment | gpt-6-astra/high | no authority migration | non-dispatchable judgment roles stay non-dispatchable |

These are deliberate successor **policy aliases**, not a provider assertion of
model equivalence. Current spellings come from the packaged priors; all four
requested identities answered the CLI pilot at medium effort. Returned events
exposed neither actual backend model nor applied effort. No automatic 5.6
substitution and no claim that a stale registry identity has been tested.
The registry does not provide an exact ten-family mapping; the following mapping
is an editorial extension of its seeds and packaged qualitative priors.

## Family policy and observed limits

Each heading is the evidence anchor used by every candidate in its three rows.
Enabled capability strings are **editorial task-fit assertions**, not measured
coverage. All candidates retain explicit source links, even where observations
are negative. The table is fully inspectable in `assets/worker-routing-table.json`.

### general
`general.execute`: focused-work prior; observed one scheduling-style answer per
requested model. Original general primaries retained at all difficulties.

### language
`text.summarize`, `text.rewrite`, `text.translate`: visual-writing/focused priors
and mechanical documentation seed. Only one exact-match translation was tested;
summary/rewrite, languages in general and professional editorial quality were not.

### structured_data
`data.lookup`, `data.transform`: mechanical fixture/evidence seed and focused
prior. Tiny supplied-data ordering tested; no external lookup/database connector
or large-data reliability established.

### reasoning
`logical.reason`, `quantitative.reason`: judgment/specialist-reasoning seeds.
One small logic fixture tested, not hard reasoning or quantitative reliability.

### code
`code.reason`, `frontend.code`, `framework.react`, `screenshot_to_code`: coding
and visual-writing priors plus standard-implementation/integration seeds.
Only static code-value reasoning tested; frontend/React/screenshot implementation
is unmeasured policy support. Repository editing is deliberately not advertised:
a specific write-capable runner, permissions and task validation are required.

### research
`evidence.synthesize`, `citation.ground`: evidence task seed and judgment prior,
limited to supplied sources. Pilot was a small calculation from supplied excerpts,
not web research or citation quality. External retrieval requires a separately
verified named tool; none is advertised by this stock table.

### visual
`vision.read`, `vision.ocr`, `multimodal.reason`: visual-writing prior (Luna's
extension is editorial, since its packaged prior omits visual-writing), catalog
text/image input metadata and an actual attached synthetic PNG in the pilot.
All four answered red; OCR and general visual reasoning remain unmeasured.

### design
`ui.design`, `ux.judgment`, `design.aesthetic_judgment`: visual-writing/judgment
editorial priors; not migration of lead approval authority. All four strict
scores remain **fail**: `#FFFFFF` was returned versus expected `#ffffff`.
Semantic-format caveat: the colors represent the same white, but the scorer was
not changed and no pass was retroactively granted. Tiny color/label output is
not an aesthetic, accessibility or usability evaluation. Task-specific review
is required; the strict-format counterevidence remains visible.

### media_generation
All three rows and their three local candidates are explicitly disabled, with empty
capability/modalities lists. Four harness cases were unsupported, not model
failures: no verified image-generation tool, image artifact or output route.
Text descriptions/SVG/code are not certified image generation. Actual image
output requests return NO_MATCH until a supported runner and evidence are added.

### tool_use
`tool.call` means textual structured-call proposal only. All four produced a
small proposed calculator call; no tool executed. `tools: []` deliberately makes
ANY required named execution tool fail closed. Do not omit `required_tools` to
route a real tool task: supply a task-specific table backed by the exact runner's
supported tool, permissions and observed execution. No arbitrary shell, browser,
repository, MCP or calculator support is inferred from model responses.

## Boundaries

Input text/image: observed Codex CLI 0.163.0 text and `--image` interface plus
actual text and PNG responses. Inventory observed local catalog text/image
metadata (cache client 0.166.0, different from CLI); metadata alone is not runtime
support. Code and structured_data are known textual representations in text
input/output, not separate execution engines. Output is text/code/structured_data;
no image/audio/video output is claimed. Image input does not imply image output.

`context_limit: 0` means no positive context capacity asserted: a numeric positive
requirement returns NO_MATCH, not an inferred advertised window. `constraints: []`
and `tools: []` assert no hard guarantees/runner integrations. All mandatory
input AND output, capabilities, tools, context, hard constraints, enabled and exact
pin filters apply identically to every local backup and the shared default. Exact pin mismatch never substitutes.
A default MATCH proposes an assignment; host/tool/authority checks and
independent output acceptance still apply. Price comparison is checked when
explicitly requested. No launch retry behavior changes.

## Observed pilot receipt (2026-11-07)

44 exec starts: four pre-service configuration errors, four successful canaries,
and 36 family responses. Ten families × four requested candidates: 32 pass,
four strict fail (design), four unsupported (media). Forty actual responses
including canaries; one easy synthetic fixture per family at requested medium
effort. These are smoke tests, not 30 difficulty-cell evaluations. Earlier blocked
evaluation notes are superseded by this completed pilot, not used as current results.

Returned event streams each showed one completed turn and no tool-call events;
actual backend identity/effort, internal retry count, strong host isolation,
subscription entitlement/billing/quota remain unknown. Existing MCP initialization
errors were present despite ignore-user-config. CLI wall time is not provider
inference time. No additional model calls were used to configure this table.

### Receipt hashes

SHA-256 of original retained pilot artifacts (paths are relative to the private
pilot evidence bundle; hashes are integrity references, not public raw logs):
- `verification.json`: `a10c1bc121093577d44ffe73b01a968ff6c829d6261f0c3de75e45d6e68881d8`
- `results-live/summary.json`: `c73851e9af24afb4ea4209243b4ce3a56fb0dba551e28cb033ebedf5d888c42e`
- `pilot.md`: `db2eb05e08e5655a1023e5a36d5cfa36ffee60a3bf6402dd77072e4aaedef87e`
- Fixed scorer SHA-256: `87b8f9e85ea43ec98125438b106099bceecfccbd1cb7f9e3692af142d6c891ea`

Source snapshot hashes:
- `policies/model-profile-registry.json`: `86b453d9be94b7692bac75363ae395e74d832f3da3e946a817f8c4e799cb60f6`
- `skills/company-orchestration/assets/model-choice-priors.json`: `5c40a83bb02b9988556a08d6491bce42e51833fdc3d25713dfa4845771ed55aa`

## November refresh

The November 19 table supersedes the older order above. The pilot informed retention of Terra for bounded tasks and the unsupported media boundary. Its scores do not transfer to the new models. Sol and Astra successors fill their respective broad and demanding roles based on [OpenAI's published comparison](https://openai.com/index/introducing-gpt-6-2-astra-sol/). For hard code, [DeepMind's FrontierCode 2.0 comparison](https://deepmind.google/models/gemini/) reports Neon 46.2% and Sol 43.8%. This motivates trying Neon first, without predicting a margin at the routed effort. Argon is an alternative for synthesis and data work based on the document-analysis evidence on the same page. For bounded language and tool tasks the [Hydrogen release evaluation](https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-4-hydrogen/) supports considering Hydrogen before its Flash predecessor. Tool access still requires runner evidence. Exact AGY IDs include the effort suffix. Provider evaluations inform editorial ordering; backend identity and local task quality require separate observations.

## Benchmark update

2026-11-19. For hard structured data and research, try Astra before Sol. OpenAI reports 62.5% five-attempt consistency on AA-AnalystAgent spreadsheet/report questions and leading results on Terminal-Bench-Science. Mapping those tasks to data transformation and evidence synthesis is an editorial inference. For hard code retain Neon first and Astra second, and give Sol the third slot. DeepMind reports FrontierCode 2.0 at 46.2% for Neon and 43.8% for Sol, and Terminal-Bench 4.1 at 65.2% and 61.5%. OpenAI reports Sol within 0.5 points of Astra on FrontierCode at max. Neither publication establishes this three-way order at Company high effort. The four-model local interval-repair exercise tied on all eight function checks in both repetitions. Its difficulty and trace coverage do not establish a winner for hard code. Other rows retain their prior ordering pending comparable task-specific evidence.

Sources: [OpenAI release evaluation](https://openai.com/index/introducing-gpt-6-2-astra-sol/) and [DeepMind benchmark table](https://deepmind.google/models/gemini/).

## API cost proxy

Use published USD per benchmark task as the cost proxy alongside task-specific performance. The 2026-11-19 Artificial Analysis comparisons report High effort Sol $0.56, Astra $2.07 and Neon $3.74 per task. For hard coding try Sol, Astra, then Neon. Sol's FrontierCode score is close to Astra at max, while Neon retains a different subscription route and stronger reported coding results than Sol on some tasks. These are static proposal priorities; subscription debit and per-success cost remain unknown. Sources: [Astra / Sol](https://artificialanalysis.ai/models/comparisons/gpt-6-2-astra-vs-gpt-6-2-sol), [Neon / Sol](https://artificialanalysis.ai/models/comparisons/gemini-4-neon-vs-gpt-6-2-sol).

## All-family cost policy

This order supersedes earlier orders for all 30 cells. Use AA's published cost per benchmark task (USD), not the token price column. Low/medium/high observations are Terra 0.0713/0.17/0.26, Sol 0.18/0.41/0.56, Astra 0.66/1.62/2.07, Hydrogen 0.29/0.80/1.87 and Neon 0.75/1.90/3.74. Argon medium/high are 4.31/4.97. Sources: [Terra and Argon](https://artificialanalysis.ai/models/comparisons/gpt-6-1-terra-vs-gemini-4-argon), [Hydrogen](https://artificialanalysis.ai/models/comparisons/gemini-4-hydrogen-vs-gpt-oss-120b) and the Astra/Sol and Neon/Sol comparisons above. These are editorial cost proxies, not family-specific expected bills.

Compare both subscriptions in every supported row using the same task-fit and benchmark-cost criteria. The proposal uses explicit candidate priority and preserves table order on ties. For general, language and bounded implementation tasks Terra's cost favors it. For hard reasoning, code and design, Sol's cost favors it. Design evidence is indirect. Hard research and structured data favor Astra's analytical results, with Argon available for document synthesis. For medium and hard tool use, Hydrogen's published automation results justify its higher proxy cost. For hard visual interpretation, Neon's multimodal results justify trying it before Sol. These are task-family judgments. Effort-matched local evidence is incomplete, and chart reading alone may favor Sol. See the [Hydrogen evaluation](https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-4-hydrogen/) and [DeepMind model comparisons](https://deepmind.google/models/gemini/). Media generation requires a verified output path. The shared last-resort Terra/medium carries the same $0.17 reference and still requires eligibility.

For tool use, AA AutomationBench-AA at medium shows Hydrogen 72.0% and Sol 70.3%. At high it shows Hydrogen 74.4%, Sol 69.9%, Astra 76.0% and Neon 79.2%. Hydrogen sits between Sol and the more expensive high-scoring models. Zapier's stricter task pass rate at high shows Hydrogen 51.1% and Sol 41.2%. For visual work, DeepMind reports Neon ahead of Sol on MKA and LVBench, while Sol leads Chartography 75.1% to 73.5%. The hard visual order represents a broad multimodal prior with limited evidence at matching effort. [AA Hydrogen and Sol](https://artificialanalysis.ai/models/comparisons/gpt-6-2-sol-vs-gemini-4-hydrogen), [Zapier comparison](https://zapier.com/benchmarks/gemini-neon-4-report), [DeepMind model evaluation](https://storage.googleapis.com/deepmind-media/gemini/gemini_4_neon_model_evaluation.pdf).
