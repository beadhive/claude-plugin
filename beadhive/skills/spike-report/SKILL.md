---
compatibility: "Requires bh CLI, the Task tool for read-only research sub-agents, and a host Artifact tool for the final page. Task/Skill examples and the bh: namespace are Claude-specific."
name: spike-report
description: >-
  Generate a tabbed HTML report for a concluded (or in-flight) wave of spikes — one tab per
  spike showing (1) origin & go/no-go validation criteria pulled from the parent epic's
  vision-doc lineage plus the spike bead's own description, (2) verdict + worktree/bead/gate
  metadata, (3) a small flow diagram of components touched plus a files-changed strip, (4)
  commit history and validation evidence — so a low-context reviewer can quickly call GO
  (re-plan via /bh:replan), NO-GO (write an ADR and close), or needs-repair (bh plan repair)
  for each spike. Fans out one parallel read-only research agent per spike, then renders via
  the platform Artifact tool. Use when the user says "generate the spike report", "build the
  spike batch report", "wave report", "show me the spikes as a report", or after a batch-run
  wave concludes.
allowed-tools: Bash, Read, Grep, Glob, Task
---

# spike-report

Turn a concluded wave of spikes into the single artifact a low-context reviewer needs to make GO / NO-GO / repair calls without re-deriving context from scratch. This skill runs in the **main session**, not a sub-agent — it needs the platform Artifact tool at the end, which isn't available inside a `Task` subagent.

## What this produces

A single self-contained HTML page: the wave's header/TL;DR/theme-groupings (optional, only if the wave clusters into named themes) followed by a tab system — one tab per spike, each showing a succinct display name, category, verdict chip, and lifecycle chip in the sidebar, and a detail pane with **exactly** these four sections, in this order, every time:

1. **Origin & validation criteria** — why the parent epic exists (its vision-doc lineage), and the spike's own explicit go/no-go bar
2. **Go/no-go result & worktree metadata** — the verdict, branch/gate/bead state, any claim override or escalation
3. **Solution approach & components** — a small flow diagram of what was touched or proposed, plus a files-changed strip
4. **Commit history & validation** — the actual commit(s) and the concrete evidence behind the verdict

Plus a non-optional **next action** banner per spike: GO → `/bh:replan <parent-epic>`; NO-GO → write an ADR + close; repair → `bh plan repair <parent-epic>`.

Reconstruct this shape every run from `references/report-template.html` — don't redesign the layout or invent new sections per repo. See `## Rendering` below for how to use that file.

## bh availability

This skill needs `bh`/`bd` to enumerate the batch and pull bead/gate state. Before anything else:

1. Check whether `bh` plugin skills are loaded in this session (e.g. `bh:overview`, `bh:work`). If so, load the relevant one via the `Skill` tool for the current, version-matched command reference.
2. Otherwise check `command -v bh`; if present, run `bh --help` and `bh work --help` to learn the live surface. Reads go through the first-class `bh work` verbs; the raw `bh bd` passthrough is disabled by default and this skill never needs it.
3. If neither is available, stop and tell the user `bh` is required — do not guess at query syntax.

The commands below (`bh work issue`, `bh work list`) are the current shape — confirm via the discovery step above before relying on them, especially on an unfamiliar machine or a different bh version.

## Identify the batch

Ask (or infer from context) which spikes belong to this wave:

- **Explicit**: the user names spike/epic ids directly.
- **Implicit**: query for `tag:spike` beads/epics currently in a review-gated or closed state (e.g. `bh work list -l tag:spike --json`, filtered to `review:pending` or recently closed; `bh work list -l tag:spike --status closed --json` covers the closed side), optionally scoped to a shared parent epic or a date/session marker.

List the candidates and confirm scope with the user before fanning out research — don't silently include spikes outside what they meant by "this wave."

## Per-spike data sources

For each spike in the batch, gather:

- `bh work issue <spike-id> --json` and `bh work issue <parent-epic-id> --json` — description, acceptance_criteria, notes/verdict, labels, dependencies.
- The spike's worktree branch (if one exists): `git log <branch> --oneline` and `git diff main...<branch> --stat`.
- The gate bead, if one exists: `bh work issue <gate-id> --json` (reason, await_type, status). If no gate exists, note whether the claim was refused, escalated, or completed via a disclosed override — check the spike bead's `notes` for this.
- Any verdict/decision doc committed on the branch (`docs/spikes/*`, `docs/decisions/*`, `docs/design/*`, or whatever convention the repo actually uses — don't assume a path, confirm it from what's actually there).

## Fan-out method

Launch **one parallel research sub-agent per spike** (a read-only Explore-type agent: `Bash`+`Read`+`Grep`+`Glob`), each instructed to gather exactly the data above and return a structured writeup with the same four sections the report will render (~700 words is a reasonable ceiling per spike). This is the pattern that scales cleanly to a wave of ~10 spikes as plain parallel `Task` calls.

For a materially larger batch, the platform's Workflow tool (pipeline/parallel primitives) is a legitimate alternative — but only ever propose it as an explicit opt-in the user approves before invoking; never reach for it silently as the default path.

## Synthesis into the template

Once every sub-agent writeup returns:

1. Read `references/report-template.html` for the current run.
2. For each spike, add one tab button + one matching tab panel (same `{{SLUG}}`), filling in the four `.pblock` sections and the `.nextaction` banner from that spike's writeup.
3. Derive each spike's **category** from its parent epic's theme, and keep both the display name and category succinct (a handful of words) — full detail belongs in the panel, never the tab list.
4. Pick the verdict chip class (`go` / `caution` / `blocked`) from the technical finding, and the lifecycle chip (`gate` citing the gate id, or `blocked` citing "refused"/"escalated"/the override used) independently — a spike can be a technical GO while still lifecycle-blocked (claim refused), and the report should show both facts, not collapse them into one.
5. Only include the optional theme-groupings section if the wave's spikes cluster into a few real vision-doc themes worth naming; skip it for a small or single-theme wave.

## Rendering

Write the filled-in HTML to a fresh file (not `report-template.html` itself) and publish it via the platform's Artifact tool as a single self-contained page — no external assets, inline CSS/JS only (the template already is that; keep it that way).

## What not to do

- Don't invent a different report layout per repo — retheme CSS token *values* only if a repo's own brand genuinely calls for it.
- Don't collapse the four `.pblock` sections into fewer, or reorder them — the fixed shape is what makes the report scannable across repos and waves.
- Don't skip the next-action banner — a report that describes a verdict without stating the concrete next step isn't done.
- Don't silently drop a spike from the wave because its data was hard to find (e.g. no committed verdict doc, claim refused) — report what's known and say plainly what's missing, the way the origin report handled its three notes-only spikes.
