# Installation companions for reproduce

Generated from the reviewed canonical skill-dependencies.json; this file survives skill-only copying.

The skills CLI installs only the requested directories. It does not resolve companions, install runtimes, configure MCP/hooks/agents/styles, or grant role authority.

## Required companions

- [developer](../developer/SKILL.md)
- [work](../work/SKILL.md)

## Supporting reference companions

- [intake-triage](../intake-triage/SKILL.md): included supporting documents link to this sibling; this is reference completeness, not a claim every operation runs it.

## Conditional modes

No additional internal skill modes declared.

## External providers

No separately installed skill provider is declared for this skill.

## Runtime and invocation scope

- Installed bh CLI with the bh work lifecycle; reproduction beads come from bh work investigate (external intake). Running a submitted example needs Linux, bubblewrap and the hive's scripts/hermetic.sh fence; elsewhere it is refused and recorded. Host Skill semantics and seat authority remain external.

Neutral directory names; bh: and /bh: invocation prose and Task/Skill/AskUserQuestion examples are Claude-specific, not an Agent Plugins invocation/enforcement guarantee.

Preserve the included LICENSE notice. Installing companions does not prove live-client behavior or external-provider availability.
