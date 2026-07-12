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

The plugin's MCP server runs the `bh-mcp` binary from the
[beadhive CLI](https://github.com/beadhive/beadhive). Without `bh` on your `PATH` the MCP server
won't start — agents and skills still load, but the `bh` MCP tools won't be available. The
bundled `setup` skill installs it (Phase 2).

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
- **MCP server** — `bh-mcp` (stdio), exposing planning and rig-management tools.

Start with the `beadhive-concepts` skill for the mental model (rigs, molecules, seats, planes).

## Compatibility note

The agent definitions use a `skills:` frontmatter key to preload their role skills. On Claude
Code versions without `skills:` preload support the key is ignored; the agents still work —
they load their skills via the `Skill` tool on demand.

## License

[MIT](LICENSE)
