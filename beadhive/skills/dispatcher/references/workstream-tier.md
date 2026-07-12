# Workstream tier (epic-of-epics) + recursive dispatch

## The tier model

A **workstream** is just an ordinary `issue_type=epic` bead whose children are themselves epics —
**no new issue_type**; the tier is the bead's position in the dotted id (`<bh>.<epic>.<issue>`), and
the `epic` type marks a container / dispatcher seat at *every* tier. So a workstream reuses ALL
epic machinery (seat, `start`/`finish`, seat guard, the `wt/bead/epic/…` namespace) with zero new
rules; only two namespaces ever exist — `wt/bead/epic/…` (container, any tier) and `wt/bead/issue/…`
(leaf). The land model is **one recursive rule**: `finish <container>` lands `wt/bead/epic/<container>`
onto `integration_base(<container>)` — the nearest started container ancestor, else `main`. So a leaf
lands on its epic, an epic lands on its workstream, and the workstream lands on `main`; the same
staleness / rollback / `safe_to_rewrite` safety generalizes up the chain (an intermediate,
local/unpushed container rolls back losslessly; only the final `→ main` land is fixed forward).

The seat is **tier-aware and recursive**: a *main dispatcher* seats `wt/bead/epic/<epic>` off
`main`; a nested *epic dispatcher* seats `wt/bead/epic/<bh>.<epic>` off its **workstream**
container. `finish` lands your container **up one level** — onto `main` for a top-level epic, onto
the workstream container for a nested one — then tears the seat down (removes the worktree,
deletes the container branch). Developers own no remote branch — only a local
`wt/bead/issue/<id>`.

## Dispatch by child TYPE (epic → nested dispatcher; issue → developer/collapse)

Route each ready child by its **type**, the same `_is_epic` check the assign seat guard uses
(`bh work schedule <epic>` computes this — child epics come back under `coordinators`, leaves under
`groups`/`singletons`):

- A ready **child epic** (a molecule — e.g. an epic under a workstream) → dispatch a **nested
  dispatcher** `Task` (`subagent_type: "dispatcher"`), seated on that child epic. It runs **the
  same dispatch loop one tier down** (forks its children off `wt/bead/epic/<child-epic>` via
  `integration_base`), then **self-lands** via `finish <child-epic>` onto **your** container
  (`integration_base` one tier up) and **reports back** its landed container + closed status.
- A ready **leaf issue** → the developer / collapse path, exactly as in the main loop.

> **Naming disambiguation (important).** A **nested dispatcher** is the EXISTING `dispatcher`
> agent type reused **recursively** (tools: `Task, Bash, Read, Grep, Glob, Skill` — an orchestrator,
> no `Edit`/`Write`). It is **NOT** a new agent type, and **NOT** the collapsed
> `dispatcher @ batch` mode (that is a collapse **implementer** — it holds `Edit`/`Write` and
> does beads itself). The two are **orthogonal axes** that compose via `work.dispatch.*`: the
> **tier axis** (workstream → nested dispatchers → each fans out or collapses its own issues) vs.
> the **collapse axis** (within one epic: fan out developers vs. one implementer seat). A nested
> dispatcher may itself pick `collapsed` for its leaf issues or `fanout` (developers).

> **Bounded nesting.** The *branch/land* hierarchy is N tiers deep, but **live `Task`
> nesting is capped by `work.dispatch.max_depth`** (≤ 2 today) — the shared Task-nesting budget. A
> workstream dispatcher (root) → nested epic dispatcher (`Task`, depth 1) → developer (`Task`,
> depth 2) fits. A **deeper** tier (super-workstream → workstream → epic → dev) exceeds the cap and
> **runs as its own supervised session** (its own root dispatcher on its container branch), not a
> nested `Task`. Don't expect infinite nesting.

> **Self-land + report-back contract (asymmetry vs. a developer).** A *developer* submits and **you
> merge**; a *nested dispatcher* **self-lands** — its `finish` already merged the child epic onto
> your container — so you **do NOT re-merge** a child epic. You only **track** its completion, and
> when all your child epics are landed + closed you run `finish <your-container>` to land one tier
> up.
