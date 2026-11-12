---
# yaml-language-server: $schema=https://agentguides.io/schemas/0.1/skill-guide-extension.schema.json
name: backfill
description: >-
  Reconstruct a hive's history as beads from its own local sources (git log, decision/design
  docs, planning frontmatter) WITHOUT duplicating beads that already exist. Activate when
  onboarding or catching up a repo that has real history — and possibly a partial bead corpus —
  and you want that history represented as beads. Drives `bh backfill history` (bh 0.36.0 or
  later) through propose → reconcile → classify → suggest and stops for human confirmation;
  never blind-imports.
license: MIT
compatibility: >-
  Requires `bh` 0.36.0 or later (`bh backfill history`, `collate`, `view`, `verdicts`) and a
  bd-tracked hive (`.beads/` is initialized; its JSONL corpus may be absent or empty). Local
  sources are `docs/decisions/`, `docs/design/` and/or `.planning/`. Parsing, bridge recovery,
  collation and the reconcile plan live in the bh library; fuzzy matching and NEW-vs-noise calls
  stay with the agent (or the opt-in judge).
allowed-tools: Bash, Read, Edit, Grep, AskUserQuestion
metadata:
  type: guide
  guide:
    entry: GUIDE.md
---

# Backfill (agent-assisted, reconcile-first)

This Skill is a **Guide**. A Guide-aware harness loads `GUIDE.md` to begin a run; a plain-Skill
harness should read `GUIDE.md` for framing, then walk `steps/` in order.

Core rule: **a backfill is a reconcile, not an import.** Every run proposes candidate beads from
the hive's own sources, matches them against the beads already present, and writes only the gap —
so a re-run is idempotent and an already-well-tracked hive degenerates to provenance-stamping
rather than duplicate creation.

**Requires `bh` >= 0.36.0.** Check with `bh --version`; an older `bh` has no `bh backfill
history`, and this skill no longer ships a script fallback.

The deterministic half (recover the doc↔bead link, join against the corpus, classify) is done by
`bh backfill history`. The judgment half (fuzzy fallback, is-this-NEW-or-noise, drift) stays with
the agent. Nothing is written until a human sees the diff. The bridge-recovery rules (how doc↔bead
links are found and scored) live in `references/bridges.md`.

## The flow

| Step | Command | Writes? |
|---|---|---|
| propose + reconcile | `bh backfill history --until collate` | run dir only |
| review | `bh backfill view unit` / `conflict` / `xref` / `cost`, `bh backfill verdicts <run-dir>/collation.json` | no |
| classify | the agent resolves the residual (stamp a bead, or leave it) and re-runs | no |
| suggest | `bh backfill history --until plan`, then `bh backfill inspect <run-dir>/plan.bdlg` | run dir only |
| human confirm | the operator approves the diff | |
| apply | `bh backfill history --until apply --yes` | the hive, behind the apply envelope |
| verify | re-run `--until plan`; it must propose nothing | no |

`--until` stops after a stage: `parse` (`evidence.jsonl`), `collate` (`collation.json`), `plan`
(`plan.bdlg`, the default; nothing is written to the store) or `apply`. Never run `--until apply
--yes` before the human has seen the plan.

## Run directory and resume

Every stage leaves its output in a persistent **run directory** (`--run-dir`, else
`backfill.history.run_dir`, else `<bh home>/state/backfill-history/<hive>`), with `run.json`
recording what each stage did. A re-run resumes from it: evidence is reused while the sources,
their options, `HEAD` and the working tree are unchanged (`--refresh` reads again), and the
previous `collation.json` is fed to the judge as its prior so judged queries are not asked twice.
Collation and planning are always recomputed against the current store.

## Options that change what a run does (all opt-in)

- **Create mode.** By default (`backfill.collate.create = off`) a run is link-only: a unit that
  matches no bead projects nothing, and the plan reports how many events were not proposed. Set
  `backfill.collate.create = propose` to have such units proposed as closed beads. Treat that as
  the NEW-bead path and review every one before apply.
- **HTML docs.** Markdown docs are read by default; add `html` to `backfill.sources.docs.formats`
  to read `.html` / `.htm` docs too (title, `<meta>` status/date, a visible `Status:` line).
- **Sources.** `--sources` (default `backfill.history.sources` = `git,docs,planning`). `github`
  also needs `backfill.sources.github.enabled` and an enabled `tracker-github` plugin.
- **Judge.** Off by default, so every unmatched doc is an abstain residual for the human. To use
  one, run `bh backfill judge setup` (`--dry-run` first; `--enable` writes the config only after
  every step passed). Review its verdicts with `bh backfill view verdicts`; judged entries need
  review unless they reach `backfill.judge.auto_accept`. `bh backfill view cost` and
  `backfill.judge.cost_per_call_usd` show the spend; `--yes` confirms a run larger than
  `max_calls_per_run`.
- **Gap fill.** `backfill.timeline.gapfill.on_created` (off) gap-fills only the beads a
  create-mode apply made, writing `<run-dir>/gapfill.bdlg`. Leave it off unless those ids had
  earlier history.

These are host-owned `backfill.*` config keys; do not edit them without the operator's say-so.
