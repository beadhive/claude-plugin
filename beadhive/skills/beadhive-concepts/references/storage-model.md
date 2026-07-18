# Storage & data model — hives, Dolt refs, backends, HQ / Head Office / hub

How the factory stores issue state, distributes it to agents, and aggregates it across repos.

## Hive — one beads DB per repo

A **hive** is a single repo's beads database, embedded as Dolt under the repo's gitignored
`.beads/`. Each repo is its own hive; all authoritative writes happen in the hive. Work is homed
*with* the code — ownership and sync follow the repo, and repos move between hosts and orgs
independently.

Issues are named by the hive's **prefix** — a permanent, short handle (`ag-infra-1`,
`workspace-7`) derived from the **stable** part of identity (`org` + `repo`) and deliberately
excluding `provider`, the dimension most likely to change (github → gitea). A host switch is a
label edit, not a prefix migration.

**Identity lives in labels, not the prefix.** Every issue carries a `provider:` / `org:` /
`repo:` **triplet** — the hive's registered identity, applied automatically by `bh bd create`.
Because `bd list` has no prefix filter, labels are how you slice the aggregated cross-hive view.
Orthogonal dimensions (`component:`, `phase:`, `tag:`, …) filter further. The guiding rule: the
prefix is stable; labels carry current truth, so a provider or org change is a label edit rather
than data surgery.

## Issue state on `refs/dolt/data`

Beads stores issue history under **`refs/dolt/data`** on the *same git remote as the code* — a
separate ref namespace that never touches `refs/heads/*` (branches and PRs). Consequences:

- **No database to provision and no server to run.** `bh bd dolt push` publishes a hive's data;
  a fresh clone runs `bh` bootstrap to pull it.
- **Backup rides the mirror.** Wherever the repo is mirrored carries the beads history too, as
  long as the mirror carries `refs/dolt/data`.
- The optional local Dolt SQL server is **not** part of this path — it is opt-in infra for a
  shared/central backend, never required.

## The `.beads` stance — what is tracked, what is never committed

The `.beads` directory is split deliberately so bead state distributes cleanly without leaking
into code branches:

- **Binary-managed, never committed** — the embedded Dolt DB, its locks, and its backups. These
  are managed by the backend and stay out of git entirely.
- **Tracked** — `issues.jsonl` plus the hive config, so Factory HQ can hydrate a hive's issues from
  a plain checkout.
- **Stealth-excluded** — forks and external hives _(roadmap)_ exclude even the tracked `.beads`
  artifacts, so factory metadata never enters an upstream PR.

**Why this avoids worktree / code-branch merge conflicts.** Bead state rides `refs/dolt/data`, a
namespace disjoint from `refs/heads/*`. A claim, a submit, or a close writes bead state on the
Dolt ref while a worktree's code change writes on `refs/heads/*` — two disjoint namespaces, so
they never collide. Concurrent bead writes are resolved by **Dolt ref-merge**, not by git
text-merge, which is exactly why claiming or closing a bead never conflicts with a code merge in
a worktree.

## Pluggable jsonl backends _(roadmap)_

The storage engine is a pluggable backend over a common **jsonl interchange**
(`.beads/issues.jsonl`). Multiple trackers — `bd`, `br`, `bw`, and `nodb` — implement the same
interchange, so a hive selects its engine with `bh beads switch <bd|br|nodb>` while every other
verb stays identical. The jsonl file is the stable contract between engines; the choice of engine
is a per-hive detail. The phased design for this lives in the repo's
`docs/design/bead-backend-abstraction.md`, with the engine comparison in `docs/BEAD-BACKENDS.md`.

## Factory HQ vs Head Office vs hub — three distinct things

These three names are often confused. They are separate mechanisms:

- **Factory HQ** — the durable cross-hive beads store at `~/.beadhive/hq/`, queried with `bh hq …`
  (`bh hq bd ready` for actionable work across the whole workspace). It subsumes the hub;
  `bh hub` is a **deprecated alias** of `bh hq`.
- **hub** — the internal aggregation *mechanism* at `~/.beadhive/hub`: a disposable read-cache built
  from every registered hive via beads' multi-repo hydration. Authoritative data always stays in
  each hive; the hub is just the read view that powers HQ.
- **Head Office** — the workspace **registry** at `~/.beadhive/config.yaml` (its `managed_repos` list).
  It records one entry per registered hive — `{provider, org, repo, prefix, kind}` — and is the
  single source of truth for which hives exist.

### `bh sync` mechanics

`bh sync` builds and refreshes the aggregate from `managed_repos`. For each hive:

- **cloned** (its `.beads/` exists locally) → added by **local path**.
- **uncloned** → fetched into a **minimal-clone cache** (`--filter=blob:none --no-checkout`,
  blobless, no working tree) that pulls only `refs/dolt/data` — just the beads data, ~tens of MB
  per hive — then added by that cache path.

So a hive's issues are browsable with its code never checked out, and a hive switches from the
cache to its live checkout automatically once cloned and re-synced.

## Hive kinds

A hive is classified at onboard time, which drives prefix derivation and whether beads is on:

| Kind | Detected when | Prefix | beads |
|---|---|---|---|
| **org-native** | path org has a required policy | `<code>-<repo>` (enforced) | on |
| **personal** | personal account, kept long-term | `<code>-<repo>` (suggested) | on |
| **prototype** | personal account, org undecided (default) | bare `<repo>` | on |
| **fork** | the repo is a fork | upstream identity | off unless opted in |

**External hives** _(roadmap)_ add a first-class `kind=external`: our virtualized view of a repo
outside the factory boundary, forked-and-PR'd rather than pushed directly. External hives feed the
Contribution plane — see [beadflow-and-planes.md](beadflow-and-planes.md).
