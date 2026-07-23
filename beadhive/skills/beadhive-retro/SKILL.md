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
Code's own session transcripts, not vibes. Three stdlib-only Python scripts do the scripted work
(identification, extraction, aggregation); you do the judgment work (labelling ambiguous
sessions, writing the narrative, picking recommendations).

## Run the pipeline, in order

From this skill's directory (`scripts/` is relative to `SKILL.md`):

```bash
python3 scripts/identify.py --since auto        # -> identify.json
python3 scripts/extract.py                       # reads identify.json -> extract.jsonl, events.jsonl
python3 scripts/analyze.py                        # reads extract.jsonl -> analysis.json
```

Each phase's output feeds the next; run them from a scratch/working directory (they read/write
the current directory by default). Pass `--since <iso>` to `identify.py` to override
auto-detection with an explicit boundary. Each script also has `--selftest` — run it if you
change one of them; it must stay green.

**This is the acceptance bar for this skill**: invoking it must actually run all three phases
end to end and produce a report grounded in `analysis.json`'s numbers, not a summary written from
guesswork.

## Read `analysis.json`, then write the report

`analysis.json` has one top-level key per metric family — `lifecycle`, `failures`, `skillReads`,
`tokens`, `cache`, `activity`. The exact formula behind each is **not** repeated here — read
`references/metrics.md` before interpreting a number you're unsure about, especially:

- `tokens.approximateFileIo` is an **estimate** (chars/4), not exact — never present it as
  precise in the report.
- `activity.<sessionId>.counts` are raw signal counts, not a forced label — `suggested` is a
  best-effort argmax. Resolve the final per-session planning/implementing/diagnosing/fixing
  label yourself, using the counts plus a skim of that session's `toolEvents` in `events.jsonl`
  when a call is close.
- `cache.expiryEvents` are pre-filtered candidates; `significant: true` ones are the ones worth
  quoting directly in the report ("cache expired here — a fresh handoff would have been cheaper").

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
   invent one).
4. **3–5 concrete efficiency recommendations** — derived from what the numbers actually show
   (e.g. a low cache ratio, a cluster of failed `bd`/`bh` calls, a specific skill re-read
   repeatedly, a significant expiry event that suggests a handoff point).

Progressive disclosure: keep the report's prose short and let `references/metrics.md` carry the
formula detail — link to it rather than re-deriving formulas in the report.
