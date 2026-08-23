---
name: groom
description: >-
  Groom the backlog — reconcile existing beads with new decisions, ADRs, and discussion
  (backlog-wide hygiene, no single triggering epic).
---

# /bh:groom — backlog-wide reconciliation

## Seat contract — binding before any phase instruction

This session is now in the **planning seat**. Its deliverables are exactly two artifact types:

- **Beads** — mutations to existing beads go through the `bd`/`bh` verbs only
  (`bd update` / supersede / close with reason / re-dep); any *new* molecule is compiled by
  `bh plan file`, never hand-created with `bh bd create`.
- **Decision records** — ADRs under `docs/design/`.

**Zero source edits.** Do not write or edit application code, tests, or build config in this
seat. Anything that needs implementing becomes a bead a dispatcher drives later.

## Run groom mode

1. Load the `bh:planner` skill with the Skill tool **now, inline in this main thread** and
   follow its **groom mode** section. Planning is human-interactive — do NOT hand the
   conversation to a Task subagent.
2. Groom takes **no argument**: it is backlog-wide hygiene, the counterpart to replan's
   single-molecule scope. If the human actually has one molecule with a triggering event
   (spike verdict, blocker, discovery), point them at `/bh:replan <epic>` instead.
3. Take in the new inputs — discussion, decisions, ADRs under `docs/design/` — then survey the
   backlog (`bh work list`, `bh plan status`) and reconcile: update stale descriptions,
   supersede/close beads the decisions invalidated (with reasons), re-dep where the DAG
   drifted.
4. Propose each reconciliation to the human before applying it; batch related mutations so the
   backlog moves in reviewable steps.
