# Knowledge Map

Use this map to load the smallest reference set that can change the live
decision. Do not load the entire corpus for every copy request.

## Routing

| Question | Primary reference | Add when needed |
| --- | --- | --- |
| Is the brief ready for copy? | `copy-brief.schema.json` | `foundations.md` |
| What should this interface say? | `ux-writing.md` | `surface-playbooks.md` |
| What should this paywall, store page, ad, landing page, or email say? | `conversion-copy.md` | `surface-playbooks.md` |
| What should the brand sound like? | `voice-localization.md` | `foundations.md` |
| Is this copy truthful, usable, and ready? | `evaluation-rubric.json` | matching mode reference |
| Does a new method improve the skill? | `evaluation-cases.json` | `evaluation-rubric.json` |
| Is this guidance current? | `trends-and-refresh.md` | `source-catalog.md` |

## Boundary Questions

Route to Marketing when any answer is unsettled:

- Who is the reachable target?
- What alternative is the product replacing?
- What is the positioning or offer?
- Which outcome and channel job matter?
- Which promise is supported?

Route to Design when any answer is unsettled:

- What state is the product in?
- What is the user trying to do now?
- Which action is available and what happens next?
- Is the information hierarchy or control semantic correct?
- How does the flow recover from error, interruption, denial, or offline use?

Use this skill when those decisions are settled and the remaining work is
expression, critique, consistency, localization, or matching-surface quality.

## Evidence Priority

1. Product behavior and matching-surface evidence
2. User language and behavior evidence
3. Approved positioning, voice, and terminology
4. Platform, accessibility, policy, and legal constraints
5. Stable craft methods
6. Trends

If two sources conflict, follow the higher-priority evidence and record the
conflict. If sources at the same level conflict, keep the decision conditional
or return it to the requesting owner.

## Reference Maintenance

- Put procedures and routing in `SKILL.md`.
- Put durable principles in `foundations.md`.
- Put surface-specific craft in the mode references.
- Put source provenance and review metadata in `source-catalog.md`.
- Put changing assumptions in `trends-and-refresh.md`.
- Put machine-checkable quality thresholds in JSON.

Do not copy full external guides into this package. Store the source, a bounded
operational rule, the allowed use, and the recheck trigger.
