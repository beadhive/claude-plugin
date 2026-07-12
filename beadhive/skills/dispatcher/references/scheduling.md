# Scheduling — batch vs singleton (the cost model)

The default unit is **one bead → one worktree → one developer → one merge**, and that is the
right call whenever beads are independent: distinct worktrees give you parallel wall-time and
each lands on its own clean conventional history. **Batch only when batching is genuinely
cheaper** — a *work group* runs several beads in ONE `wt/batch/<group>` worktree by one agent,
validated and merged **once** as a single `--no-ff` bubble (per-bead commits preserved inside, so
it stays lossless / bisectable).

Batching wins when a **trigger** applies AND the group stays **cohesive**:

- **Linear chain, no mid-point unit** — beads that build on each other with no testable/reviewable
  checkpoint until the end. A chain can't be parallelized anyway, so per-bead merges only add
  meaningless intermediate states; one bubble is strictly cheaper.
- **Same-file contention** — DAG-parallel beads all editing one file would collide on repeated
  separate merges. The planner declares these as a `batch:<group>` (it knows them at decompose
  time).
- **Expensive validation** — when integration-test setup costs more per session than implementing
  several cohesive beads serially and validating **once** at the end.

Otherwise keep singletons — independent + cheap-to-validate beads benefit from parallel wall-time.

**`bh work schedule <epic>`** computes this for you (read-only; `--json` for machine use). It:

1. **Honors planner batches** — any `batch:<group>` the planner declared (already cohesion- /
   size- / model-validated at plan time) with ≥2 members becomes one grouped agent.
2. **Auto-detects pure linear chains** — a run of beads connected by *private* `blocks` edges
   (no fan-in / fan-out), which nobody validated at plan time, so the scheduler re-applies the
   guards below before batching it.

Everything else is a singleton. Dispatch one developer `Task` per group / singleton.

## Guards (why a candidate is NOT batched)

- **Cohesion** — members must hang together (same component, or contiguous in the dep DAG). A
  grab-bag batch fails as a unit and is hard to review. (A private-edge chain is contiguous by
  construction; planner batches are checked at plan time.)
- **Size cap** — at most `work.batch_max_size` (default 5) members, so the bubble stays reviewable
  and bisectable. An overlong chain falls back to singletons.
- **Single model tier** — a group runs as one unit on one model; mixed `model:` tiers are refused.
- **No mixed review gates** — members must share a review gate; a chain mixing `gate:` overrides is
  refused (so one approval covers the whole bubble).

A candidate that trips any guard is dispatched as singletons instead — the cost model never forces
an incohesive or oversized batch. **Blast radius:** a batch fails (and bounces on changes-requested)
as a whole, so keep groups small and cohesive; that is the price of fewer merges/validations.
