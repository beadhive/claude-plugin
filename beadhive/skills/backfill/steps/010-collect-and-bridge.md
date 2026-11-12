---
# yaml-language-server: $schema=https://agentguides.io/schemas/0.1/step.schema.json
step:
  id: collect-and-bridge
  title: Collect sources and recover deterministic doc↔bead bridges
  performer: agent
  action:
    type: manual
  verify:
    type: agent_judgment
  on_failure:
    strategy: abort
  effect: read-only
  estimated_duration_minutes: 3
  tags: [collect, bridge, deterministic]
---

# What this step does

Runs `bh backfill history --until collate` from the hive (or with `--hive <path>`). It reads the
hive's own sources, collates them into work units and identifies each unit against the beads that
already exist. Nothing is written to the hive: the output is `collation.json` (and
`evidence.jsonl`) in the **run directory**.

Check `bh --version` first: `bh backfill history` needs bh 0.36.0 or later.

**Sources.** `--sources` picks the readers (default `backfill.history.sources`:
`git,docs,planning`):

- `docs` — `docs/decisions/` and `docs/design/` (and the other layout presets) are matched to
  EXISTING beads. Each doc's owning bead is recovered by deterministic bridges, in order:
  1. **Existing `external_ref`** — a bead already carrying the doc path. Exact.
  2. **Frontmatter back-ref** — a `Beads: <epic>, <id>` line in the doc. Exact.
  3. **Git add-trailer** — the bead id in the subject of the commit that first added the doc.
     Exact.

  HTML docs are read only when `html` is in `backfill.sources.docs.formats` (opt-in).
- `planning` — a GSD `.planning/phases/` tree: each phase is a proposed epic, each plan an issue
  (closed when its summary exists), `depends_on:` edges become dependencies.
- `git` — commits and merges, clustered into work units (a PR, then a merge, then a `feat`
  commit). Only the conventional-commit types in `backfill.collate.include_types` (default
  `feat`) make units.
- `github` — a snapshot read; needs `backfill.sources.github.enabled` and the `tracker-github`
  plugin.

Each unit gets a decision: NEW, PRESENT, NOISE, or a residual left for a human.

**The run directory** is persistent: `--run-dir`, else `backfill.history.run_dir`, else
`<bh home>/state/backfill-history/<hive>`. A re-run resumes from it (evidence is reused while the
sources, their options, `HEAD` and the working tree are unchanged; `--refresh` reads again).

# Why this is first

The deterministic recovery is cheap, correct, and never guesses — so it shrinks the problem
before any judgment is spent. On a tidy hive it resolves the large majority of docs exactly and
hands the agent only the genuine residual.

# Success criteria

- The command exits 0 and `collation.json` exists in the run directory.
- `bh backfill view unit <run-dir>` lists the units with their decisions; residual units are the
  next step's input.

# What can go wrong

| Failure | Likely cause | Action |
|---|---|---|
| `No such command 'history'` | bh older than 0.36.0 | Upgrade bh; do not fall back to a script |
| No units | no `docs/decisions` / `docs/design` and no `feat` commits | Nothing to reconcile from docs; consider `planning` or widen `backfill.collate.include_types` |
| Bead ids not recognised | ids from a ledger the run does not know | Restrict or extend `backfill.history.ledgers` |
| HTML docs ignored | `html` not enabled | Add `html` to `backfill.sources.docs.formats` (opt-in) |

# Notes

Read-only for the hive. The only files written are in the run directory. `backfill.*` is
host-owned config: ask the operator before changing it.
