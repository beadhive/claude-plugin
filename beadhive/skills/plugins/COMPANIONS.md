# Installation companions for plugins

Generated from the reviewed canonical skill-dependencies.json; this file survives skill-only copying.

The skills CLI installs only the requested directories. It does not resolve companions, install runtimes, configure MCP/hooks/agents/styles, or grant role authority.

## Required companions

None. This does not remove the runtime requirements below.

## Supporting reference companions

- [control](../control/SKILL.md): included supporting documents link to this sibling; this is reference completeness, not a claim every operation runs it.
- [refactor](../refactor/SKILL.md): included supporting documents link to this sibling; this is reference completeness, not a claim every operation runs it.
- [setup](../setup/SKILL.md): included supporting documents link to this sibling; this is reference completeness, not a claim every operation runs it.
- [setup-git-workspace](../setup-git-workspace/SKILL.md): included supporting documents link to this sibling; this is reference completeness, not a claim every operation runs it.

## Conditional modes

No additional internal skill modes declared.

## External providers

- `bh integrations`: Operating a particular integration; no automatic installation. Optional per-integration bh plugin capabilities; probe installed help and explicit authorization.

## Runtime and invocation scope

- Installed bh CLI for described lifecycle operations; host Skill/Task/AskUserQuestion semantics and seat authority remain external.

Neutral directory names; bh: and /bh: invocation prose and Task/Skill/AskUserQuestion examples are Claude-specific, not an Agent Plugins invocation/enforcement guarantee.

Preserve the included LICENSE notice. Installing companions does not prove live-client behavior or external-provider availability.
