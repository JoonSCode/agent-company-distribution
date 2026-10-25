# Source baseline and selective updates

The package owns active Company policy. `upstream/baseline.json` records the
reviewed Orca skill tree, runtime document bytes, selected capability scopes,
adoption reasons and hashes of active local policy. Upstream snapshots are
comparison inputs, not extra runtime authority. Dated model evidence is a
starting prior; actual support/authentication is observed per execution route.

All paths below are relative to this skill folder. The scripts use stdlib Python;
use Python 3.13 in the repository or a compatible available interpreter. They
work from a copy of the package without a global skill installation.

The package includes the [contract checker](../scripts/orca_contract.py),
[record checker](../scripts/record_check.py) and
[synthetic record cases](../assets/record-cases.json).

```text
python3 scripts/orca_contract.py check --json
python3 scripts/orca_contract.py observe --orca orca --output <new-observation-directory> --json
python3 scripts/orca_contract.py compare --observation <observation-directory> --scope launch_preferences --json
```

For another platform/dev/managed host use the already resolved Orca executable.
Keep observations outside the source package and don't overwrite old evidence.
The package option selects an isolated copy when needed. Observe only reads
status and known guide commands; it never opens, restarts, updates, launches or
stops a process. Compare does not accept a new baseline or change local policy.

| Result | Meaning and next action |
|---|---|
| valid / observed | Package bindings checked / read-only commands collected; neither implies acceptance or working provider behavior. |
| baseline_match | Required selected support and document identity match; reuse the observation. This is not a runtime behavior certification. |
| formatting_only | Only narrowly defined harmless formatting changed; inspect the reported scope and retain original hashes. |
| review_required | Read the changed relevant section or missing capability, decide how it affects the intended operation, and verify a bounded change. |
| unverifiable | Necessary runtime evidence is unavailable; preserve uncertainty and continue work not needing that execution path. |
| invalid | Malformed/tampered records, unsafe paths or broken source bindings; correct the specific input/package before using its claim. |

Exit codes are 0 for valid/observed/match/formatting-only, 1 for review-required, 2 for
unverifiable, 3 for invalid. A version change alone does not imply a semantic
contract break; unknown extra capabilities are not newly tested support. Missing
capability checks apply to the selected operation scope, not every possible
Company activity. Observation errors must never turn into guessed process death.

## Review only meaningful changes

The observation tool compares the installed runtime's guide contract. It does not
poll GitHub for a newer discovery stub or refresh model benchmarks. When an
upstream skill change is announced or otherwise relevant, obtain that published
source from the baseline's source URL into a separate candidate directory and
compare it with `upstream/discovery-stub.md`. This needs no installed global skill
file. Review that source change alongside any runtime differences before adopting
it; a successful runtime comparison alone says nothing about uninspected upstream
commits or benchmark freshness.

1. At a new run or relevant host/build update, collect a small observation; reuse
   valid evidence within that run. A new remote host gets its own observation.
   No per-message benchmark, full-guide model reading or background watcher.
2. Compare old upstream, new upstream and local policy. Use hashes, schema and
   diffs mechanically; ask AI about meaning, conflicts and decisions, not whether
   two byte strings match. Preserve code indentation and other meaningful syntax.
3. Record adopt, adapt, defer or irrelevant with a reason. Operational advice is
   selective; actual host command/authority/settlement requirements must be met
   before the affected action. Continue unrelated approved work.
4. Prepare the smallest patch, keep local model/authority/context decisions, and
   run affected deterministic and synthetic checks. For a changed execution
   claim, add a bounded real-host check. Static success cannot replace it.
5. Update the accepted source snapshots, policy revision/bindings and adoption
   record only after reviewing that candidate. Keep the old baseline in version
   history. Do not auto-merge source updates or install over global skills.

Routine internal maintenance within approved scope can proceed autonomously.
Changes to goals, material experience/maintenance/learning, authority, additional
spending or publication need the user's concrete choice. Not every upstream
update needs approval. Running Dispatches keep their authority; an update never
settles, cancels or duplicates them. Restoring an old internal file is not proof
that it works with a newly updated host.

## Keep the package complete

When policy files change, refresh their hashes deliberately in baseline.json and
run check. Preserve the upstream hashes independently so an edited policy is not
misreported as exact upstream. Include required active references/scripts/assets
in policy_files; do not bind the manifest to itself or to volatile observations.
Copying the complete skill directory must preserve its usable context and tools.
Declare active file dependencies with simple inline Markdown links, as above.
Check requires the SKILL.md entry and follows these links in bound policy Markdown:
every local target must exist inside this package and have a source binding.
HTTP(S) evidence URLs are references and are not fetched. Hashes and dependency
checks establish consistency, not authenticated authorship or policy quality.

Global user preferences may remain for other projects. This package imports the
approved model/path/token/context rules as owned policy and does not read those
global files at execution time. Do not remove or rewrite other projects' guidance
as a side effect of Company maintenance.

Before claiming an improvement, distinguish source integrity, synthetic cases,
actual provider execution and outcome quality. Keep observed token coverage and
comparators; shorter instructions alone do not establish measured savings.
