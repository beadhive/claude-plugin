# Installation companions for refactor

Generated from the reviewed canonical skill-dependencies.json; this file survives skill-only copying.

The skills CLI installs only the requested directories. It does not resolve companions, install runtimes, configure MCP/hooks/agents/styles, or grant role authority.

## Required companions

None. This does not remove the runtime requirements below.

## Supporting reference companions

- [plugins](../plugins/SKILL.md): included supporting documents link to this sibling; this is reference completeness, not a claim every operation runs it.

## Conditional modes

- request: install `plan` when No claimed implementation bead; route request through planning.
- execution: install `developer`, `work` when A claimed implementation bead enters the execution protocol.

## External providers

- `bh integrations`: Optional Repowise analysis; repository-native tools/fallback remain available. Optional per-integration bh plugin capabilities; probe installed help and explicit authorization.

## Runtime and invocation scope

- Installed bh CLI for described lifecycle operations; host Skill/Task/AskUserQuestion semantics and seat authority remain external.

Neutral directory names; bh: and /bh: invocation prose and Task/Skill/AskUserQuestion examples are Claude-specific, not an Agent Plugins invocation/enforcement guarantee.

Preserve the included LICENSE notice. Installing companions does not prove live-client behavior or external-provider availability.
