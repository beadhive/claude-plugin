# beadhive-retro — metric definitions

Single source of truth for how each metric is computed and how ambiguous cases are labelled.
`scripts/analyze.py` implements this file exactly; if the two disagree, this file is the spec —
fix the script. Six metric families:

## (a) Bead lifecycle verb mapping

A bead's lifecycle is inferred from `bd`/`bh` Bash commands and `bh:*`/`beads:*` Skill
invocations found in tool events (see extract.py). A bead id (matched by `BEAD_ID_RE`, see (b))
present alongside one of these verbs classifies the event:

| Verb (command prefix) | Lifecycle stage |
|---|---|
| `bd create`, `bh plan` (any subcommand) | **planned** |
| `bh work submit`, `bd close` | **implemented** |
| `bh work merge` (incl. `--group` / `--molecule` / `bh work finish`) | **merged** |

A session can contribute multiple stage events for the same or different beads; `analyze.py`
counts per-stage occurrences, deduplicated by `(stage, bead_id)` pair so a resubmitted bead only
counts once per stage.

## (b) beads/bh tool grouping rule

Every tool event is classified into exactly one of two buckets:

- **beads/bh** — a `Bash` command whose text (after stripping leading `cd ... &&` chaining)
  starts with `bd` or `bh`, OR a `Skill` invocation whose `input.skill` starts with `bh:` or
  `beads:`.
- **other** — every other tool event (Read, Write, Edit, Grep, Glob, WebFetch, Task, other Bash,
  other Skills, …).

This rule feeds metric (2) (failed tool calls) and (3) (skill reads).

**Bead-id shape** (`BEAD_ID_RE`): `\bbh-[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[0-9]+)?\b` — a literal `bh-`
prefix followed by one or more dash-separated lowercase alnum segments, with an optional `.N`
child suffix (matches this hive's `bh-cp-jlk`, `bh-cp-jlk.2`, and other Beadhive hives' `bh-n5z3`
style ids). This is a **heuristic**: it only catches ids that literally start with `bh-`; a hive
using a different prefix convention (e.g. `ag-infra-1`) will undercount. Good enough for the
"any bh-xxxx-shaped id" Beadhive-usage signal in identify.py; not a general bead-id parser.

## (c) Token categories

**Exact** (from `message.usage`, no estimation): `input_tokens`, `output_tokens`,
`cache_read_input_tokens`, `cache_creation_input_tokens` (further split into
`cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens`). Percentages in
metric (4) are `category_sum / (input + output + cache_read + cache_creation)` summed across the
session set.

**Approximate file-IO split** — read-from-file vs write-to-file tokens, estimated as
`chars / 4` from content sizes extract.py collects (`tool_result` content chars = read-from-file
family; `Write`/`Edit` `input` chars = write-to-file family). **This is a rough approximation,
not per-tool token precision** — the `usage` field never reports which tool call an input token
belongs to, so this number is a byte-derived estimate only, and every surface that reports it
(script output, `report.md`) must label it `"approximate": true` or an equivalent note. Never
present it as exact.

## (d) Cache-ratio formula and expiry-significance threshold

**Cache ratio** (a session or the whole window): `cache_read_input_tokens / (input_tokens +
cache_creation_input_tokens)` — the share of context that was served from cache versus fed fresh
(cold input + re-created cache). Computed per-session and as a window-wide aggregate (sum of
numerators / sum of denominators, not an average of ratios).

**Cache-expiry event**: walking a session's ordered usage series (one entry per assistant
message), a turn `t` (with previous turn `t-1`) is flagged as a cache-expiry event when **all**
of:

1. **Idle gap**: `timestamp(t) - timestamp(t-1) >= 5 minutes` (the ephemeral 5m cache TTL —
   using the shorter TTL is the conservative/more-sensitive choice for detection).
2. **Cache miss**: `cache_read_input_tokens(t) <= cache_read_input_tokens(t-1) / 2` — the served
   cache collapsed relative to the prior turn (a same-size or growing cache_read means the cache
   was still warm despite the gap).
3. **Re-creation spike**: `cache_creation_input_tokens(t) >= 5000` — the turn had to feed a
   non-trivial amount of context back in fresh.

**"Significant"** (numerically): a flagged event's **wasted tokens** = `cache_creation_input_
tokens(t)` (what had to be re-fed that a still-warm cache would have served from `cache_read`
instead). An event is **significant** when wasted tokens `>= 10000` — large enough that a fresh
session handoff at the gap boundary would plausibly have been cheaper than resuming the stale
one. Non-significant flagged events (5000–9999 wasted tokens) still count toward the expiry-event
total but are not called out individually in the report.

## (e) Activity-signal heuristics

Per assistant turn, `analyze.py` increments a signal counter based on the turn's tool events
(non-exclusive — a turn can raise more than one signal; the per-session **suggested** label is
the argmax, defer-to-agent per SKILL.md):

| Signal | Raised by |
|---|---|
| **planning** | A `Skill` event with `input.skill` matching `bh:planner`, `bh:plan`, or `bh:replan`; or a `bd create` / `bh plan` Bash command (see (a)). |
| **implementing** | An `Edit`/`Write`/`NotebookEdit` tool event co-occurring with a `bh work` Bash command (claim/submit/etc.) anywhere in the same session — i.e. the session is under active `bh work` lifecycle while files change. |
| **diagnosing** | `Read`/`Grep`/`Glob`/test-running `Bash` (command containing `test`, `pytest`, `check`, or the rig's validation command) tool events on a turn with **zero** `Edit`/`Write` events. |
| **fixing** | An `Edit`/`Write` tool event on a turn where the **immediately preceding** tool_result (any tool) had `is_error: true`, or the preceding assistant turn's Bash tool_result text matched a failure pattern (`FAIL`, `Error`, non-zero test exit noted in text). |

Diagnosing vs. fixing is inherently fuzzy (a diagnosing turn can flip to fixing mid-session); the
script emits **counts**, not a forced single label — SKILL.md's workflow step resolves the final
per-session label with judgment, using these counts as evidence, not as ground truth.
