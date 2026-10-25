# Research cache

Private reusable research knowledge for every Company discipline. This is not
an evaluation set, a provider prompt cache, or a memory-record mutation. The
tool is [research_cache.py](../scripts/research_cache.py). It uses the Python
standard library and does not open a network connection, start a shell, run a
daemon, or delete records.

This same store now supports classified v2 knowledge records and explicit local
Git wrapping; see [one private knowledge repository](knowledge-repository.md)
for reviewed imports, privacy/size boundaries, actual use and Git ownership.
Research is one record kind alongside lessons, corrections, failures, insights
and references. Existing v1 records/default callers require no migration rewrite.

The default root is `knowledge/research` under the record home from
[run_completion.py](../scripts/run_completion.py) `default_home()`. Explicit
`SEJONG_HOME` wins. When this package is the canonical Company install and the
caller is the standard Orca runtime home or a shared skills link, that
install's `sejong` is the record home. A standalone package uses
`CODEX_HOME/sejong`. Do not open a second cache from the terminal home alone.
The root sits outside runs and managed installs. Pass `--root` for a private
staging copy. Generic policy stays in this package. User-specific records stay
under the private root and are not committed to the public Company repository.

## What a record holds

Each current record is one Markdown file plus the same fields in JSON. The
small `index.json` is the only file search reads. A useful note needs an id,
`stable_concept` or `volatile_fact`, a topic, a compact synthesis, one
provenance ref, the checked date, and the scope it applies to. Provenance may
be an `https` URL, a `run-artifact:` id, or an explicit local artifact path
already held by the owner. A relative path is not explicit provenance. Problem,
query, version, uncertainty, counterevidence, disposition, observed use, and
owner are written when they are known.

`stable_concept` may be reused while its scope still fits. A review date, when
recorded, is a checkpoint and not a deletion. `volatile_fact` remains stored.
`live_check_required` stays true, and an omitted review date defaults to seven
days after `checked_on`: a cached date never makes that fact current. The same
seven-day checkpoint is the default for volatile method, tool, skill, and
routing evidence. A later date refreshes the outdated portion only. A timestamp
alone is not source truth.

Search returns the matching index rows, not the archive. Read one record with
`get`. Held-out evaluation cases stay outside this cache. Do not put them here.

## Commands

`init` creates the private root. `put` inserts a new id and refuses a second
write of the same id. `update` and `use` require the current content hash.
The stored `content_sha256` binds semantic fields, revision, status, and replacement
links. A replacement changes that token even when its old evidence is unchanged.
Ordinary `update` and `use` reject stale or contradicted records, including when
the caller supplies their latest token. A mismatched hash leaves the current record and writes the rejected body under
`conflicts/<id>/`. `replace` links a new record and marks the old one `stale`
or `contradicted`; both stay readable. `search` and `digest` read the index.
`assess` decides reuse, scope mismatch, partial refresh, or a required live
check for one record. `opening --task trivial` skips the cache and the web only for small settled exact
work. Reversibility alone does not qualify.
`opening --task consequential` searches the relevant subset first.

Initialization and writers share the exclusive lock. Before a mutation, the tool
validates the index and existing JSON/Markdown record integrity and their index
bindings. Malformed JSON or structure returns a structured error before record
changes. Searches still read only the small index. Each file write is atomic,
but a crash or I/O failure between multiple file writes can leave a mismatch;
subsequent writes refuse that mismatch. This is not multi-file crash recovery.

There is no delete command and no semantic-search service. Rank is token
overlap over the index fields, with the id as a deterministic tie-break.

## Across connected Macs

Records are durable across runs. Propagate them only as private incremental
copies at the existing [fleet checkpoint](fleet-policy.md). Compare the
destination id, revision, and content hash. Do not overwrite a newer or
divergent peer finding; keep both and leave the conflict visible. Git or
GitHub is an optional private transport when that publication boundary already
exists. It is not required, and it is not a reason to put personal source
evidence in the public Company repository. No sync daemon is part of this cache.
