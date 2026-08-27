---
name: refactor
description: >-
  Plan or execute evidence-led, behavior-preserving refactoring. Use when asked to refactor,
  restructure, extract, reorganize, move responsibilities, reduce coupling, or improve code
  architecture without intentionally adding product behavior. With no claimed implementation
  bead, shape the statement into a refactor request and route it through planning; with a claimed
  bead, establish a baseline and north-star, move incrementally with risk-based validation, and
  leave clean reviewable history.
---

# Refactor

Accept a refactoring statement, then choose exactly one mode from the current work context.
Do not treat a request to refactor as permission to change externally observable behavior.

## Choose the mode

- **Proposal mode — no claimed implementation bead:** read
  [the request schema](references/request-schema.md), turn the statement and available evidence
  into a proposed request, then load `bh:plan` and follow its human-gated planner flow in the main
  thread. Produce beads and decision records only in that seat. Do not edit source code or create
  lifecycle state through raw `bd` commands.
- **Execution mode — a claimed implementation bead:** load `bh:developer` and `bh:work`, stay in
  the provisioned bead worktree, and read
  [the execution protocol](references/execution-protocol.md) completely before editing. The bead
  and its acceptance criteria bound the change. If a bead is merely assigned, use the developer
  workflow to brief and claim it first; execution starts only after the claim succeeds.

If the statement is empty or its intended behavior boundary is ambiguous, ask for the missing
intent before proposing or editing. If execution reveals a product decision or scope expansion,
stop that part and route the discovery back through planning rather than silently absorbing it.

## Execution invariants

Follow these phases in order:

1. Record the functional and test baseline, including exact expected failures, before edits.
2. Write the north-star architecture, invariants, boundaries, and explicit non-goals.
3. Plan incremental movement commits whose effects can be compared with the baseline.
4. Select and record an economical, balanced, or strict validation cadence from risk,
   criticality, repository policy, and any operator override.
5. Create local squashable checkpoints at known-good transitions, then self-refine and submit
   through `bh:work`.

Every cadence ends with the repository's full configured validation gate. An unchanged expected
failure may remain when repairing it is outside the bead; a new failure or a materially changed
expected failure is an unexpected regression and blocks progress.

## Safety boundary

Preserve unrelated user changes and stage only this bead's work. Checkpoints are local recovery
evidence, not authorization to reset or discard files, rewrite shared history, force-push, bypass
validation, self-approve, or merge. Use the repository's normal recovery policy and the
`bh:developer`/`bh:work` lifecycle; hand the validated branch to review.
