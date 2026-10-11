# Installation companions for setup

Generated from the reviewed canonical skill-dependencies.json; this file survives skill-only copying.

The skills CLI installs only the requested directories. It does not resolve companions, install runtimes, configure MCP/hooks/agents/styles, or grant role authority.

## Required companions

- [setup-git-workspace](../setup-git-workspace/SKILL.md)

## Supporting reference companions

None beyond required companions.

## Conditional modes

No additional internal skill modes declared.

## External providers

No separately installed skill provider is declared for this skill.

## Runtime and invocation scope

- Linux or Darwin instructions; bh/uv/OS tooling installation changes require operator context; Darwin runtime evidence remains explicitly deferred.

Neutral directory names; bh: and /bh: invocation prose and Task/Skill/AskUserQuestion examples are Claude-specific, not an Agent Plugins invocation/enforcement guarantee.

Preserve the included LICENSE notice. Installing companions does not prove live-client behavior or external-provider availability.
