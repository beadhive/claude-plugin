---
compatibility: "Requires bh CLI and the bh:plan / bh:planner planning-plane skills. Skill examples and the bh: namespace are Claude-specific."
name: propose
description: >-
  Judge and prioritize the pool of tag:idea beads brainstorm filed (or ad hoc ideas handed to
  it directly), then mechanically file the accepted ones through bh:planner's existing molecule
  flow — an implementation molecule when feasibility is already settled, or a spike molecule
  (spike beads + one decision bead, explicit go/no-go acceptance criteria) when it isn't. Never
  calls bd create for a molecule and never invents a bead-filing shortcut — always ends in
  bh plan file so bh plan verify / claim / assign accept the result. Use when the user says
  "judge these ideas", "what's worth pursuing", "prioritize the idea backlog", "file these
  ideas", "spike this", or after brainstorm produces idea beads.
allowed-tools: Read, Bash, Skill
---

# propose

Two jobs, in order: **judgment** (which brainstormed ideas are worth pursuing, and in what priority), then **filing mechanics** (getting the accepted ones correctly into `bh:planner`'s molecule flow). This skill generates no ideas of its own — that's `bh:brainstorm`'s job, upstream.

## Hard rule

Never call `bd create` or hand-craft bead JSON for a molecule. The only correct path for an epic/spike molecule is `bh plan file` via a `bh:plan` (planner) session. A hand-rolled epic fails `bh plan verify` (missing kickoff gate / bd swarm / acceptance criteria) and gets refused by `claim`/`assign`/`start` downstream.

(The one exception in this loop is `bh:brainstorm`'s own lightweight `tag:idea` beads, which are deliberately pre-molecule capture items — that's a different, narrower use of `bd create` than what this rule forbids.)

## bh availability

1. Check whether `bh` plugin skills are loaded in this session (e.g. `bh:plan`, `bh:planner`); load the relevant one via the `Skill` tool.
2. Otherwise check `command -v bh`; if present, run `bh plan --help`.
3. If neither is available, stop — this skill cannot file anything without `bh`.

## Input

Pull the pool of `tag:idea` beads `bh:brainstorm` filed (`bh work list -l tag:idea --json`), or accept ad hoc ideas the user hands you directly.

## Judgment pass

Score/rank each idea on:

- **Vision alignment** — how directly it traces to a north-star theme.
- **Urgency** — does it unblock something concrete right now.
- **Feasibility clarity** — is the approach known, or is there a genuine open question.
- **Rough effort** — a coarse sense of cost, not a full estimate.
- **Readiness** — does it depend on something not yet in place (another epic, a design decision).

Present the prioritized shortlist to the user for accept/cut/reorder. **Never silently file the whole idea pool** — judgment without a human checkpoint isn't judgment, it's just automation with extra steps.

## Feasibility triage (per accepted idea)

Mirror `bh:planner`'s own spike-loop exit criteria — don't redefine it:

- **Feasibility settled** (the approach is known) → file as a normal implementation molecule via `bh:plan`.
- **Open go/no-go question** → file as a spike molecule: spike bead(s) (`type: task`, label `tag:spike`, acceptance criteria = a verdict doc with an explicit, testable go/no-go bar — confirm the repo's actual verdict-doc convention rather than assuming a path) plus one decision bead (label `tag:decision`, depends on all spike beads in the molecule, describes both outcomes: GO → `/bh:replan <spike-epic>`, NO-GO → write an ADR under the repo's decisions convention and close).

Refuse to file a spike bead without an explicit, testable go/no-go bar in its description — a spike filed without one produces an unreviewable report tab later (`bh:spike-report`'s section 1 has nothing to pull).

## Filing mechanics

Invoke the `bh:plan` skill (plan mode) with the idea (and, for a spike, the go/no-go bar) as the seed input. Let the planner drive its normal staged flow (ideate → research → architecture → decompose → `bh plan file`) rather than trying to shortcut any stage yourself.

## Verification

After filing, run `bh plan verify <epic>` (or the planner's own equivalent check step) before declaring the idea filed. Surface the resulting epic id(s) to the user.

## Idea-bead cleanup

Mark each promoted idea bead as linked to its resulting epic (so the lineage from raw idea → filed molecule stays traceable), and mark each cut/deferred idea bead with the reasoning from the judgment pass — so `bh:brainstorm`'s raw pool doesn't silently orphan. There is no first-class `bh work` verb for annotating a bead, so this uses the `bh bd` passthrough, which is disabled by default; if it is, hand the operator the list of idea ids with the epic link or reasoning for each rather than overriding the gate.

## What NOT to do

- Never call `bd create`/`bd update` directly for a spike or implementation molecule.
- Never skip the decision bead on a spike molecule.
- Never file an implementation molecule for an idea with a genuinely open feasibility question "just to get moving" — that's precisely the mistake the spike loop exists to prevent.
- Never file the entire idea pool without a human accept/cut/reorder pass first.
