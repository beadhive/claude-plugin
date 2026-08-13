# retro — metric definitions

Single source of truth for how each metric is computed and how ambiguous cases are labelled.
`scripts/analyze.py` (families (a)–(j), `analysis.json`) and `scripts/wallclock.py` (family (k),
`wallclock.json`) implement this file exactly; if the two disagree, this file is the spec — fix
the script. Eleven metric families:

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
cache_creation_input_tokens)` — ratio of cache-read tokens to freshly-fed tokens (cold input +
cache writes); >1× means more reuse than fresh feeding, higher is better. Computed per-session
and as a window-wide aggregate (sum of numerators / sum of denominators, not an average of
ratios).

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

## (f) Model attribution (ts→model join)

Each `usageSeries` entry already carries the `model` id that produced it (extract.py reads
`message.model` off the assistant record). A `toolEvent`, however, has no `model` field of its
own — it shares the `ts` of the assistant turn that emitted it, so `analyze.py` builds a
`ts -> model` index from a session's `usageSeries` and looks up each `toolEvent`'s model by that
shared timestamp. This works uniformly for main-chain and `isSidechain` events (e.g. a fanout
developer sub-agent's own tool calls carry `isSidechain: true` but still share a `ts` with their
own assistant turn's usage entry).

This is an **approximate** join: if two assistant turns in the same session share an identical
timestamp (sub-second collisions), the later one wins the lookup. `models.beadsByModel` —
lifecycle events (see (a)) attributed to the model active at that event's `ts` — is labelled
`"approximate": true` in `analysis.json` for this reason.

Model ids are mapped to a pricing **family** by substring match against `pricing.json`'s
`models` keys (e.g. `"claude-sonnet-5"` → `sonnet`, `"claude-opus-4-…"` → `opus`,
`"claude-haiku-4-…"` → `haiku`). A model id matching no known family is **not** silently merged
into a default family — it is counted separately and, for cost purposes, into `cost.unpriced`
(see (g)).

## (g) Cost estimation

**Transcripts carry no raw cost** — Claude Code session JSONL never includes a `costUSD` field —
so all cost in `analysis.json` is **estimated** from `references/pricing.json`, a small
user-editable rate table (`asOf`, per-family `inputPerM`/`outputPerM`, and `cacheMultipliers`).
Every cost figure in the report or `analysis.json` must be labelled an estimate; never imply
billed precision.

Per model family `f` (from the ts→model join in (f)), summed over that family's `usageSeries`
entries:

- `inputCost(f) = input(f) / 1_000_000 * inputPerM(f)`
- `outputCost(f) = output(f) / 1_000_000 * outputPerM(f)`
- `cacheReadCost(f) = cache_read(f) / 1_000_000 * inputPerM(f) * cacheMultipliers.read`
- `cacheWriteCost(f) = eph5m(f) / 1_000_000 * inputPerM(f) * cacheMultipliers.write5m`
  `+ eph1h(f) / 1_000_000 * inputPerM(f) * cacheMultipliers.write1h`
- `totalCost(f) = inputCost(f) + outputCost(f) + cacheReadCost(f) + cacheWriteCost(f)`

`cost.byModel` reports these four components plus `totalCost` per family; `cost.total` sums
`totalCost` across all priced families. `cost.currency` is always `"USD"`, `cost.pricingAsOf`
echoes `pricing.json`'s `asOf`, and `cost.approximate` is always `true` with a `note` restating
the no-raw-cost caveat. A model id whose family isn't in `pricing.json` contributes its raw token
counts to `cost.unpriced` instead of being dropped or guessed at.

**Cache-waste tie-in**: `cost.cacheWasteUSD` prices the wasted tokens from every
`cache.expiryEvents` entry (see (d)) at that event's model family's cache-**write** rate, split
by the turn's actual `wastedEph5m`/`wastedEph1h` TTL buckets rather than a flat 5m assumption
(`wastedEph5m / 1_000_000 * inputPerM(f) * cacheMultipliers.write5m + wastedEph1h / 1_000_000 *
inputPerM(f) * cacheMultipliers.write1h`) — a wasted 1h-TTL write costs more per token than a
5m one, so pricing them the same would understate real 1h-cache waste. This turns the existing "a
fresh handoff would've been cheaper" call-outs into a dollar figure, most usefully quoted beside
`significant: true` events.

## (h) `meta` block

`analysis.json`'s `meta` family carries run provenance, not a metric — FOUR distinct
version fields plus two provenance fields, all best-effort (subprocess/file reads that
never raise; each falls back to the literal string `"unknown"` on any failure):

- `bhVersion` — the bh CLI's own version: `bh --version`, falling back to `bh version`
  (some releases expose it as a subcommand instead).
- `pluginVersion` — the bh claude-plugin's version: read from the installed plugin's
  `plugin.json` (resolved relative to this script — the offset from
  `scripts/analyze.py` to the plugin root's `.claude-plugin/plugin.json` is the same for
  a dev checkout and the installed plugin cache), falling back to parsing `claude plugin
  list` for the `bh@<marketplace>` entry.
- `bdVersion` — the bd CLI's own version: `bd version`.
- `ccVersions` — the union of every session's `ccVersions`, i.e. the distinct Claude Code
  build(s) seen in the analyzed window (see extract.py).

These four were previously conflated: `bhVersion` used to fall back to `bd version` when
`bh` wasn't on PATH, silently mixing the two tools' versions into one field. They're now
independent — `bhVersion` and `bdVersion` never substitute for each other; each is
`"unknown"` on its own if its own probe fails.

`meta` also carries `pricingAsOf` (echoing `pricing.json`) and `generatedAt` (analysis run
timestamp, UTC ISO 8601). The maintainer-recommendation stamp in (i) below now cites
`bhVersion`, `pluginVersion`, and `bdVersion` together (not just `bhVersion`).

## (i) Two-tier recommendation taxonomy

The report's recommendations section (SKILL.md step 4) splits into two audiences, because a
usage-pattern fix and a product fix have different owners and different shelf lives:

1. **Usage-pattern recommendations** (for the Beadhive **user** running this retro) — grounded
   directly in this run's numbers: e.g. "session X used opus for a mechanical task the numbers
   show sonnet handled fine elsewhere" (from `models`/`cost`), "handoff at the significant expiry
   event in session Y would have saved ~$Z" (from `cache.expiryEvents` + `cost.cacheWasteUSD`),
   "batch N similar beads instead of fanning them out" (from `activity`/`lifecycle`), a cluster of
   failed `bd`/`bh` calls, or a skill re-read repeatedly (`skillReads`). These are actionable
   *this run*, on *this* Beadhive version, and don't need a version stamp.

2. **Beadhive product-improvement recommendations** (for Beadhive **maintainers**) — a pattern in
   the data that points at a Beadhive tooling gap (e.g. a `bh`/`bd` command failing repeatedly in
   a way user-side retries can't fix, a skill that's clearly hard to discover given re-read
   counts). Each maintainer item is **stamped** `observed on bh <meta.bhVersion> (CC
   <ccVersions>)` — because the underlying bh/bd release may already have shipped a fix by the
   time the report is read, the stamp lets a maintainer immediately tell whether the observation
   is stale. Include a short paste-ready machine-readable handoff block (e.g. the offending
   command, the error text, the session id) so a maintainer can act without re-deriving it from
   `analysis.json`.

## (j) Tool-call classification (`toolClasses`)

Every `toolEvent` (across every session) is classified into exactly one of four classes by
`classify_tool_event()` — the single function `toolClasses` and the skill-invocation 3-way
breakdown in `skillReads.byClass` both call, so the two never disagree on where an event lands:

| Class | Matches |
|---|---|
| **beadhive** | A native `bh <verb>` Bash call that is **not** `bh bd`/`bh git` (e.g. `bh work …`, `bh plan …`, `bh rig …`); or a `bh:*` Skill invocation. |
| **raw-beads** | A direct `bd …` Bash call, **or** a `bh bd …` passthrough — both reach for beads directly, bypassing bh verbs; or a `beads:*` Skill invocation. |
| **raw-git** | A direct `git …` Bash call, **or** a `bh git …` passthrough. |
| **other** | Everything else — non-bd/bh/git Bash, other Skills, Read/Write/Edit/Grep/Glob/…. |

`raw-beads` and `raw-git` each carry a **direct vs. passthrough** sub-split (`direct` = the bare
`bd …`/`git …` form; `passthrough` = the `bh bd …`/`bh git …` form) — both sub-cases reach for the
raw tool instead of a native `bh` verb, but the passthrough form at least stayed inside `bh`'s
CLI surface, so the split is worth keeping separate rather than collapsing it away. A Skill event
classified `raw-beads` (a `beads:*` skill) has no passthrough concept and is bucketed under
`direct`.

`analysis.json`'s `toolClasses` reports, per class: `total` and `failed` call counts, a `byTool`
breakdown (keyed by skill id for a `Skill` event — the granularity the skill-invocations chart
needs — or by tool type, e.g. `Bash`/`Read`/`Edit`, for everything else, matching what the
failures chart already used), and (for `raw-beads`/`raw-git` only) `direct`/`passthrough`
sub-totals in the same `{total, failed}` shape.

**Direct `git …` capture**: `extract.py`'s command-detail regex (previously `bd`/`bh`-prefixed
commands only) now also captures a bare `git …` Bash command's text, so a direct git call is
visible to `classify_tool_event()` at all — before this, only `bh git …` passthrough calls (which
already matched the `bh`-prefix capture) carried command text; a plain `git commit` would have had
no `detail` and silently fallen out of every classification. `bh`'s own passthrough form was
always captured (it starts with `bh`); this closes the gap for the direct form.

**Back-compat**: the pre-existing `failures` (`beadsBh`/`other`) and `skillReads`
(`invocations.bhBeads`/`invocations.other`) keys are **unchanged in value** — they still use the
original 2-way `bd`/`bh`-prefix check (`is_beads_bh`), which counts a `bh git …` failure as
`beadsBh` even though `toolClasses` now buckets it under `raw-git`. `toolClasses` and
`skillReads.byClass` are additive, not a replacement.

**Concrete failure examples**: `failures.examples` is a bounded (`FAILURE_EXAMPLE_LIMIT = 5`)
list of actual failing tool calls — `sessionId`, `ts`, `tool`, `class`, `detail` (the offending
command), and `errorText` — so a maintainer-facing recommendation can cite a real instance
instead of just an aggregate count. It is the first five **chronologically**, kept for
back-compat; prefer `failures.groups` below.

**Ranked failure clusters** (`failures.groups`): the same failures grouped by *command shape* and
*error signature*, ranked by count — "this failed 6 times" rather than five arbitrary early
examples (in the 2026-08-13 window, four of the first five were unrelated Claude Code classifier
denials while the largest real cluster never surfaced). Ranking is two-level: command shapes by
total count, then signatures within a shape; equal counts keep first-seen order.

- **Command shape** — the invocation with run-specific noise collapsed to placeholders: bead ids
  and shell vars → `<id>`, seats (`disp/claude`) → `<seat>`, paths → `<path>`, shas → `<sha>`,
  quoted strings → `<str>`, integers → `<n>`, redirections dropped. Hyphenated bd/bh subcommands
  (`set-state`) and flag names are preserved.
- **Error signature** — the same idea applied to the error text, but prose-safe: only digits,
  paths, shas, seats and the ids that appeared in *that failure's own command* collapse, so
  ordinary hyphenated words survive. Capped at `FAILURE_SIGNATURE_MAXLEN` — it is a grouping key,
  not the error itself.
- **Which failures group**: those with a `bd`/`bh` invocation **anywhere** in the command, reusing
  `extract.py`'s `BD_BH_TOKEN_RE` (`analyze.failure_invocation`). Never re-anchor on `argv[0]`: a
  `bd`/`bh` call routinely sits in a loop body or behind a `cd … &&`, and an argv[0]-anchored
  prototype found only 14 of the same window's 26 failures. `failures.groupsMeta.failuresGrouped`
  reports the covered count; a failing `bh:*` Skill invocation counts in `beadsBh` but has no
  command to shape, so it never groups. Grouping is presentation — it does **not** change
  `beadsBh`/`other`.
- **Exemplar**: each signature carries the first failing call it saw, with the **complete**
  `tool_result` text (`errorText`/`errorChars`) and the whole command — paste-ready into a bug
  report. `extract.py` writes the same records for *every* failure to `failures.jsonl`; only the
  inline copy on each tool event stays clipped at `ERROR_TEXT_MAXLEN` (300), which is what keeps
  `events.jsonl` bounded. `analysis.json` carries at most `FAILURE_GROUP_LIMIT` shapes ×
  `FAILURE_SIGNATURE_LIMIT` signatures.

## (k) Wall-clock timing model (`wallclock.py` → `wallclock.json`)

Transcripts carry no durations — only a `timestamp` per record, written when that record was
appended. `scripts/wallclock.py` (Phase 4) walks the sessions named by `identify.json` and
derives every duration in `wallclock.json` from a **gap between consecutive records**, never a
measured span:

- **inference** = `ts(last assistant record of a requestId) − ts(record before the first)` —
  includes model latency, thinking, streaming, and any retry/queue time.
- **tool** = `ts(tool_result record) − ts(assistant record carrying the tool_use)` — includes
  anything the harness did before/after the command, notably time the call sat in a permission
  prompt waiting on a human.
- **human idle** = `ts(human prompt) − ts(previous record)`, counted **only** when the previous
  assistant turn ended WITHOUT a `tool_use` (the agent had genuinely stopped, not merely between
  parallel tool calls).

Every family below states this **"derived from record gaps, not measured"** caveat
(`TIMING_CAVEAT`) verbatim in its own `note` field, not only here — a renderer or report must
never present a `wallclock.json` number as an observed span.

**Parallel tool-call overlap**: one assistant message can issue several `tool_use` blocks at
once; their `durationSec` values (each measured from the same assistant ts) sum to more than the
wall-clock time the batch actually occupied. `totals.toolSec` / `bySession[*].toolSec` use the
**batch span** (`max(result ts) − assistant ts`) to stay honest; `toolTime.byClass`/`byTool` sum
every call's `durationSec` individually and are labelled `inflated` relative to `totals.toolSec`
in `toolTime.byClassNote` — never present a `byClass`/`byTool` sum as the wall-clock time tools
occupied.

**`<task-notification>` exclusion**: a background sub-agent's completion notification is a
`user`-type record carrying `promptSource` — indistinguishable from a real human turn on that
field alone — but no human typed it. `is_human_prompt()` excludes any record whose text starts
with `<task-notification>`; getting this wrong misattributed 41h of background-agent runtime to
"parked" human idle in the prototype this script replaced.

### Human-idle classes and thresholds

Each idle gap is classified by `classify_idle()`, checked in this order (first match wins):

| Class | Condition | Threshold/set |
|---|---|---|
| `parked` | gap ≥ `PARKED_SEC` | 6h — the session was left overnight, not a decision stall |
| `answering-a-question` | the preceding assistant turn's tool set intersects `GATE_TOOLS` | `GATE_TOOLS = {AskUserQuestion, ExitPlanMode, EnterPlanMode}` |
| `approval-shaped` | reply matches `APPROVAL_RE` (yes/lgtm/go ahead/…) or is ≤ 24 chars and not a question | n/a |
| `direction` | none of the above | substantive typed guidance |

`humanIdle.recoverableSec` is the `approval-shaped` bucket's total seconds — the portion "a
supervisor-agent loop could plausibly have answered without a human."

### Other thresholds (`wallclock.py` constants, echoed in `wallclock.json`'s `meta.thresholds`)

| Constant | Value | Used by |
|---|---|---|
| `SLOW_TURN_SEC` | 180s | `inferenceRate.slowTurnCount`/`.top` — an inference turn worth naming |
| `MIN_TOKENS_FOR_RATE` | 200 tokens | excludes short, latency-dominated turns from the tokens/sec rate stats (`inferenceRate.ratedTurns`) |
| `APPROVAL_GATE_SEC` | 45s | `suspectedApprovalGate` — a normally-instant (`FAST_RE`-matching) command that took this long was probably parked in a permission prompt (heuristic, not observed — no permission event exists in the transcript) |
| `MERGE_WINDOW_SEC` | 20 * 60 = 1200s | `testChurn.mergeAdjacent` — a test/build/lint run this soon after a merge/submit command counts as merge-adjacent |
| `CHURN_MIN_RUNS` | 3 | `testChurn.repeated` — same normalized command run at least this many times in the window counts as churn |

### Family reference

`aggregate()`'s return dict has one top-level key per family below, plus `meta` (the timing model
and thresholds above, echoed for a renderer/report to cite instead of re-deriving) and
`bySession` (per-session
`spanSec`/`inferenceSec`/`toolSec`/`humanIdleSec`/`unattributedSec`/`testSec`):

| Family | Computes |
|---|---|
| `totals` | session-span split into `inferenceSec` / `toolSec` / `humanIdleSec` / `unattributedSec`, summed across sessions (concurrently-open sessions add, so this is **not** wall-clock elapsed time). `unattributedSec` = `span − inference − tool − humanIdle` — mainly background sub-agent (sidechain) activity and a session left open with no following turn to close the gap, neither of which produces a human-idle or tool-call record to attribute to. |
| `humanIdle` | `byClass` counts/seconds (see table above), `recoverableSec` (the `approval-shaped` total), and the top idle gaps by duration |
| `inferenceRate` | p25/median/p75 output-tokens/sec (over turns with ≥ `MIN_TOKENS_FOR_RATE` output tokens), `excessSecondsVsP75` (time that would have been saved had every rated turn generated at the p75 rate), and the slowest turns |
| `toolTime` | seconds by class/tool (`byClass`/`byTool` — per-call sum, labelled inflated vs `totals.toolSec`) and the slowest individual calls, overall and per test/build/lint class |
| `humanGate` | count/seconds of `GATE_TOOLS` calls — see the subset warning below |
| `testChurn` | `commands`/`repeated` (same normalized command run ≥ `CHURN_MIN_RUNS` times; `retestTaxSec` = seconds spent on runs 2..N) and `mergeAdjacent` (test/build/lint runs within `MERGE_WINDOW_SEC` of a merge/submit call, deduped by `mergeAdjacentUnique*` since overlapping windows can double-count a run) |
| `suspectedApprovalGate` | `FAST_RE`-matching commands that took ≥ `APPROVAL_GATE_SEC` — probably sat in a permission prompt (heuristic, labelled as inferred, not observed) |
| `plausiblyAutomatable` | `humanIdle.recoverableSec + humanGate.sec` — see below |

### `humanGate` is a SUBSET of `toolTime`, not a fifth partition of session span

This is the one relationship in `wallclock.json` most likely to be double-counted, so state it
plainly: `AskUserQuestion`/`ExitPlanMode`/`EnterPlanMode` block on a human answer but are recorded
as ordinary tool calls (`class: "other"`, since `classify_command()` only runs for `Bash`), so
their wait time is **already inside** `totals.toolSec` / `toolTime.byClass['other']` /
`toolTime.byTool` — invisible there as anything but ordinary tool execution. `humanGate` pulls the
same seconds back out as its own, separately reported figure — a labelled subset, not a new
bucket. **Do not add `humanGate.sec` on top of `totals.toolSec` or a `toolTime.byClass`/`byTool`
sum; that double-counts.**

`plausiblyAutomatable.sec` (= `humanIdle.recoverableSec` + `humanGate.sec`) answers a different
question than `totals` — "how much of this window could a supervisor-agent loop plausibly have
handled without a human" — deliberately excluding `humanIdle`'s `direction`/`parked` time (no
auto-approver should touch either). Because its `humanGateSec` component is already counted
inside `totals.toolSec`, `plausiblyAutomatable` is not a fifth slice additive with `totals`; it
answers its own question rather than partitioning session span.
