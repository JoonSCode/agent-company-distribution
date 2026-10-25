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

Every generated role receives the same Outcome and Execution contract before
its Independent Judgment and role-local sections. It preserves the CEO's
portfolio purpose, intended outcome, requested quality, and deliverable;
accepts an incomplete thought as valid intake; and makes a finished brief the
result of grounded clarification rather than an entry requirement. Once
material user choices are settled, roles own reversible local design, method,
tool, and resource choices inside their authority.

The common contract also requires prior evidence to retain source, rationale,
counterevidence, scope, freshness, and supersession state. It distinguishes the
actual product or customer path from manual assistance, automated checks from
observed experience, publication from readback, and technical completion from
business outcome. Roles use the smallest evidence and resource set that
preserves quality. Company owns bounded allocation and acceptance policy; the
actual Orca host owns Task/Dispatch execution and permission boundaries. No
external Core is required by the active role instructions.

Every generated role also receives the same Independent Judgment contract.
Material CEO or user suggestions are decision inputs rather than predetermined
conclusions: roles inspect evidence and counterevidence, distinguish inference,
preference, constraint, and explicit decision, and recommend `adopt`, `modify`,
`defer`, or `reject`. The contract does not manufacture disagreement or delay
trivial exact low-risk instructions, and an explicit CEO decision remains
authoritative within higher-priority safety and permission boundaries. These
dispositions are advisory and do not replace role-local statuses or authority;
a settled decision is reopened only when material evidence crosses a named
safety, permission, approved-scope, or approved-risk boundary.

Sandbox defaults stay role-specific. Evidence-only roles are read-only;
development and qa-release may use workspace-write for their bounded work.
None of the six agents can override user material authority, host permissions
or an accepted assignment, self-award final verification, or impersonate the
overall Company head. Current handoffs use Company destinations; historical
surface labels remain readable metadata and do not invoke an external engine.

Read-only checks:

```bash
# docs-audit: execute expected-exit=0
python3 scripts/test_profiles.py
# docs-audit: execute expected-exit=0
python3 scripts/test_native_agents.py --case compile-six-deterministic
```
