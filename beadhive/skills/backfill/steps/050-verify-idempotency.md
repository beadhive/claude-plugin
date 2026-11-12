---
# yaml-language-server: $schema=https://agentguides.io/schemas/0.1/step.schema.json
step:
  id: verify-idempotency
  title: Re-run the pipeline and confirm zero proposed changes
  requires: [apply]
  performer: agent
  action:
    type: manual
  verify:
    type: agent_judgment
  on_failure:
    strategy: ask
  effect: read-only
  estimated_duration_minutes: 2
  tags: [verify, idempotency, terminal]
---

# What this step does

Runs `bh backfill history --until plan --refresh` a second time (`--refresh` re-reads the sources
so the new stamps and commits are seen) and inspects the plan with `bh backfill inspect
<run-dir>/plan.bdlg`. Now that every doc-backed bead carries its `external_ref`, the bridges and
the stored refs match exactly: every unit is PRESENT and the plan proposes nothing.

# Why it matters

Idempotency is the whole safety property of the reconcile model. A second run that proposes
changes means a stamp did not take or a NEW bead was mis-created — the run is not done. A clean
second run is the proof that re-running this Guide on the same hive is a no-op, which is what makes
it safe to re-run after every future doc is added.

# Success criteria → terminal

- The second plan has no events to apply.
- No residual remains that the classify step judged NEW/PRESENT (those are now filed or stamped).

On success the walk terminates at **`reconciled`** — or **`nothing-to-do`** if the very first
run already proposed nothing.

# Notes

Read-only. This is the terminal verification; no further writes.
