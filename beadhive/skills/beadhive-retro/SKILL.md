---
name: beadhive-retro
description: >-
  Retrospective efficiency analysis over recent Claude Code sessions that used Beadhive. Use
  when asked "how did we do since the last reset", "what did the last week of Beadhive sessions
  cost", "how many beads got planned/implemented/merged", "which tool calls failed", "what's our
  cache-hit ratio", "where did we waste tokens re-feeding an expired cache", or "how did time
  split across planning/implementing/diagnosing/fixing". Runs a three-phase pipeline
  (identify → extract → analyze) over `~/.claude/projects/*/*.jsonl`, then synthesizes a report
  with real numbers — never hand-waves a retrospective from memory.
---

# beadhive-retro — retrospective efficiency analysis

Answers "how efficient were our recent Beadhive sessions" with real numbers pulled from Claude
Code's own session transcripts, not vibes. Stdlib-only Python scripts do the scripted work
(identification, extraction, aggregation, and — opt-in — HTML rendering); you do the judgment
work (labelling ambiguous sessions, writing the narrative, picking recommendations).

## Run the pipeline, in order

From this skill's directory (`scripts/` is relative to `SKILL.md`):

```bash
python3 scripts/identify.py --since auto   # -> ~/.beadhive/retros/<run-id>/identify.json
python3 scripts/extract.py                 # -> extract.jsonl, events.jsonl in the same run-dir
python3 scripts/analyze.py                 # -> analysis.json in the same run-dir
```

No path args needed for the common case: `identify.py` creates a fresh, datetime-named run
folder under `~/.beadhive/retros/<YYYYMMDD-HHMMSS>-<hash8>/` (the id is derived from the run's
own `since`/`generatedAt`/session-count — see `scripts/_rundir.py`), writes `identify.json`
there, and points `~/.beadhive/retros/latest` at it. `extract.py` and `analyze.py` pick up that
same run-dir automatically via the `latest` pointer, so each run's four artifacts
(`identify.json`, `extract.jsonl`, `events.jsonl`, `analysis.json`) land together and accumulate
run-over-run for comparison.

Pass `--since <iso>` to `identify.py` to override auto-window-detection with an explicit
boundary. Pass `--run-dir <dir>` (all three scripts) or `--out`/`--in`/`--events` (individually)
to target an arbitrary directory instead — e.g. for an ad-hoc or CI invocation that shouldn't
touch `~/.beadhive/retros/` or the `latest` pointer. Each script also has `--selftest` — run it
if you change one of them; it must stay green.

**This is the acceptance bar for this skill**: invoking it must actually run all three phases
end to end and produce a report grounded in `analysis.json`'s numbers, not a summary written from
guesswork.

## Artifact mode: render report.html instead of the in-chat report

**Default behavior (no flag) is unchanged**: write the report inline in chat per the section
below. If the user asks for an artifact / file / HTML report (or says "artifact mode"), run a
fourth, opt-in step after `analyze.py`:

```bash
python3 scripts/render.py   # reads <run-dir>/analysis.json -> <run-dir>/report.html
```

`render.py` resolves the same run-dir as the other three scripts (via the `latest` pointer or
`--run-dir`) and writes a single self-contained `report.html` (inline CSS, no JS framework, no
new dependencies) next to `analysis.json` — tables for every metric family plus the significant
cache-expiry call-outs and a two-tier recommendations section, all computed straight from
`analysis.json`.

When artifact mode is requested, **present `report.html` to the user instead of writing the full
report in chat**: give its path and tell them to open it. A short in-chat summary (a couple of
headline numbers) is fine, but don't re-paste the full per-section report — that's what the
artifact is for. The numbers must still be the same ones grounded in `analysis.json`; `render.py`
just formats them.

## Read `analysis.json`, then write the report

This section is the default in-chat report (no artifact flag). If artifact mode was requested,
skip straight to presenting `report.html` (see above) — the same grounding rules below still
apply to what `render.py` put in it, you just aren't retyping it into chat.

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
