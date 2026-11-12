---
# yaml-language-server: $schema=https://agentguides.io/schemas/0.1/step.schema.json
step:
  id: apply
  title: Apply the approved plan — stamp links and file NEW beads
  requires: [emit-proposal]
  performer: either
  action:
    type: manual
  verify:
    type: agent_judgment
  on_failure:
    - reason: apply-failed
      strategy: ask
    - reason: label-validate-failed
      strategy: ask
  effect: reversible
  estimated_duration_minutes: 4
  tags: [apply, write]
---

# What this step does

Only after the human's recorded approval, writes the plan into the hive:

```
bh backfill history --until apply --yes
```

This runs the existing apply envelope: plan hash and drift gate, a pre-state export
(`pre-state.jsonl`), a checkpointed audit (`audit.json`), verification, rollback on failure and a
second dry run. `--yes` is required when the plan holds verdicts that need review, so passing it
is itself the confirmation: never add it before the human has approved the diff. A plan can also
be applied later with `bh backfill apply <run-dir>/plan.bdlg`.

What gets written:

- **Stamps (PRESENT):** `external_ref`, `git.commits` and cross-reference stamps on beads that
  already exist. Nothing is overwritten.
- **NEW beads (create mode only):** with `backfill.collate.create = propose` the plan creates
  closed beads for units that matched nothing, with epics, `parent-child` and `blocks` edges for
  planning sources. With create mode off, NEW work is not written by the pipeline; file the
  few judged-NEW items with `bh bd create` (run inside the hive: it injects the
  `provider:/org:/repo:` triplet that plain `bd create` omits).
- **Gap fill (opt-in):** with `backfill.timeline.gapfill.on_created` on, the beads this apply
  created are gap-filled afterwards into `<run-dir>/gapfill.bdlg` (the store is only read).

Then `bh labels validate` must be green in the hive.

# Verification (agent_judgment)

The apply exits 0 and its audit reports a clean second dry run. A non-zero exit means the
envelope rolled back or stopped; do not proceed, and use `pre-state.jsonl` for recovery.

# Failure shape

| Reason | Strategy | Next |
|---|---|---|
| `apply-failed` | `ask` | The envelope stopped (drift, plan hash, a write error); human inspects the audit and decides |
| `label-validate-failed` | `ask` | A NEW bead is missing the triplet/registry labels; fix labels, re-validate |
| (any other) | discovered friction | Runtime captures the unknown failure |

# Notes

`effect: reversible` — the pre-state export and the audit make the write recoverable. Prefer
fixing forward (re-stamp, re-label) over deleting history.
