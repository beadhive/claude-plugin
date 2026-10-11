# Beadhive Instructions

Use Beadhive (`bh`) for bead lifecycle, hive-aware issue operations, planning, dispatch,
review and merge flow. Prefer first-class `bh work`/`bh plan` verbs when available.
Use `bh bd` for low-level bead operations only when the task requires them and no
first-class verb covers the action.

Load the relevant role skill before acting:

- [overview](../skills/overview/SKILL.md) explains terminology and lifecycle.
- [planner](../skills/planner/SKILL.md) handles idea-to-molecule planning.
- [dispatcher](../skills/dispatcher/SKILL.md) executes approved molecules.
- [developer](../skills/developer/SKILL.md) and [work](../skills/work/SKILL.md) implement single beads.
- [reviewer](../skills/reviewer/SKILL.md), [merger](../skills/merger/SKILL.md) and work cover review/integration.
- [control](../skills/control/SKILL.md) covers factory coordination and commissioning.
- [operator communication](../skills/operator-communication/SKILL.md) supplies decision/status guidance.

Keep planning, implementation, review and merge responsibilities separated by role.
Do not bypass lifecycle gates with raw git or bead edits when a `bh work` or `bh plan`
verb exists. These are bundled instructions, not automatically injected host policy.
