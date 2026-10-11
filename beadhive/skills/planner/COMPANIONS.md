# Installation companions for planner

Generated from the reviewed canonical skill-dependencies.json; this file survives skill-only copying.

The skills CLI installs only the requested directories. It does not resolve companions, install runtimes, configure MCP/hooks/agents/styles, or grant role authority.

## Required companions

- [operator-communication](../operator-communication/SKILL.md)

## Supporting reference companions

None beyond required companions.

## Conditional modes

- refactor: install `refactor` when Planning a behavior-preserving refactor.
- modularize: install `modularize` when Planning an explicit internal module boundary.
- spike-verdict: install `replan` when A completed spike returns a verdict to planning.

## External providers

No separately installed skill provider is declared for this skill.

## Runtime and invocation scope

- Installed bh CLI for described lifecycle operations; host Skill/Task/AskUserQuestion semantics and seat authority remain external.

Neutral directory names; bh: and /bh: invocation prose and Task/Skill/AskUserQuestion examples are Claude-specific, not an Agent Plugins invocation/enforcement guarantee.

Preserve the included LICENSE notice. Installing companions does not prove live-client behavior or external-provider availability.
