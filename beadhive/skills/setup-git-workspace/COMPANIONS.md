# Installation companions for setup-git-workspace

Generated from the reviewed canonical skill-dependencies.json; this file survives skill-only copying.

The skills CLI installs only the requested directories. It does not resolve companions, install runtimes, configure MCP/hooks/agents/styles, or grant role authority.

## Required companions

None. This does not remove the runtime requirements below.

## Supporting reference companions

None beyond required companions.

## Conditional modes

No additional internal skill modes declared.

## External providers

- `git-workspace:import`: Importing existing repositories; required for this documented guided branch. External skill/provider; not bundled or installed automatically.
- `git-workspace:install`: Selecting plugin-led installation branch. External skill/provider; not bundled or installed automatically.
- `git-workspace:providers`: Configuring providers with the documented guided branch. External skill/provider; no token/account access granted by this pack.

## Runtime and invocation scope

- git-workspace executable/configuration and authorized provider access; Linux/Darwin installation paths remain host-specific.

Neutral directory names; bh: and /bh: invocation prose and Task/Skill/AskUserQuestion examples are Claude-specific, not an Agent Plugins invocation/enforcement guarantee.

Preserve the included LICENSE notice. Installing companions does not prove live-client behavior or external-provider availability.
