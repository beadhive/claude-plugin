---
name: plugins
description: >-
  Progressive-disclosure router for the `bh plugin` CLI namespace and its Herdr, Orca,
  Observaloop, Repowise, agent-hitch, and git-workspace integration surfaces. Use for questions
  about plugin enablement, installation, status, diagnostics, ownership, static-analysis evidence,
  or safe integration operation; probe installed `bh plugin` help for version-specific syntax.
---

# bh plugins — integration router

This skill covers the **`bh plugin` CLI namespace**: integrations mounted by the installed
`bh` binary. It is not the Claude Code **`bh` plugin** package that ships these agent skills.
Those are related delivery surfaces, but installing or updating the Claude package does not by
itself state which CLI integrations are available or enabled.

## Start with the installed CLI

The installed CLI is the syntax authority. Before proposing or running an integration command,
probe the available surface:

```bash
bh plugin --help
bh plugin NAME --help
```

Use the selected reference for stable intent, lifecycle, boundaries, and safe diagnostics. Do
not copy a full option list into this router: command names, flags, and supported targets can
change with the installed `bh` version.

## Route by integration

| Integration | Load this reference for |
|---|---|
| Herdr | Persistent interactive-agent execution, agent integration, targets, and safe pane cleanup: [references/herdr.md](references/herdr.md). |
| Orca | Registration, optional worktree delegation, settings fences, and readiness: [references/orca.md](references/orca.md). |
| Observaloop | Telemetry profile lifecycle, status, shutdown, and observability diagnostics: [references/observaloop.md](references/observaloop.md). |
| Repowise / static analysis | Local-index lifecycle, native analysis boundaries, refactor evidence, and safe diagnostics: [references/repowise.md](references/repowise.md). |
| agent-hitch | Explicit harness launch targets, profiles, readiness, and teardown: [references/hitch.md](references/hitch.md). |
| git-workspace | Required workspace dependency, repo groups, provider/auth diagnostics, and native-tool handoff: [references/git-workspace.md](references/git-workspace.md). |

## Shared reference contract

Each integration reference is a focused operational contract, not a replacement for its native
manual. Keep every reference in this shape:

1. **Purpose** — what the integration supplies and when to choose it.
2. **Prerequisites and gating** — installation, version, service, configuration, or state
   checks that must pass before operation.
3. **Ownership boundary** — what `bh` owns, what the native integration owns, and what remains
   user or hive/worktree state.
4. **Normal workflow** — probe-first, ordered operations with the installed `--help` as syntax
   authority; call out commands that mutate state before running them.
5. **Diagnostics** — status/readiness probes, common failure signals, and the next safe check.
6. **Cleanup and safety** — teardown effects, idempotence, and conditions that prohibit a
   destructive action.
7. **Current limitations** — unsupported behavior, scope limits, and no-op or asymmetrical
   lifecycle edges.
8. **Upstream or deeper guidance** — where to go for native installation, configuration, or
   exhaustive command documentation.

The router stays thin: load only the reference for the integration being operated.
