---
name: triage
description: >-
  bv (Beads Viewer) robot-mode command reference for bead triage, grooming, planning, and
  scheduling — the AI-agent entry points (--robot-triage, --robot-next, --robot-plan,
  --robot-insights) that give deterministic JSON output instead of ad hoc `bd`/`bh work`
  queries. Only applicable when `bv` is installed (`command -v bv`); if it isn't, fall back
  to `bd ready` / `bh work schedule` as usual. Use when deciding what to work on next,
  grooming/reconciling the backlog, building an execution plan for a molecule, or answering
  "what's ready", "what should I work on", "how should this epic be sequenced".
---

# bv — robot-mode bead triage, grooming, planning, scheduling

`bv` (Beads Viewer) is a companion CLI to `bd`/`bh` that reads the same beads database and
adds graph-aware analysis: dependency-respecting execution plans, structural insights
(fan-in/fan-out, cycles, stale clusters), and a single unified triage recommendation. Bare
`bv` launches an interactive TUI for humans — agents use the `--robot-*` flags instead, which
are deterministic and machine-parseable.

Triage/grooming/planning/scheduling: try `bv --robot-*` output first if `bv` is installed
(`command -v bv`); otherwise use raw `bd ready` / `bh work schedule`.

**Precondition** — this only applies when `bv` is on `PATH` (`command -v bv`). If it isn't
installed, keep using `bd ready` / `bh work schedule` / `bh work list` as normal; nothing here
is required.

## Core commands

| Flag | Use for |
|---|---|
| `--robot-triage` | Unified triage output — the recommended default entry point for "what's the state of the backlog / what needs attention". |
| `--robot-next` | Single top recommendation — "what should I work on next" in one shot. |
| `--robot-plan` | Dependency-respecting execution tracks — building/checking a schedule for a molecule (pairs with `bh work schedule`). |
| `--robot-insights` | Graph metrics and structural analysis — grooming: stale clusters, orphans, high fan-in/out, cycles. |
| `--robot-capabilities` | Machine-readable command/contract manifest — call this first if the exact flags/output shape for this `bv` version are unclear. |
| `--robot-schema` | JSON Schema for robot outputs — validate/parse `--robot-*` output programmatically. |

## Guidance

- Prefer `--robot-triage` as the default first call for any triage/grooming session; drill
  into `--robot-plan`/`--robot-insights` only once triage points at scheduling or structural
  questions.
- `--robot-next` is for a single-pick decision (e.g. "what do I claim next") — don't reach for
  full `--robot-triage` when only one recommendation is needed.
- Treat `bv` output as advisory, not authoritative — it reads the same `bd`/`bh` database but
  never mutates it; all lifecycle changes (claim/close/dep) still go through `bd`/`bh work`.
- If `--robot-capabilities` or `--robot-schema` disagree with this table (a newer/older `bv`),
  trust the live output over this file.
