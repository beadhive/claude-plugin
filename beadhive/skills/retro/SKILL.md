---
name: retro
description: >-
  Retrospective efficiency analysis over recent Claude Code sessions that used Beadhive. Use
  when asked "how did we do since the last reset", "what did the last week of Beadhive sessions
  cost", "how many beads got planned/implemented/merged", "which tool calls failed", "what's our
  cache-hit ratio", "where did we waste tokens re-feeding an expired cache", or "how did time
  split across planning/implementing/diagnosing/fixing". Runs a three-phase pipeline
  (identify → extract → analyze) over `~/.claude/projects/*/*.jsonl`, then synthesizes a report
  with real numbers — never hand-waves a retrospective from memory.
---

# retro — retrospective efficiency analysis

Answers "how efficient were our recent Beadhive sessions" with real numbers pulled from Claude
Code's own session transcripts, not vibes. Stdlib-only Python scripts do the scripted work
(identification, extraction, aggregation, and — opt-in — HTML rendering); you do the judgment
work (labelling ambiguous sessions, writing the narrative, picking recommendations).

## Run the pipeline, in order

From this skill's directory (`scripts/` is relative to `SKILL.md`):

```bash
python3 scripts/identify.py --since auto   # -> ~/.beadhive/retros/<run-id>/identify.json
python3 scripts/extract.py                 # -> extract.jsonl, events.jsonl, failures.jsonl (same run-dir)
python3 scripts/analyze.py                 # -> analysis.json in the same run-dir
```

No path args needed for the common case: `identify.py` creates a fresh, datetime-named run
folder under `~/.beadhive/retros/<YYYYMMDD-HHMMSS>-<hash8>/` (the id is derived from the run's
own `since`/`generatedAt`/session-count — see `scripts/_rundir.py`), writes `identify.json`
there, and points `~/.beadhive/retros/latest` at it. `extract.py` and `analyze.py` pick up that
same run-dir automatically via the `latest` pointer, so each run's five artifacts
(`identify.json`, `extract.jsonl`, `events.jsonl`, `failures.jsonl`, `analysis.json`) land
together and accumulate run-over-run for comparison.

`failures.jsonl` is one record per failing tool call, carrying the **complete** `tool_result`
text and the command exactly as it ran — the inline `errorText` on every event stays clipped at
`extract.ERROR_TEXT_MAXLEN` so `events.jsonl` doesn't grow with full stack traces. Quote a
failure from here (or from `analysis.json`'s `failures.groups[].signatures[].exemplar`) instead
of re-walking `~/.claude/projects`.

Pass `--since <iso>` to `identify.py` to override auto-window-detection with an explicit
boundary. Pass `--run-dir <dir>` (all three scripts) or `--out`/`--in`/`--events`/`--failures`
(individually)
to target an arbitrary directory instead — e.g. for an ad-hoc or CI invocation that shouldn't
touch `~/.beadhive/retros/` or the `latest` pointer. Each script also has `--selftest` — run it
if you change one of them; it must stay green.

**This is the acceptance bar for this skill**: invoking it must actually run all three phases
end to end and produce a report grounded in `analysis.json`'s numbers, not a summary written from
guesswork.

## Artifact mode: render report-artifact.html (or report.html) instead of the in-chat report

**Default behavior (no flag) is unchanged**: write the report inline in chat per the section
below. If the user asks for an artifact / file / HTML report (or says "artifact mode"), you have
**two possible branches** after `analyze.py` — a script can't introspect which skills are loaded
or whether Artifacts are enabled, so picking the branch is agent-time judgment, made explicitly
here. In **both** branches the actual chart-building is scripted and self-tested — you never
hand-author chart marks (a hand-built pass once shipped a bug where SVG marks were built via
`element.innerHTML` of bare `<rect>`/`<circle>` tags, which land in the HTML namespace and render
blank in Brave/Chromium; the macOS `open` preview happens to hide this, which is exactly why it
shipped — `--selftest` now asserts namespaced creation directly).

### Capability branch — is `dataviz` (and/or `artifact-design`) available, and are Artifacts on?

If **both** are true — `dataviz` and/or `artifact-design` appear in your available-skills
listing for this conversation, **and** Claude Artifacts are enabled — run the charted renderer:

```bash
python3 scripts/render_artifact.py   # reads <run-dir>/analysis.json -> <run-dir>/report-artifact.html
```

`render_artifact.py` resolves the run-dir the same way the other three scripts do (via the
`latest` pointer or `--run-dir`) and writes a single self-contained, interactive
`report-artifact.html` next to `analysis.json` — inline CSS + inline JS, **zero external refs**
(no CDN, no external fonts/scripts/stylesheets). Every SVG chart mark is built via
`document.createElementNS` against the SVG namespace, never via `element.innerHTML` of bare
`<rect>`/`<circle>` tags. Run `--selftest` if you ever touch the script — it must stay green.

**CLI-vs-canvas realization**: in a context with a real Artifacts canvas, *the Artifact* is that
canvas — open `report-artifact.html` and paste its contents into an HTML artifact so the canvas
renders it live (Claude Artifacts support inline HTML+JS directly, no build step). In Claude Code
CLI (no Artifacts canvas), "the Claude Artifact" is realized as this self-contained
HTML-with-JS file on disk instead — present its path and tell the user to open it. Either way it
is a distinct file from `render.py`'s JS-free `report.html` (the fallback below):
`report-artifact.html` is charted and interactive, `report.html` is tables-only and
framework-free with no JS at all.

`dataviz` is still worth loading for its color-by-job / accessibility / interaction *vocabulary*
(this skill's `references/palette.md` is the brand instance of its palette method) when narrating
or adjusting the artifact — but the chart construction itself is `render_artifact.py`'s job, not
something to re-derive by hand each run.

Chart form mapping baked into `render_artifact.py`, one row per `analysis.json` family (final
forms — the script implements every row below, including the scaling and color-job rules; this
is documentation of what the script does, not a menu to hand-implement):

| `analysis.json` field | Form | Color job |
|---|---|---|
| token split (`tokens.exact.totals`) | stacked bar | categorical (token category is unordered) |
| cache ratio + significant-expiry count (`cache.cacheRatio`, `cache.significantExpiryEventCount`) | hero stat tiles | n/a (single value) |
| `models.beadsByModel` | stacked bar | sequential/ordinal (planned→implemented→merged is a sequence) |
| `cost.byModel` | stacked bar (surface `cost.unpriced` explicitly, never drop it) | categorical (cost components are unordered) |
| `cost.cacheWasteUSD` | a stat tile beside the expiry call-outs | n/a (single value) |
| `activity` distribution | aggregate stacked bar + capped, sorted small multiples (one per session, top-N by activity — see scaling below) | status (planning/implementing/diagnosing/fixing are discrete states) |
| `cache.expiryEvents` | scatter/timeline — idle gap (x) × wasted tokens (y) | status (warning-toned points; magnitude via radius, not hue) |
| `lifecycle.byEpic` | top-N + "+N more" aggregate bar (see scaling below) | sequential/ordinal (planned→implemented→merged) |
| `failures` (colored via `toolClasses`) | stacked bar, beadhive / raw-beads / raw-git / other | categorical (tool class is unordered; palette slots 1-4) |
| `skillReads` (colored via `toolClasses`) | top-N + "+N more" aggregate stacked bar, beadhive / raw-beads / raw-git / other | categorical (skill identity + tool class, both unordered) |

**Scaling guidance (high-cardinality families)**: `lifecycle.byEpic` and `activity`'s per-session
small multiples are both unbounded by construction — a real run had ~81 epics and ~41 sessions,
so a plain "one bar per epic" / "one tiny chart per session" render is unusable.
`render_artifact.py` enforces a concrete cap for each: top 12 epics (sorted by total lifecycle
events) with the remainder folded into one aggregate "+N more" bar, and small multiples capped at
the top 24 sessions by activity volume with the remainder folded into one aggregate "+N more"
tile. `skillReads` gets the same top-12-plus-aggregate treatment. Aggregate bars/tiles render at
lower opacity with a dashed border to signal "rolled up, not a single real entity" — the
remainder is always folded into a visible aggregate, never silently dropped.

Legend for any chart with ≥ 2 series (categorical color from `palette.md`'s fixed slot order,
never cycled or reassigned); a table view alongside every chart for accessibility; dark mode
(the palette's dark columns) as the primary/default theme, matching `report.html`'s dark-first
default.

**Cost caveat on the visual itself**: `cost.unpriced` must never be surfaced only in prose —
`render_artifact.py`'s cost chart carries the estimate/under-count caveat as a footnote drawn
directly on the SVG bar chart itself (in addition to the section note above it), and the cost
table appends an explicit `unpriced` row rather than omitting the excluded model families. If you
ever hand-adjust the cost visual, keep this rule: the caveat must be legible on the tile/chart
itself, not only in the surrounding text.

Present the Artifact instead of `report.html` — don't also render and link the plain file when
the Artifact path is taken.

### Fallback — no dataviz/Artifacts

Without `dataviz`/`artifact-design` loaded, or without Artifacts enabled, run the fourth, opt-in
step after `analyze.py`:

```bash
python3 scripts/render.py   # reads <run-dir>/analysis.json -> <run-dir>/report.html
```

`render.py` resolves the same run-dir as the other three scripts (via the `latest` pointer or
`--run-dir`) and writes a single self-contained `report.html` (inline CSS, no JS framework, no
new dependencies) next to `analysis.json` — tables for every metric family plus the significant
cache-expiry call-outs and a two-tier recommendations section, all computed straight from
`analysis.json`. **This is on-brand by default, no flag needed**: `render.py` renders the
honeycomb palette from `references/palette.md` unless `--plain` is passed (an escape hatch to the
old unstyled gray theme — rarely needed). So the fallback is always on-brand, just less charted
than the Artifact path, with zero new runtime deps either way.

When artifact mode is requested (either branch), **present the artifact to the user instead of
writing the full report in chat**: give the rendered file's path (`report-artifact.html` or
`report.html`, whichever branch ran) — or show the Artifact directly if you pasted it into a
canvas — and tell them to open it. A short in-chat summary (a couple of headline numbers) is
fine, but don't re-paste the full per-section report — that's what the artifact is for. The
numbers must still be the same ones grounded in `analysis.json`; rendering just formats them.

## Stable data contract

`analysis.json` is the artifact input contract — for **both** branches above. It has one
top-level key per metric family: `lifecycle`, `failures`, `skillReads`, `tokens`, `cache`,
`activity`, `models`, `cost`, `meta` (formulas in `references/metrics.md`). `render_artifact.py`
binds to these fields directly rather than re-deriving numbers — the same grounding rule
`render.py` already follows: every value traces back to `analysis.json` verbatim. Treat this
family list as stable; if `analyze.py` ever adds or renames a top-level family, update this list,
`metrics.md`, and both renderers' family coverage together.

## Read `analysis.json`, then write the report

This section is the default in-chat report (no artifact flag). If artifact mode was requested,
skip straight to presenting `report-artifact.html` or `report.html` (see above) — the same
grounding rules below still apply to what the renderer put in it, you just aren't retyping it
into chat.

`analysis.json` has one top-level key per metric family — `lifecycle`, `failures`, `skillReads`,
`tokens`, `cache`, `activity`, `models`, `cost`, `meta`. The exact formula behind each is **not**
repeated here — read `references/metrics.md` before interpreting a number you're unsure about,
especially:

- `tokens.approximateFileIo` is an **estimate** (chars/4), not exact — never present it as
  precise in the report.
- `activity.<sessionId>.counts` are raw signal counts, not a forced label — `suggested` is a
  best-effort argmax. Resolve the final per-session planning/implementing/diagnosing/fixing
  label yourself, using the counts plus a skim of that session's `toolEvents` in `events.jsonl`
  when a call is close.
- `cache.expiryEvents` are pre-filtered candidates; `significant: true` ones are the ones worth
  quoting directly in the report ("cache expired here — a fresh handoff would have been cheaper").
- `models.beadsByModel` is an **approximate** ts→model attribution (metrics.md (f)) — label it as
  such, don't present it as verified.
- `cost.*` is an **estimate**, never a billed figure — transcripts carry no raw cost. Always cite
  `cost.pricingAsOf` and say "estimated" in the same breath as any dollar figure. An unpriced
  model family shows up in `cost.unpriced`, not silently dropped.
- `meta.bhVersion` is the best-effort observed `bh`/`bd` version at analysis time — this is what
  maintainer recommendation items get stamped with (see step 4 below).

Write the report (optionally to `report.md`) with:

1. **One section per requested metric**, as a table: beads planned/implemented/merged (by epic —
   `lifecycle.byEpic`, and by workstream if you cross-referenced labels), failed tool calls
   (`failures`, beads/bh vs other), skills read (`skillReads`, bh:/beads: vs other, plus
   `skillMdReads`), token category split (`tokens`, exact + the labelled-approximate file-IO
   split), cache ratio (`cache.cacheRatio`), and the planning/implementing/diagnosing/fixing
   distribution (`activity`).
2. **Epic/workstream breakdown** — `lifecycle.byEpic` keyed table; note `lifecycle.source`
   (`id-heuristic` — offline, no live `bd`/`bh` cross-reference) so the reader knows the epic
   grouping is inferred from bead-id shape, not a verified parent link.
3. **Cache-expiry call-outs** — for every `cache.expiryEvents` entry with `significant: true`,
   name the session, the idle gap, and the wasted-token count, grounded in that real event (never
   invent one). Beside each call-out, cite `cost.cacheWasteUSD` (the dollar estimate of that
   waste) so the "a handoff would've been cheaper" observation lands as a number, not a vibe.
4. **Model usage** — a `models.bySession` table (models used, `dominant`) and a
   `models.beadsByModel` table (bead lifecycle events per model, labelled approximate per
   metrics.md (f)).
5. **Estimated cost** — a `cost.byModel` table (input/output/cache-read/cache-write cost per
   family + `totalCost`) plus the `cost.total` grand total; cite `cost.pricingAsOf` and state
   plainly this is an estimate from `references/pricing.json`, not a billed number. List any
   `cost.unpriced` model families and their raw token counts rather than omitting them.
6. **Recommendations — two labelled tiers**, each item grounded in a specific number from
   `analysis.json` (never invent one):
   - **Usage-pattern (for you)** — 3–5 items actionable this run: model over-provisioning (a
     session's `models`/`cost` show opus/sonnet spend where a cheaper family would likely have
     done the job), a handoff point at a significant cache-expiry event (cite the wasted tokens
     and `cost.cacheWasteUSD`), batch-vs-fanout dispatch shape, a cluster of failed `bd`/`bh`
     calls (`failures`), or a skill re-read repeatedly (`skillReads.skillMdReads`).
   - **Beadhive product improvements (for maintainers)** — 0–3 items where the data points at a
     Beadhive tooling gap rather than a usage fix. Stamp each one `observed on bh
     <meta.bhVersion> (CC <meta.ccVersions>)` — framed version-relative, since a later `bh`
     release may already have addressed it — with a short paste-ready block (offending command,
     error text, session id) a maintainer can act on without re-deriving it from `analysis.json`.

Progressive disclosure: keep the report's prose short and let `references/metrics.md` carry the
formula detail — link to it rather than re-deriving formulas in the report.
