# The no-model Company demo

This is a **synthetic example**, not a capture of real people, models, Tasks or
Dispatches. It is rendered by the same `status_tui.py` used for actual Company
records. The record checker, pinned-source loader, task cards, dependency layout,
keyboard navigation and terminal restoration are real code paths.

From the distribution root:

```sh
uv run --no-project --python 3.13 python scripts/agent_company_demo.py --once
uv run --no-project --python 3.13 python scripts/agent_company_demo.py
```

The first command checks the bundled files and prints a frame. The second stays
in your terminal: `j`/`k` select, `x` focuses, `w` returns to the wide map,
`o`/`f`/`c` switch organization/flow/combined views, `n`/`p` change pages and
`q` exits. A non-interactive shell needs `--once`. No credentials, Orca connection,
provider calls, worker launches, configuration changes or installation are needed.
If Python 3.13 is not available, uv may download it; prepare it separately for
fully offline execution. With an existing Python 3.13 interpreter you can run
`python3 scripts/agent_company_demo.py --once` without uv.

The default is the shipped English ASCII presentation, which works on light and
dark terminals without color. `--unicode --palette dark` uses the original
Unicode/Korean labels with the explicitly selected dark palette. It does not
change your terminal theme or font. Width and height overrides require `--once`:

```sh
uv run --no-project --python 3.13 python scripts/agent_company_demo.py --once --width 120 --height 40
uv run --no-project --python 3.13 python scripts/agent_company_demo.py --once --width 40 --height 20 --layout focus
```

## What the picture means

- `demo-planner`, `demo-builder` and `demo-reviewer` are illustrative exact model
  IDs, **not provider model names** or proof of model execution.
- `Task review passed` is a consistent synthetic record state. The overall goal
  remains pending, user confirmation is unobserved, and specialist evidence is
  unknown. Passing task records do not approve the overall goal.
- Team membership, planned dependencies, assignments and observed execution are
  different relations. The source declares partial dependency coverage. No live
  staffing or concurrent execution is observed.
- `view.json` pins the SHA-256 of the adjacent `record.json`, `claims.json` and
  `plan.json`. Changing those files without repinning is rejected. These hashes
  prove byte consistency, not host origin or human consent.
- The resident viewer refreshes its supplied inputs; these bundled inputs are
  static. The demo does not fabricate a progression or run a simulation worker.

For actual records and input requirements, use the
[status TUI guide](../../references/status-tui.md). `--json --once` prints the
validated read model, including local resolved paths: redact those before
sharing. Never publish real records just because the synthetic demo is safe.
