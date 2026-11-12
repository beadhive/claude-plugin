# batch-run safety invariants

Quoted verbatim by both the `bh:batch-run` skill and the `bh:spike-runner` agent. This is the highest-consequence rule in the whole spike loop — restated in full wherever it applies, redundantly, on purpose.

- **NEVER call `bh work approve`.**
- **NEVER call `bh work merge`** (including `--group`).
- **NEVER call `bh work finish`.**
- **NEVER auto-resolve a review gate**, by any mechanism.
- Every spike run this skill/agent touches ends at `bh work submit` (gate opened) or an explicit failure/escalation — there is no third outcome.
- Any `BH_DEBUG=1` override used to get past a molecule-convention refusal must be **surfaced to the human in the run summary**, never silently applied and left unmentioned.
- Workers operate only inside their own assigned worktree; no cross-worktree writes.
- If uncertain whether an action is merge-adjacent, treat it as forbidden and stop — ask the human rather than improvise around the rule.

This list exists because a spike batch is meant to run unattended (overnight, spare capacity). Nothing it produces may land on `main` without a human in the loop.
