# Agent Company

Agent Company is a Codex extension that installs six bounded company roles on
top of the exact King Sejong Core version it requires. King Sejong remains the
routing, execution, approval, receipt, and final-verification authority.

## Install

Prerequisites: macOS, Git, GitHub CLI (`gh`), `uv`, and Codex. The fixed v0.1.0
installer verifies the GitHub release attestation before cloning or executing
release source. It then installs and verifies the pinned King Sejong Core,
followed by Agent Company in persistent managed source checkouts.

```bash
curl -fsSL https://raw.githubusercontent.com/JoonSCode/agent-company-distribution/v0.1.0/install.sh | bash
```

Run the same command with `-s -- --dry-run` appended to inspect the plan without
creating managed source checkouts or changing Codex state. An existing
incompatible King Sejong installation blocks by default; use `--replace-core`
only when replacement is explicitly intended.

The public repository is a history-free runtime projection. Tests, evaluator
inputs, reports, and private memory are not distributed. Runtime memory and
Sejong receipts remain under the user's own Codex home.

## License

Agent Company is MIT licensed. See `THIRD_PARTY_NOTICES.md` for Ponytail
attribution.
