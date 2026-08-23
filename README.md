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

The plugin requires the supported [`bh` CLI range](beadhive/scripts/bh-compatibility.sh) on your
`PATH`. The MCP server runs the `bh-mcp` binary from the
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
  `control`), the `work` verb reference for the bead lifecycle, an `overview`
  glossary/router, `setup` + `setup-git-workspace` onboarding walkthroughs, `backfill`
  for reconciling bead provenance on an existing repo, and `triage` — a robot-mode
  command reference for `bv` (Beads Viewer), self-gated to only apply when `bv` is on
  `PATH`.
- **Planning skills** — namespaced planning-seat entry points: `/bh:plan <idea>` (idea → gated molecule),
  `/bh:replan <epic>` (re-enter planning on a spike verdict or mid-execution discovery), and
  `/bh:groom` (backlog-wide reconciliation). Each states the seat contract — deliverables are
  beads + decision records, never code — and loads the `planner` skill inline.
- **Output style** — `planning-seat`, pinning that contract for a whole session
  (`/config` → Output style).
- **MCP server** — `bh-mcp` (stdio), exposing planning and hive-management tools.
- **Hooks** — `PreToolUse` steering that nudges direct `bd` calls to the hive-aware `bh bd`
  passthrough (and, for triage/groom/plan/schedule shaped calls, further points at `bv`'s
  `--robot-*` commands when `bv` is installed — see `triage`) and auto-approves read-only
  `bd`/`bh` verbs; a `SessionStart` hook that runs `bh hive context --hook-json` to inject AGF
  steering for a registered hive that carries no on-disk plugin files.

Start with the `overview` skill for the mental model (hives, molecules, seats, planes).

## Compatibility note

The agent definitions use a `skills:` frontmatter key to preload their role skills. On Claude
Code versions without `skills:` preload support the key is ignored; the agents still work —
they load their skills via the `Skill` tool on demand.

The runtime preflight is intentionally blocking: if `bh` is missing or outside the supported
range, the
SessionStart advisory explains the mismatch and PreToolUse denies `bh`/`bd` Bash calls plus `bh`
MCP tool calls until the CLI is upgraded. If the SessionStart sentinel is absent, the guard fails
open and leaves the normal permission flow unchanged.

The `SessionStart` hive-context injection reaches Claude Code only — it feeds steering into the
live session. Other harnesses (e.g. Codex) read steering from an on-disk `AGENTS.md`, so a
zero-footprint hive still needs `bh hive onboard --furnish`/`--agents` to write that file for
them; the registry-only path does not cover them. The hook is also a silent no-op on a `bh`
older than 0.3.0 (no `hive context` verb), so it never breaks session start.

## License

[MIT](LICENSE)
