# beadhive/claude-plugin

Claude Code marketplace for the **`bh` plugin** — the agents and skills Claude Code uses to
perform roles in a [Beadhive](https://github.com/beadhive/beadhive) factory: planning ideas into
bead molecules, dispatching them to developer agents, reviewing, and merging onto an always-green
integration line.

## Install

```sh
claude plugin marketplace add beadhive/claude-plugin
claude plugin install bh@beadhive
```

Restart Claude Code after installing. Then `/setup` walks a fresh machine from zero to a
configured Beadhive workspace.

### Prerequisite: the `bh` CLI

The plugin requires `bh >=0.3.0` on your `PATH`. The MCP server runs the `bh-mcp` binary from the
[beadhive CLI](https://github.com/beadhive/beadhive); without a compatible `bh`, the MCP server
won't start and the hooks block `bh`/`bd` calls instead of failing silently. On mismatch,
SessionStart prints an upgrade advisory and points to the
[Beadhive install guide](https://github.com/beadhive/beadhive/blob/main/INSTALL.md) or `/setup`.
The bundled `setup` skill installs it (Phase 2).

## What's inside

One plugin, `bh` (in [`beadhive/`](beadhive/)):

- **11 agents** — one per factory seat: `supervisor`, `director`, `custodian`, `controller`
  (control plane); `planner`, `analyst` (planning); `dispatcher`, `developer`, `reviewer`,
  `merger` (integration); `warden` (assurance). Each states its plane, authority, and hard
  limits; launch one as the main loop with `claude --agent bh:<seat>`.
- **Skills** — role guides (`planner`, `dispatcher`, `developer`, `reviewer`, `merger`,
  `control`), the `work` verb reference for the bead lifecycle, a `beadhive-concepts`
  glossary/router, `setup` + `setup-git-workspace` onboarding walkthroughs, and `backfill`
  for reconciling bead provenance on an existing repo.
- **Commands** — planning-seat entry points: `/bh:plan <idea>` (idea → gated molecule),
  `/bh:replan <epic>` (re-enter planning on a spike verdict or mid-execution discovery), and
  `/bh:groom` (backlog-wide reconciliation). Each states the seat contract — deliverables are
  beads + decision records, never code — and loads the `planner` skill inline.
- **Output style** — `planning-seat`, pinning that contract for a whole session
  (`/config` → Output style).
- **MCP server** — `bh-mcp` (stdio), exposing planning and hive-management tools.

Start with the `beadhive-concepts` skill for the mental model (hives, molecules, seats, planes).

## Compatibility note

The agent definitions use a `skills:` frontmatter key to preload their role skills. On Claude
Code versions without `skills:` preload support the key is ignored; the agents still work —
they load their skills via the `Skill` tool on demand.

The runtime preflight is intentionally blocking: if `bh` is missing or older than `0.3.0`, the
SessionStart advisory explains the mismatch and PreToolUse denies `bh`/`bd` Bash calls plus `bh`
MCP tool calls until the CLI is upgraded. If the SessionStart sentinel is absent, the guard fails
open and leaves the normal permission flow unchanged.

## License

[MIT](LICENSE)
