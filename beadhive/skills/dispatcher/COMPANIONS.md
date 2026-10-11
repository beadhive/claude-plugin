# Installation companions for dispatcher

Generated from the reviewed canonical skill-dependencies.json; this file survives skill-only copying.

The skills CLI installs only the requested directories. It does not resolve companions, install runtimes, configure MCP/hooks/agents/styles, or grant role authority.

## Required companions

- [developer](../developer/SKILL.md)
- [operator-communication](../operator-communication/SKILL.md)
- [plugins](../plugins/SKILL.md)
- [work](../work/SKILL.md)

## Supporting reference companions

None beyond required companions.

## Conditional modes

No additional internal skill modes declared.

## External providers

- `bh integrations`: Herdr only when separately requested/authorized; ordinary in-process fanout does not require it. Optional per-integration bh plugin capabilities; probe installed help and explicit authorization.

## Runtime and invocation scope

- Installed bh CLI for described lifecycle operations; host Skill/Task/AskUserQuestion semantics and seat authority remain external.

Neutral directory names; bh: and /bh: invocation prose and Task/Skill/AskUserQuestion examples are Claude-specific, not an Agent Plugins invocation/enforcement guarantee.

Preserve the included LICENSE notice. Installing companions does not prove live-client behavior or external-provider availability.
