# Evidence acquisition

An operator habit for [routing](model-routing.md), [candidates](model-candidates.md)
and any other decision where evidence is thin. **Uncertainty produces the next
evidence action, not a final answer of "unknown".** This is a decision aid, not a
scheduler, daemon or required benchmark routine.

## Proportion first

1. Reuse adequate current sources (dated [model evidence](model-evidence.md), a
   [practitioner source ledger](practitioner-evidence.md), recent local observations). Refresh only when the result could change
   the decision.
2. Small settled exact work needs no survey: take the cheapest discriminating
   check (read the config, run a bounded probe, use a deterministic tool) and go on.
   The source minimum below applies only to a **broad multi-model or practitioner
   survey**, never to every small task.
3. Stopping is decided by decision coverage and credible limits, not an arbitrary
   count of sources or queries.

## Research cache before a new search

Keep the method-discovery rules in this file, including the seven-day review
checkpoint for reusable methods, tools, skills, and routing evidence. A passed
date is a targeted refresh checkpoint. It does not delete a record, does not
prove the source is still true, and is not a blanket TTL.

Small settled exact work still takes the cheapest discriminating check.
Do not survey the cache or the web for it. Reversibility alone is not enough: a
large or unfamiliar change searches the relevant cache before new research. `opening --task trivial` records
that choice. Other work searches the relevant cache subset before a new
external search, then reads only the matched records. The default root is
`knowledge/research` under the same record home as
[run_completion.py](../scripts/run_completion.py). Explicit `SEJONG_HOME` wins.
An Orca runtime uses the canonical Company installation's record home when this
package is that install, so the cache is not a second store. The root stays
outside runs and managed installs. Reuse a stable concept when the scope and
version still fit and a recorded checkpoint has not passed. Refresh only the
outdated or contradicted portion. A volatile fact stays visible, and its cached
date never counts as the required live check. Write back the compact finding
and, separately, the observed application result. Stale, contradicted, and
conflicted records remain and link their replacement. Held-out evaluation
cases stay outside this cache.

The installed `research-methods` skill is the shared procedure. Its researcher
profile is an on-demand specialist for curation, retrieval, refresh, and deeper
research, including when a domain owner is missing. It is not a standing agent
and not a gate every task must pass. Research cannot approve domain
implementation or independent QA. The [research cache contract](research-cache.md)
has the fields and commands. Private copies across connected Macs follow
[fleet policy](fleet-policy.md); there is no second sync tool.

## Seek better methods across the work

Each owner proactively looks for a better way to achieve the intended user
experience or business outcome. Apply this to every discipline and its relevant
subparts, not only the overall project or implementation. For an unfamiliar
field, map the important decisions, dependencies and competing values, then
research enough to make a grounded first choice. This is not a fixed department,
headcount or meeting requirement.

Compare improving the current method, another tool, a combination of skills,
suitable existing work or open source, and a small direct solution. Inspect
original research skills, prompts, professional methods and failure accounts;
adapt useful criteria rather than copying their tool assumptions, source quotas
or numeric bias. Keep the wanted experience, controllability, integration,
quality, rights, maintenance and actual resource constraints in the comparison.
Technical checks alone do not establish the intended experience.

Record the decision question, source and checked portion, observation date,
strongest counterevidence, choice, reason and condition that would change it.
Use a bounded practical trial when documents cannot resolve the choice. Carry
the accepted method into the owner's next action and compare its observed result
with the intended effect. Researchers supply compact reusable evidence; owners
read the relevant changes before work and record application or deferral in the
existing decision record. Do not keep researching once the next useful action is
clear, or let novelty reopen a settled user decision without material evidence.

Reviewed examples: [Anthropic's research-system engineering account](https://www.anthropic.com/engineering/multi-agent-research-system)
supports adaptive search, bounded delegation and claim/source review. Its
[public researcher prompt](https://github.com/anthropics/claude-agent-sdk-demos/blob/main/research-agent/research_agent/prompts/researcher.txt)
illustrates why fixed search counts and quantitative-output quotas should not be
copied into every task. Reviewed 2026-10-11; these examples do not prove local
quality or savings.

## Broad practitioner survey standard

- At least **10 distinct, substantive, original firsthand accounts**, each with the
  original URL and publication date. Prefer sources that describe the task, model,
  native effort/setting, tools and outcome.
- Label what each source actually supports: **operational configuration** (what
  they demonstrably set up), **firsthand experience** (reported use, failures and
  rework), and/or **measured result** (numbers with method). A suggested template
  alone is not firsthand use. A configuration plus experience is still one
  practitioner; neither proves comparative efficiency without measurement.
- Exclude the same author counted twice, duplicates/reposts/aggregators of one
  account, and promotional-only recommendations (vendor, affiliate or launch
  material without a described use). Vendor documents may still prove published
  capabilities, billing and settings, but not field quality.
- Build a **coverage map** of questions/tasks (see the task table in
  [model-candidates](model-candidates.md)) against sources. Deliberately seek
  contradictory and negative examples for each leading candidate.
- If ten qualifying accounts remain ambiguous or leave task cells empty, **broaden
  sources and queries** (other communities, languages, issue trackers, changelogs)
  before concluding. Ten is a floor for a broad survey, not proof of sufficiency.
- Prefer reputable primary benchmarks keyed by **task and effort setting**; treat a
  score without its effort, tool and scoring conditions as weak.

## When documents cannot resolve it

- Inspect the actual configuration, model catalog, effort selectors and readback of
  the real route instead of trusting a label.
- Run a **bounded, authorized local probe** inside the existing scope: reversible,
  small, with acceptance and a stop condition. Never use hidden API payments,
  paid overage, new logins or purchases to obtain evidence; stop on quota or
  authentication failure and report it.
- Be proactive: take the next available, discriminating reversible research or
  probe step before reporting insufficiency. Continue while it can materially
  change the decision within task limits; do not perform an unbounded search.

## Delegated collection

A delegated collector returns sources, classification and limits. The lead reviews
and integrates the collection and spot-checks original URLs and dates rather than
repeating the whole search. Specify a compact structured output and source refs
in the brief; do not duplicate a full report in prose, JSON and handoff messages.
Keep original evidence available without pushing all of it into the lead context.
Keep the collector independent of the decision it
informs; do not feed the preferred answer into a first judgment.

## Honest gaps

For each unresolved gap record: **action already taken**, **why it remains
unresolved**, **next owner**, and **reentry condition** (what new model, setting,
quota/path, benchmark or observed failure would reopen it). Keep it visible; do not
turn it into a conclusion. A bounded provisional choice with acceptance and stop
conditions can proceed while the gap is open.

## Public record and refresh

Public records hold generic evidence, dates, the strongest counterargument, the
choice and its reversal criteria. They hold no private quota values, accounts,
product details or transcripts; those stay in private run evidence.

Refresh evidence at a meaningful task boundary and whenever a model, native
setting, quota/path, benchmark or observed failure changes. Record a **next review
date** (7 days by default for reusable methods, tools, skills and routing evidence;
earlier on a material change or failure). Before relevant reuse after that date,
check the original source, support/settings, rights, cost, integration and new
failure evidence. If nothing material changed, record that check and update its
date; repeat a full survey or benchmark only when it can change a current choice.

This date is a reuse checkpoint, not an automatic timer or authority to create a
scheduler. Separately requested recurring research uses an explicitly scoped
schedule, current priority questions and owned outputs. It does not resurvey every
field each run, automatically adopt product changes, or expand spending,
installation, publication or access authority. Keep research, application,
observed effect and any unverified automation steps distinct.
