---
description: Re-enter the planning seat for ONE molecule — carry a spike verdict or a mid-execution blocker/discovery into amended beads or the implementation molecule
argument-hint: <epic>
---

# /bh:replan — re-enter planning on evidence

## Seat contract — binding before any phase instruction

This session is now in the **planning seat**. Its deliverables are exactly two artifact types:

- **Beads** — molecule specs compiled by `bh plan file`. That verb is the **only** filing
  path; never hand-create an epic or issue with `bh bd create`. Amendments to existing beads
  go through the `bd`/`bh` verbs (update / supersede / close with reason / re-dep).
- **Decision records** — ADRs under `docs/design/`.

**Zero source edits.** Do not write or edit application code, tests, or build config in this
seat. Anything that needs implementing becomes a bead a dispatcher drives later.

## Run replan mode

1. Load the `bh:planner` skill with the Skill tool **now, inline in this main thread** and
   follow its **replan mode** section. Planning is human-interactive — do NOT hand the
   conversation to a Task subagent.
2. The molecule to replan: **$ARGUMENTS** — an epic id is **required**. If empty, stop and ask
   the human which epic before doing anything else.
3. Read the epic and its swarm state (`bh plan show <epic>`, `bh work list`), then pick the
   trigger path:
   - **Spike epic** (labeled `tag:spike`) — walk the molecule's `docs/spikes/` artifacts and
     the decision bead's verdict. On **GO**, carry the evidence into architecture and drive
     toward filing the **implementation molecule** with `bh plan file`, linking its
     description/`external_ref` back to the spike epic for provenance. On **NO-GO**, confirm
     the ADR is recorded and the molecule is closed out with reasons.
   - **Live molecule** — a blocker, review bounce, or discovery invalidated part of the plan:
     supersede/close the invalidated beads (with reasons), re-dep survivors, and file
     follow-on beads as needed.
4. **Evidence first, always**: gather the triggering evidence, restate what changed, and get
   the human's confirmation *before* altering any bead.
