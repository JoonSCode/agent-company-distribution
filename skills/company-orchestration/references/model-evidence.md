# Model evidence and freshness

Use [model routing](model-routing.md) and [task candidates](model-candidates.md)
for the active decision process. Model choice comes from resolved configuration,
current-task authority and actual host support. This package supplies no personal
model choice, provider order, exclusion or effort floor.

## Evidence to collect

Prefer task-matched benchmarks and reuse comparable accepted local results when
available; do not require a new local A/B before every cheaper starting choice. Record source URL, publication/observation date, model and native effort,
task/harness, sample coverage, quality measure, token categories and uncertainty.
[Official model-selection guidance](https://developers.openai.com/api/docs/guides/model-selection)
is a method reference, not proof of a particular subscription route or account.
[Artificial Analysis](https://artificialanalysis.ai/) and
[Bug Hunt data](https://bughunt.productcompass.pm/data/benchmark.json) are potential
comparison sources; inspect their current methods and coverage before use.
The [source table](../assets/model-choice-priors.json), checked 2026-10-27,
separates directly inspected official API rates/qualitative capability guidance
from user-provided accessible-chart transcription of ALE v1 scores and $/task.
The latter is not independently retrieved chart data; confidence intervals were
not supplied. Similar point scores are not statistical equivalence. No effort-
specific score is inferred from a model-wide ranking. These priors guide an
initial task-fit choice, not a permanent ranking or entitlement check.

Rates are USD per million tokens for Standard/global with 30-minute cache writes;
other tiers, regions or retention need their own verified basis. The helper applies
the documented >272K full-request input multipliers. Refresh dated rates and
capability priors when their scope or freshness could change the choice.

API prices, actual subscription charges/credits, quota and latency are different
units. Optimize task-fit whole-work price rather than raw-token count. Include
instruction/feedback/failure/retry/review/integration costs, but never multiply
benchmark $/task into an unrelated workload estimate. An estimate or prior is not
actual usage or measured savings. Unknown coverage/cost stays unknown. Verify actual model/effort, tools, authentication
and billing on the execution route before launch; public catalog availability
is not account entitlement.

Keep account observations, personal preferences and detailed run evidence in the
private knowledge repository. Retrieve only authorized applicable records and
assess their provenance and freshness; absence is not permission to reconstruct
someone else's preferences. Refresh evidence when the model, task, harness,
route, billing or a regression could change the decision.
