---
name: plan
description: >-
  Enter the planning seat — drive an idea through the staged planner flow into a gated beads
  molecule (beads + decision records only, never code).
metadata:
  argument-hint: <idea>
---

# /bh:plan — enter the planning seat

## Seat contract — binding before any phase instruction

This session is now in the **planning seat**. Its deliverables are exactly two artifact types:

- **Beads** — molecule specs compiled by `bh plan file`. That verb is the **only** filing
  path; never hand-create an epic or issue with `bh bd create`.
- **Decision records** — ADRs under `docs/design/`.

**Zero source edits.** Do not write or edit application code, tests, or build config in this
seat. Anything that needs implementing becomes a bead a dispatcher drives later. To pin this
contract for whole sessions, select the plugin's `planning-seat` output style (`/config` →
Output style; applies from the next session).

## Run the flow

1. Load the `bh:planner` skill with the Skill tool **now, inline in this main thread**.
   Planning is human-interactive — do NOT hand the planning conversation to a Task subagent.
   (The skill's deep tier spawning read-only `analyst` research subagents is the one exception.)
2. The idea to plan: **$ARGUMENTS** — if empty, ask the human for the idea before proceeding.
3. Drive the skill's staged flow — frame → triage → research → architecture → decompose →
   validate/preview → file → verify → kickoff — with a human checkpoint at every stage.
4. Honor the **spike branch** of fidelity triage: if research or architecture surfaces an
   unresolved GO/NO-GO question, propose a **spike molecule** (spike beads `tag:spike` + one
   decision bead `tag:decision`) instead of guessing or filing speculative implementation
   beads. The verdict re-enters planning via `/bh:replan <spike-epic>`.
