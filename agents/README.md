# Agents

The six JSON files in this directory are the single source of truth for Agent
Company roles: founder, planning, marketing, design, development, and
qa-release. They validate against `policies/role-profile.schema.json` and keep
role mission, ownership, skills, tools, approval rules, and bounded handoff
wiring together.

The native-agent compiler generates exactly six prefixed TOML files named
`agent-company-<role>.toml`. Generated TOML is a derivative and must never be
edited independently. The managed installer records its digest and ownership;
it refuses an unmanaged destination collision.

The compiler preserves curated role methods, tools, memory references, and the
required bounded-handoff shape inside `developer_instructions`. Changing any
of those source fields must change the affected generated agent. They remain
instructional routes rather than native `skills.config` allowlist entries.

Sandbox defaults stay role-specific. Evidence-only roles are read-only;
development and qa-release may use workspace-write for their bounded work.
None of the six agents can select the Core route, approve Uigwe, award final
verification, or impersonate the CEO.

Read-only checks:

```bash
# docs-audit: execute expected-exit=0
python3 scripts/test_profiles.py
# docs-audit: execute expected-exit=0
python3 scripts/test_native_agents.py --case compile-six-deterministic
```
