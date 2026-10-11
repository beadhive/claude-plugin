# Installation companions for retro

Generated from the reviewed canonical skill-dependencies.json; this file survives skill-only copying.

The skills CLI installs only the requested directories. It does not resolve companions, install runtimes, configure MCP/hooks/agents/styles, or grant role authority.

## Required companions

None. This does not remove the runtime requirements below.

## Supporting reference companions

None beyond required companions.

## Conditional modes

No additional internal skill modes declared.

## External providers

- `dataviz`: Optional Artifacts presentation branch only. External skill; text/HTML fallback remains available.
- `artifact-design`: Optional Artifacts presentation branch only. External skill; text/HTML fallback remains available.
- `Artifacts`: Optional interactive host rendering branch only. Host capability; not configured by skills CLI.

## Runtime and invocation scope

- Python 3 standard library and Claude Code JSONL transcript schema; no Codex/OpenCode transcript support.

Neutral directory names; bh: and /bh: invocation prose and Task/Skill/AskUserQuestion examples are Claude-specific, not an Agent Plugins invocation/enforcement guarantee.

Preserve the included LICENSE notice. Installing companions does not prove live-client behavior or external-provider availability.
