# Installation companions for intake-triage

Generated from the reviewed canonical skill-dependencies.json; this file survives skill-only copying.

The skills CLI installs only the requested directories. It does not resolve companions, install runtimes, configure MCP/hooks/agents/styles, or grant role authority.

## Required companions

- [work](../work/SKILL.md)
- [operator-communication](../operator-communication/SKILL.md)

## Supporting reference companions

- [reproduce](../reproduce/SKILL.md): included supporting documents link to this sibling; this is reference completeness, not a claim every operation runs it.

## Conditional modes

No additional internal skill modes declared.

## External providers

No separately installed skill provider is declared for this skill.

## Runtime and invocation scope

- Installed bh CLI with the external-intake verbs (bh work intake, accept --work/--new-work, link, investigate, thread, needs-info, wake, outbox draft; batch --review also bh work triage review/propose/check/apply, bh 0.35.0 or later) and a hive whose host-owned intake.external switches are on; drafts only, never approves or sends. Tracker access, operator seats and host Skill semantics remain external.

Neutral directory names; bh: and /bh: invocation prose and Task/Skill/AskUserQuestion examples are Claude-specific, not an Agent Plugins invocation/enforcement guarantee.

Preserve the included LICENSE notice. Installing companions does not prove live-client behavior or external-provider availability.
