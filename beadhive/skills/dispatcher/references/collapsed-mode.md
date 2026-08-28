# @batch (collapsed) mode

> `work.dispatch.mode = collapsed` (or `auto` when the epic fits the budget)

You are **one** Task sub-agent that owns an **entire epic** in a single session. Instead of the
root dispatcher fanning out one developer per bead — N worktree setups, N sub-agents re-learning
context — you claim the whole ready set **once** and drive every bead sequentially in **one shared
collapsed worktree** on **one shared batch branch**. You implement the beads yourself.

Load the **`work`** skill for the verb mechanics. Two depth levels run this loop, chosen by the
root dispatcher via `work.dispatch.max_depth`:

- **Depth 1 (`dispatcher @ batch`)** — no Task, so no escape valve: every bead lands on the
  shared batch branch.
- **Depth 2 (`dispatcher @ batch` + `sub-dispatch:1`)** — same loop, plus Task, so it can kick
  ONE risky/conflicting bead back out to an isolated `wt/bead/issue/<id>` + developer sub-agent
  (see **The depth-2 escape valve** below).

The default dispatch mode is still **fanout** (one bead → one developer); this collapsed loop is
what the root dispatcher selects when `work.dispatch.mode` is `collapsed`/`auto` and the epic is
small enough to run in one session (`work.dispatch.max_beads_per_session`, default 8).

## Claim once

Take the whole epic's ready set as a single work-group — **one** shared worktree for every member:

```bash
bh work claim --group <id1>,<id2>[,…] --as dev/<name>   # explicit member ids
bh work claim --collapse <epic> --as dev/<name>          # or: batch the epic's un-batched
                                                         #     ready children for me
```

`--group` provisions the ONE shared `wt/batch/<group>` worktree, stamps your identity on it once,
and claims every member. `--collapse <epic>` is the shorthand for an epic the planner never
labelled: it synthesizes a `batch:<epic>` label on the epic's ready children, then claims them as
one group. Either way you get a single tree — `cd` there and **stay in it**:

```bash
cd "<path-printed-by-claim>"
```

## The loop — one shared tree, bead by bead

Walk the members in **dependency order**. For each bead:

1. **Implement** its scope in the shared worktree with normal git. Commit clean conventional
   subjects (`feat(scope): …` / `fix(scope): …`); one or more commits per bead is fine. Keep them
   clean from the start — `bh work show` / `bh work refine` target per-bead branches
   (`wt/bead/issue/<id>`) and are **not** available to batch members, so squash any checkpoint
   noise with plain `git rebase -i` before handoff.
2. **Self-check** — run the hive's validation directly in the batch worktree (`just check`).
   `bh work check <id>` looks for `wt/bead/issue/<id>` and won't find the shared tree; run the
   hive command directly until it's green.
3. **Move to the next bead.** A dependency chain is just the next commit on the same tree; there is
   no per-bead branch to open and no parallelism to buy.

## Submit and review once — batch-end

After every member is implemented and the whole shared tree is green, hand off the batch as one
unit:

```bash
bh work submit --group <id1>,<id2>[,…] --as dev/<name>
```

`submit --group` validates the shared branch once from a clean checkout and opens exactly **one**
review gate whose reason names every member. Do not submit members individually. Approval or
bounce may target any member because all members share that gate; a bounce blocks the whole group,
which must be fixed in the shared worktree and resubmitted with `submit --group`.

### Review gate — self vs fresh

`work.dispatch.review_mode` (config accessor `config.dispatch_review_mode`, default `self`)
decides who signs off the group's shared review gate before it can merge. Two modes ship; a third
(`paired`) is deferred and safely degrades.

### `review_mode: self` (default)

You **are** the review authority. After the group is submitted, self-resolve its one shared review
gate by approving any member — **no second Task is spawned**:

```bash
bh work approve <any-member> --as dev/<name>
```

This is legitimate because the
collapsed seat runs under a **live human watching the collapsed session**: that human is the review
authority, and the dispatcher/merge layer only checks the mergeable invariant — **no open gate,
not changes-requested**. A self-resolve satisfies that invariant exactly as an external approval
would; it is not a rubber stamp being smuggled past review, it is the human-in-the-loop review the
collapsed seat was designed around. Satisfy every member's acceptance criteria before approving.

### `review_mode: fresh`

The implementing session must **not** review its own work. After group submit, spawn **one distinct
reviewer Task for the whole batch**, with **fresh context**, independent of this implementing
session, receiving the member ids, shared branch/diff, and every member's acceptance criteria.
That reviewer approves any member with `bh work approve <any-member> --as <reviewer>` or bounces
any member with `bh work bounce <any-member> -m "…" --as <reviewer>`; either decision resolves the
one shared gate. Fix the shared branch and resubmit the group after a bounce. Merge only after the
shared gate is approved.

- **Spawning a Task requires depth 2.** `fresh` is only available with `sub-dispatch:1`;
  depth-1 collapsed holds no Task, so it cannot spawn an independent reviewer. If depth-1
  is configured with `fresh`, that's a dispatcher misconfiguration — surface it rather than
  silently self-reviewing.
- The reviewer is review-only: it never commits to the shared batch branch and never merges.

### `review_mode: paired` — out of scope, falls back to `fresh`

`paired` (two seats sign off) depends on the resumable-agent spike and is **not wired**. Selecting
it does **not** silently no-op: `config.dispatch_review_mode` normalizes `paired` → `fresh` and
emits a `review_mode_paired_fallback` warning through the log pipeline, so the bead still gets an
independent reviewer instead of an unreviewed gate. Treat a `paired` request exactly as `fresh`
(and heed the warning: paired isn't available yet).

## Merge — approved batch-end only, then finish

Land the whole collapsed set as **one** bubble at the **end** of the epic, never incrementally:

```bash
bh work submit --group <id1>,<id2>[,…]  # one validation + one shared review gate
bh work approve <any-member>            # self or fresh reviewer; bounce instead if needed
bh work merge --group <id1>,<id2>[,…]   # one --no-ff bubble into the epic's container branch,
                                         # closes every member
bh work finish <epic>                    # land wt/bead/epic/<epic> onto integration as one
                                         # bubble, close the epic
```

`merge --group` validates once from a clean checkout, merges `--no-ff` into the epic's container
branch `wt/bead/epic/<epic>` (per-bead commits preserved inside — lossless + bisectable), and
closes every member; its history budget is relaxed to `max_commits × members`. `bh work finish
<epic>` (alias of `bh work merge <epic> --molecule`) then lands the assembled molecule onto the
integration branch as one `--no-ff` bubble and closes the epic — the only step that touches `main`.

## The depth-2 escape valve (`sub-dispatch:1` only)

Only the depth-2 seat holds Task. For **one specific** bead that is genuinely risky or conflicting,
you may kick it back out to an **isolated** `wt/bead/issue/<id>` worktree driven by a **developer**
sub-agent (one `Task`, passing that bead's `model:`), while its siblings stay collapsed. This
reintroduces the per-worktree overhead collapse exists to avoid — use it sparingly, and never as a
back-door to per-bead fanout.

The kicked-out bead has strict, non-negotiable landing rules:

- **Its work must NEVER be committed onto the shared batch branch.** It lives only on its own
  isolated `wt/bead/issue/<id>` branch — quarantined from the collapsed tree.
- **It lands LAST, via the normal per-bead `merge()` path, against an already-updated container.**
  Order: `bh work merge --group` the collapsed siblings into `wt/bead/epic/<epic>` first, so
  the molecule is updated; then land the isolated bead against that updated container with the
  ordinary per-bead `bh work merge <id>`; then `bh work finish <epic>`.

## Hard rules

- **One shared worktree, one shared branch.** Stay in `wt/batch/<group>`; do not open per-bead
  branches for the collapsed beads or touch another group's worktree.
- **No incremental merge.** The collapsed set merges batch-end only, `--group` into the epic's
  container branch, then `finish`.
- **Depth-1 has no escape valve.** A bead needing isolation at depth-1 is out of scope — that
  requires `sub-dispatch:1`.
- **The kicked-out bead is quarantined** (depth-2): its commits never touch the shared batch
  branch, and it lands last against an already-updated container.
- **Never push `main` or open a PR.** Integration is the merge path (`merge --group` / per-bead
  `merge` / `finish`) — never raw `git push` of the shared branch.

## Partial-epic-failure recovery

Nothing has landed on integration until `merge --group`, so a mid-epic failure is recoverable
inside the session:

- **Prefer fix-forward.** If a bead breaks validation, fix it in place in the same shared worktree
  and re-run `just check`. The tree is scratch space until you merge — just keep going.
- **Fallback: reset-and-land-prefix.** If a bead can't be salvaged this session, `git reset` its
  commits off the shared branch so the tree holds only the working prefix, then land that prefix
  then `bh work submit --group <working-ids>`, resolve its shared review gate, and land it with
  `bh work merge --group <working-ids>`. Report the dropped bead back to the root dispatcher so it
  can be re-dispatched; never land a red bead to "make progress".
