---
compatibility: "Requires bh CLI with the bh work lifecycle and the Task tool; bh work assign needs an orchestrator seat (disp/<name> or dir/<name>). Task/Skill examples and the bh: namespace are Claude-specific."
name: batch-run
description: >-
  Batch-execute a set of ready tag:spike beads in parallel, each in its own bh-provisioned git
  worktree, running until each spike's plan is executed and bh work submit opens its review
  gate — then STOP. Hard-forbidden from ever calling bh work approve, merge, or finish; nothing
  this skill touches may reach main unattended. Designed for overnight / spare-capacity runs.
  Use when the user says "run the spike batch", "kick off the spikes overnight", "batch-run
  ready spikes", "execute this wave of spikes in parallel", or "spike batch".
allowed-tools: Bash, Read, Task, Skill
---

# batch-run

## Absolute safety invariant

**Never call `bh work approve`, `bh work merge`, or `bh work finish`.** Every spike this skill touches stops at `bh work submit`. The full invariant list lives in `references/safety-rules.md` — read it before running this skill and treat it as non-negotiable. If a step ever seems to require merging, stop and hand control back to the human; do not improvise around the rule.

If this skill is being run via the `bh:spike-runner` agent, that agent's own `tools:` list structurally omits `Edit`/`Write` for the same reason — don't try to work around that ceiling either.

## bh availability

1. Check whether `bh` plugin skills are loaded in this session (e.g. `bh:work`, `bh:dispatcher`); load the relevant one via the `Skill` tool for the canonical verb reference.
2. Otherwise check `command -v bh`; if present, run `bh work --help` to learn the live command surface.
3. If neither is available, stop — `bh` is a hard dependency, don't guess at flags for a lifecycle-mutating command.

## Readiness check

Pull the dependency-ordered ready set, filtered to spike work: `bh work ready -l tag:spike --json`. bh's own ready-set already encodes "not blocked by other unresolved beads" — don't re-derive that check by hand. `bh work ready` forwards its flags to `bd ready`, so `--gated` (`bh work ready --gated`) separately lists molecules whose kickoff gate has closed and are ready for gate-resume dispatch; use it to see which spike molecules are cleared to start. Optionally sanity-check batch-vs-singleton cost per candidate molecule with `bh work schedule <epic>`.

## Selecting the batch

Confirm the actual scope with the user (or apply an explicit cap they gave you — "at most N spikes tonight", "everything ready", a named list). Do not silently expand the batch to include ready spikes the user hasn't scoped in; an overnight run with an unbounded scope is exactly the kind of surprise this skill exists to prevent.

## Claim + fan-out

Mirror `bh:dispatcher`'s fanout pattern — one worker per bead, each in its own worktree, each responsible only for its own spike. For each selected spike bead:

1. Take the molecule's epic seat the way `bh:dispatcher` does (`bh work start <epic> --as disp/<name>`) when the batch is dispatched from an orchestrator identity.
2. Provision the spike's worktree with `bh work claim <id> --as dev/<name>` (the worker's ack), or pre-stamp it from an orchestrator seat with `bh work assign <id> --to dev/<name> --as disp/<name>`. `assign` is orchestrator-only: it hard-denies any seat other than `disp/<name>` or `dir/<name>`, and `--to` takes a `dev/<name>` identity. Add `--preview` to either verb to see what it would provision without touching `bd` or git.
3. Launch one `Task` per spike, passing the spike bead's Question/Method as the brief.

If a spike's molecule fails `bh plan verify <epic>` conventions (missing kickoff gate, no bd swarm, missing acceptance criteria) and `claim`/`assign`/`start` refuses it, see `## Escape hatches` below — do not paper over the refusal silently.

## Per-worker contract

Each worker: reads its spike bead's Method, executes it (code changes, experiments, measurements — whatever the spike's plan calls for) **inside its assigned worktree only**, writes the verdict doc with an honest Question/Method/Evidence/Verdict/Recommendation (confirm the repo's actual verdict-doc convention/path rather than assuming one), commits, then runs `bh work submit <id>` and stops. Workers must never touch another worker's worktree.

## Watching the wave

Poll gate status across the batch (`bh work issue <gate-id> --json`, `bh work show <id>` for the bead's branch and gates, or `bh work list --json` filtered by status). Do not proceed to merge anything, ever, for any reason — that's categorically out of scope for this skill.

## Escape hatches, disclosed only

If a molecule fails conventions:

- `BH_DEBUG=1` is a human override, usable but **must be surfaced loudly in the run summary** — never silently applied.
- `bh escalate '<msg>'` punts to HQ intake without overriding anything — the safer default when a human isn't actively watching the run.

Never silently retry with an override and move on as if nothing happened; always narrate what was needed and why.

## Wave summary

On conclusion (every worker submitted, escalated, or errored), produce a short table: spike id, worktree branch, gate id, submit status, any escalations/overrides used. Don't attempt to synthesize verdicts here — that's the `bh:spike-report` skill's job, and it's the natural next step to point the user at.
