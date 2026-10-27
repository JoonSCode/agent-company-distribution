# Conditional prepared-shell workflow

Use this only when the selected execution host has observed a shell-startup
question or lost agent command before `agent_readiness`. A startup `read -k1`
can consume the `c` in `codex`, leaving `odex: command not found` before any model
turn. A failed real trial stays failed; readiness work is not a retry or a model
oracle failure. Keep original Task/Dispatch/raw evidence and inspect the exact
recovery receipt before replacing anything.

The current macOS/Linux `terminal create --command` types the command into the
host login shell. Its `--shell` override is Windows-only. `worker-start` has no
per-launch shell/surface selector. A promptless `agent launch --surface chat`
can return a structured chat, but this runtime rejected its adoption by
`worker-start --terminal` as `terminal_handle_stale`. Do not fabricate a supported
structured-adoption route, change global defaults or try another writer on an
unknown result. These are host limitations, not external Orca fixes in Company.

## Prepare before agent-command delivery

The accepted operator owns one blank terminal in the exact worktree. No other
writer may use it during preparation. Run current host help first if its contract
differs. All JSON paths below are new small private evidence files, not installed
package files. The [readiness checker](../scripts/launch_readiness.py) is a stdlib
read-only checker/nonce producer. It sends no input, launches no process, creates
no Task/Dispatch and changes no settings. Use Python 3.13+ with `-B`.

1. Create the blank shell with `ORCA terminal create --worktree <exact> --json`.
   Pass no `--command`, agent or task brief. Save the original receipt and exact
   returned terminal handle. Capture `terminal show` and `terminal read --screen`
   for that handle. Inspect the actual shell prompt and ownership.
2. If the exact known question `[oh-my-zsh] Would you like to update? [Y/n]`
   appears, block all command delivery. An operator may explicitly decline that
   exact question within the accepted scope, recording the answer and any cache
   change before freezing a new study. The checker never answers it. Unknown
   startup, trust, permission, account or password prompts remain blocked and
   require their actual owner; never send a harmless command to answer them.
   Capture fresh show/screen after any explicit resolution.
3. Prepare the challenge using the exact observed final shell-prompt line:

```text
uv run --no-project --python 3.13 python -B scripts/launch_readiness.py prepare \
  --show before-show.json --read before-screen.json \
  --terminal <exact-handle> --worktree <exact-absolute-path> --prompt '<exact-shell-prompt>'
```

Save stdout as `challenge.json`; proceed only on exit 0 and
`challenge_prepared`. The checker requires a connected, writable, unclaimed shell,
the actual rendered screen, an exact prompt and a recent observation. A Git prompt's
`?1` count is not a question. Ambiguous/unknown frames block rather than receive input.

4. Send the generated fixed `printf` command **once** to that same terminal through
   supported `terminal send --text <challenge.command> --enter`. Use proper shell
   quoting or a structured command argument; never reconstruct or interpolate a
   user-supplied command. The marker is split across arguments so command echo alone
   cannot prove execution. Record the send receipt. `input_accepted` alone is not proof.
5. Read incremental output with `terminal read --cursor <challenge.before_cursor>`
   and capture a fresh `terminal show`. Verify within 60 seconds:

```text
uv run --no-project --python 3.13 python -B scripts/launch_readiness.py verify \
  --challenge challenge.json --show after-show.json --read after-stream.json
```

`saved_shell_proof_validated` means those supplied snapshots contain one standalone
executed nonce in an advancing complete stream, the same runtime/terminal/PTY/
incarnation/worktree, and fresh ordered times. Echo-only, missing/wrong/duplicate
nonce, changed handle, stale proof, incomplete stream, question or unknown state
blocks. Incarnation and time come from `terminal show`; read receipts need not
contain them. Never fabricate missing host fields. The checker validates captured
assertions; it does not authenticate a current process. Archived proof cannot
authorize input to a closed/replaced terminal.

6. Immediately recheck that the same owned terminal remains live and unused.
   Only then send one recognized agent's supported promptless launch command in
   that terminal, with the approved process-local model/effort. Verify actual TUI
   readiness, agent identity and settings using current host/provider readback.
   No task brief is sent until readiness is established. Use the supported
   `worker-start --task <id> --worktree <exact> --terminal <same-handle>` to take
   supervised ownership. Its terminal path cannot combine `--model`/`--effort`;
   preparation must preserve requested versus observed settings separately.

Do not replace this with `dispatch --inject`, which leaves the process
unsupervised. No blind retry: stop and inspect the original exact response and
residual resources on unknown send/start/adoption results. The operator owns
prepared-terminal closeout if adoption is unavailable, and supervised lifecycle
rules apply after adoption. This workflow has no launch interceptor or scheduler;
operators must follow its command-delivery boundary on the affected host.

## Evidence limits and focused verification

Controlled PTY fixtures use a task-owned temporary ZDOTDIR and fake agent, with
no user rc changes or model/network call. They reproduce the old `c` loss, block
all command delivery while the known question is active, and permit the fake
agent only after a fresh executed proof. Run
[the focused tests](../scripts/test_launch_readiness.py). Actual blank-shell nonce
evidence establishes only that shell round trip. It does not prove real agent
readiness, provider behavior, full supervised adoption or that Orca's startup
race was repaired. Keep those actual host checks and independent review separate.
