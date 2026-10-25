# Shared policy synchronization and task-start checks

The user authorizes approved Company/common global-guidance changes to propagate
between their connected Macs, regardless of the originating Mac. The changing
lead owns publication, connected-peer reconciliation and receipts. This includes
changes made in another project. Existing authorization needs no repeated prompt.
New spending, public disclosure or consequential scope changes retain user control.

## At a new task and after a policy change

1. Once before substantive work, collect a local version snapshot using
   [policy version tool](../scripts/policy_version.py) and list the connected Orca
   hosts. Reuse that observation during the same task; refresh for a meaningful
   policy/runtime/host change. Do not scan histories or whole disks.
2. Ask each participating/connected peer for the same small snapshot using its
   actual execution host. Compare common global-guidance hash, Company source
   content fingerprint, actual bound policy hash/revision and actual host identity.
   A commit, timestamp or role name alone is not policy equivalence. Existing
   independent user Core installations are preserved, not queried as a Company gate.
3. Reconcile approved drift before affected work. The change origin publishes a
   pinned source/change and its verification evidence. Read both sides and their
   last shared base; no last-writer-wins or unconditional overwrite. Divergent
   edits require a scoped merge and explicit resolution of consequential choices.
   Preserve backups and use compare-and-swap on observed destination hashes.
4. Global guidance travels privately through connected authorized hosts. Do not
   put personal global instructions in a public Company repository. Preserve any
   marked `Host Local Guidance` block; synchronize the common portion. Runtime
   history, credentials, ports, device UDIDs, source paths and model defaults are
   not common policy. Other providers receive a self-contained brief; file
   synchronization alone does not prove they loaded new instructions.
5. Company updates use a clean, persistent owned source and the existing official
   transactional installer with Company-owned source/installed identity. Keep local
   runtime settings, unrelated user installations and rollback generations. The
   standalone Company candidate must not need per-host Core lock commits, Core
   identity files or an adjacent Core checkout. Do not edit managed installed
   skills/TOML or bypass compatibility/integrity checks. Do not move a checkout
   another writer owns. Reuse existing deployment workspaces when safe.
6. Re-read destination files and versions, check affected source/record cases,
   installed invocation, Doctor/sync status, and capture applied/deferred/conflict
   receipts per host. Start affected workers only with the confirmed version in
   their brief. Running tasks retain their pinned version until a natural task
   boundary; don't rewrite live Dispatch authority or assume hot reload.
7. Offline/unverifiable peers remain pending. Keep their last observed hashes and
   pending change reference. Retry at the next task start/reconnect checkpoint;
   don't claim all hosts synchronized. Independent work may continue while a
   conflicting or unavailable policy-dependent path stays pending.

Invoke the same procedure immediately after completing an approved change to
Company source or common global guidance. A task-start change discovered on a
peer is a change-origin handoff, not authority to silently override local work.
Keep one source owner and integration owner per change, not competing publishers.

```sh
python3 /path/to/company-orchestration/scripts/policy_version.py snapshot --codex-home /path/to/.codex
python3 /path/to/company-orchestration/scripts/policy_version.py compare local.json peer.json
```

Snapshots and backups belong under `${SEJONG_HOME:-${CODEX_HOME:-~/.codex}/sejong}`.
The tool reads/hashes and compares; it does not launch agents, transfer files,
pull Git, install, resolve conflicts or create a background watcher. The agent
executes synchronization at task-start/change-completion checkpoints using
supported Orca operations. Existing daily updater applies approved local source;
it is not an upstream Git auto-pull. A task without an agent/host invocation is
not silently covered by this instruction-based workflow.

## Private research records

Reusable research records live under `knowledge/research` on the same record
home as [run_completion.py](../scripts/run_completion.py): `SEJONG_HOME` when
set, otherwise the canonical Company install when Orca shares it, otherwise
`CODEX_HOME/sejong`. They are private knowledge, durable across runs, and
neither Company source nor common global guidance. Do not publish personal
source evidence into the public Company repository. The
[research cache](research-cache.md) stores incremental records with an owner,
revision, and content hash. A private record may name an authorized local
artifact; that path stays in the private root.

At this same checkpoint, a host that should carry a record receives an explicit
private copy. Compare the destination id, revision, and content hash. Equal
hashes are already seeded. A newer or divergent peer finding stays in place;
write the rejected copy beside it and leave both visible. Do not overwrite it.
Offline peers stay pending with their last observed record hashes. Git or a
private GitHub repository is an optional transport only when that publication
boundary already exists. This section adds no daemon, network sync tool, or
second reconciliation framework. The policy-version snapshot does not hash
these private records; a commit or timestamp is not their equivalence either.
