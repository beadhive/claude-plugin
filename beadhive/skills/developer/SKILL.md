---
name: developer
description: >-
  Role guide for a DEVELOPER — an agent assigned a single bead to
  implement and take to a reviewable state. Use when an agent has been assigned or has claimed
  a bead and is about to start coding in a bh-managed repo, or would otherwise reach for
  `git clone` / `git checkout -b` / `gh pr create` to begin a task. Pairs with the `work`
  skill for the `bh work` verb mechanics.
---

# Developer — take one bead to reviewable

Your duty: turn one assigned bead into a small, validated, reviewable change. You do **not**
dispatch work (that's the Dispatcher) or merge it (that's the Merger).

Load the **`work`** skill for verb details, then:

1. `bh work brief <id>` — understand the requirements and the printed validation command.
2. `bh work claim <id>` — your ack; it gives you a worktree with identity + signing already
   stamped. **Don't `git clone` / `checkout -b`** — the branch is already `wt/bead/<id>`.
   `cd "$(bh worktree path --bead <id>)"`.
3. **Route structural work before editing.** For a behavior-preserving restructure, extraction,
   responsibility move, or coupling reduction, load `bh:refactor` and follow its execution mode.
   For an explicit internal module boundary, port/interface, independently testable subsystem, or
   test-closure isolation, load `bh:modularize`; it loads and strictly extends `bh:refactor`.
4. Implement with normal git **inside the worktree** (commit freely — it's scratch space).
   Tip: `git commit --fixup=<target>` as you go.
5. **Self-refine** before handoff: `bh work show <id>` to see the noise, then
   `bh work refine <id> --autosquash` (or `--plan`/`--since`) to squash checkpoints into a
   few clean conventional digests. It's a safe rewrite (backup branch + byte-identical gate),
   so `submit`'s history guard passes.
6. `bh work check <id>` — run validation; fix until green. See
   [Self-testing before submit](#self-testing-before-submit--trust-the-gate-dont-duplicate-it)
   for when to also test by hand versus when that's redundant with this step.
7. `bh work submit <id>` — hand off to async review. **Submit is not "done"**; your branch
   is the durable handoff, so don't rely on the worktree directory surviving.
8. `bh work resume <id>` — if review returns changes-requested; address it and re-submit.

Rules: stay inside the worktree; never push `main`, open a PR, or run the merge.

## Self-testing before submit — trust the gate, don't duplicate it

`bh work check` runs the hive's real validation in your worktree, and `submit` re-runs it
from a clean checkout and records a tree-keyed verdict that later boundaries reuse instead of
re-running (Attested Green, bh-ku9n9) — so hand-testing the same thing a third time is, by
default, wasted wall-clock rather than added safety. That trust rests on two fixes:
`review --run` no longer prints a false green against a stale branch in batch mode
(bh-87ktb), and a transient network blip in the license gate is no longer recorded as a real
policy failure (bh-u9ip). If either regresses, the old caution below is rational again.

- **Redundant — skip it:** re-running the full `just check` (or equivalent) locally right
  before `submit` on an ordinary change with existing coverage. `check` and `submit` already
  run it; a third identical run just delays the same verdict.
- **Still warranted:**
  - a genuinely novel or risky change (new subsystem, concurrency, a migration) where a
    failure would be expensive to trace after the fact from the gate's output alone;
  - a change touching a path with no existing test coverage — write and run a targeted test
    as part of implementing it, not as insurance against the gate;
  - localizing a failure the gate already reported, with a narrower targeted rerun (e.g.
    `uv run pytest tests/test_x.py::test_y -x`) — diagnosis, not a full-suite repeat
    "just in case."

## Hitting a tool bug — bottom rung

If you hit a `bh` / `bd` / tool bug while working, fire a one-liner to HQ and keep going:

```sh
bh escalate '<what happened> with <tool>'
```

Fire-and-forget — do not stop to route or investigate. HQ queues it as `origin:escalation`;
the director picks it up from `bh hq intake` and decides where it lands. Your job is the
bead, not the bug.

## Batch (work-group) path

When the dispatcher assigns a `batch:<group>` of beads to you as a unit, use this opt-in
path. The default single-bead flow above is unchanged and is always the default.

**1. Claim the group** — one shared `wt/batch/<group>` worktree for every member:

```sh
bh work claim --group <id1>,<id2>[,...] --as dev/<name>
```

The command prints the worktree path and the group name. `cd` there immediately:

```sh
cd "<path-printed-by-claim>"
```

**2. Implement serially** — for each member in order, edit that bead's scope then commit
with a clean conventional subject:

```sh
git add -p
git commit -m "feat(scope): what and why"
```

One or more conventional commits per bead is fine. Keep them clean from the start —
`bh work show` and `bh work refine` target per-bead branches (`wt/bead/<id>`) and are not
available for batch members. Checkpoint noise must be squashed with plain `git rebase -i`
before handoff.

**3. Validate once** — run the hive's validation command directly in the batch worktree:

```sh
just check
```

`bh work check <id>` looks for `wt/bead/<id>` and won't find the batch worktree; run the
hive command directly until it's green.

**4. Hand off the group** — once validation is green, submit the whole batch from the shared
worktree:

```sh
bh work submit --group <id1>,<id2>[,...] --as dev/<name>
```

Group submit validates the shared branch once from a clean checkout, checks the relaxed history
budget (`max_commits × members`), and opens exactly **one** review gate naming every member.
Approval or bounce can target any member because they all share that gate. This is your handoff;
the reviewer runs `bh work approve <any-member>` or `bh work bounce <any-member> -m "…"`, and the
merge owner eventually runs `bh work merge --group <id1>,<id2>[,...]`. You never approve or merge
your own submission.

**Batch rules:** stay in the shared worktree (`wt/batch/<group>`). Per-bead
`bh work submit <id>` is still wrong for batch members — use `submit --group` once for the whole
set. Never open per-bead branches, approve or merge your own submission, or touch another group's
worktree.
