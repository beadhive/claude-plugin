---
# yaml-language-server: $schema=https://agentguides.io/schemas/0.1/step.schema.json
step:
  id: classify
  title: Resolve the judgment residual — fuzzy match, NEW vs noise, drift
  requires: [collect-and-bridge]
  performer: agent
  action:
    type: manual
  verify:
    type: agent_judgment
  on_failure:
    strategy: ask
  effect: read-only
  estimated_duration_minutes: 6
  tags: [classify, judgment]
---

# What this step does

Reviews the collation, then takes the residual the pipeline refused to guess and resolves each
item with judgment it cannot supply. Review with the read-only views (each takes the run
directory or a `collation.json`):

- `bh backfill view unit [--decision D]` — every unit with its NEW / PRESENT / NOISE / residual
  decision, bead, status and dates.
- `bh backfill view conflict` — status conflicts between sources; both sides are shown and none
  is resolved. You do not resolve them either: flag them for the human.
- `bh backfill view xref` — references to other ledgers' beads and tracker items.
- `bh backfill view cost` — judge calls recorded and their estimated cost.
- `bh backfill verdicts <run-dir>/collation.json [--class C] [--min-confidence X]` — the judge
  verdicts, when a judge is on.

Each residual item comes with candidate beads (up to `backfill.collate.identify.max_candidates`).
Confirm a candidate only if the doc and the bead are genuinely the same work — a high overlap
score is a hint, not proof. For every residual doc, decide:

- **PRESENT (fuzzy)** — a candidate (or another bead you know) is the same work and you are
  confident. Stamp it: `bd update <id> --external-ref <doc>` (or add a `Beads:` line to the doc),
  then re-run `bh backfill history --until collate` so the bridge makes it exact. Record which
  candidate and why. If no candidate fits, do not force one — it is NEW.
- **NEW** — no existing bead represents this work. With create mode off the pipeline proposes
  nothing for it; either set `backfill.collate.create = propose` (opt-in, host-owned; ask the
  operator) so it is proposed as a closed bead, or file it yourself with `bh bd create`.
- **NOISE** — the work is already covered by a coarser bead (a version/phase epic). Link to that
  epic; do not create a new bead.
- **DRIFT** — a matched bead disagrees with its source. Note the delta as a proposed update.
  Reverse-drift (bead richer than the doc, e.g. a decision with no ADR) is a *doc* gap — flag it,
  do not mutate the bead.

**The judge.** It is off by default, so every unmatched doc is an abstain residual. If the operator
wants one: `bh backfill judge setup --dry-run`, then `bh backfill judge setup --enable`. Judged
verdicts need review unless they reach `backfill.judge.auto_accept`; you still read them. The
setup never prints the API key and changes the config only with `--enable`.

Also scan commit history for significant delivered work with **no** doc and no covering bead —
those are NEW candidates too.

# Verification (agent_judgment)

Before declaring done, record in the run log, per residual item: the verdict, and the evidence
(the title matched, the epic that covers it, or why it is genuinely new). A verdict without
recorded reasoning is not acceptable — this is the step where a wrong call creates a duplicate or
buries real history.

# Why judgment, not script

Fuzzy similarity and "does this deserve a bead" are exactly the calls a deterministic tool gets
wrong. Keeping them here — explicit, logged, human-auditable — is what makes the pipeline safe to
trust for everything else.

# Notes

Read-only except for the optional `bd update --external-ref` stamps, which the human should see
first. Output is a classified list feeding the proposal.
