---
compatibility: "Optional bh CLI for the backlog-state pass; without it the skill reads vision docs only. Skill/Task examples and the bh: namespace are Claude-specific."
name: vision-scan
description: >-
  Read a repo's vision/strategy documents (north-star docs, docs/ROADMAP.md, ADRs,
  "*-Reframe-and-*" or "*-GTM-*" style strategy docs) together with its current backlog and
  code state, and synthesize (a) a vision overview — themes, current state relative to each
  theme, known blockers, what's already filed or closed — and (b) a set of candidate lens
  topics derived from the vision doc's own structure, for the brainstorm skill to fan out
  against. Produces understanding only — no ideas, no beads. Use before brainstorming new
  work, when the user asks to "scan the vision docs", "what's our north star here",
  "understand where this repo is headed", "summarize the strategy doc", or "spike scan".
allowed-tools: Read, Grep, Glob, Bash
---

# vision-scan

Build understanding, not ideas. Ideation is entirely `bh:brainstorm`'s job (fanning out `bh:ideator` sub-agents); this skill's only output is the shared context and candidate angles that step needs.

## What this produces

Two parts, both handed to `bh:brainstorm`:

1. **Vision overview** — a synthesized brief: the north-star themes, the product/repo's current state relative to each theme, known blockers, and what's already filed or already closed (including past spike verdicts, so nothing downstream retreads settled ground). This becomes the shared context every `ideator` agent is seeded with.
2. **Candidate lens topics** — a set of distinct directions/aspects/components to brainstorm *about*, derived from the vision doc's own structure (its actual sections/themes) — not a fixed generic checklist reused across repos. Each topic gets a sentence or two: why it matters, and what's already known vs. open about it. This becomes the list `bh:brainstorm` assigns one-per-`ideator`.

## Vision-doc discovery

Look, in priority order:

- Repo-root strategy docs matching patterns like `*Reframe*`, `*GTM*`, `*Strategy*`, `*Vision*`.
- `docs/ROADMAP.md`.
- `docs/decisions/*` or `docs/adr/*` — ADRs establish constraints and direction, not just history.
- `.planning/` if present.
- README "Roadmap"/"Vision" sections.

If nothing matches, ask the user where the north-star doc lives — don't guess or synthesize a vision from scratch.

## Backlog-state pass

Run `bh work ready --json` (see `## bh availability` below) and a broad `bh work list --json` pass (add `--status open`, `--status closed` and so on to slice it) to see what's already filed or in flight. Specifically flag any `tag:spike` epics that already closed **NO-GO** — their topics shouldn't be silently re-surfaced as fresh candidates without noting the prior verdict.

## bh availability

1. Check whether `bh` plugin skills are loaded in this session (e.g. `bh:overview`, `bh:work`); load the relevant one via the `Skill` tool.
2. Otherwise check `command -v bh`; if present, run `bh work --help`.
3. If neither is available, note that the backlog-state pass can't run and proceed with the vision-doc read alone — this skill degrades gracefully without `bh` (unlike `bh:propose`, `bh:batch-run` and `bh:spike-report`, which hard-depend on it).

## Synthesis method

Build the overview by reading the vision doc(s) for their actual structure — section headers, named themes, explicit priorities — rather than imposing an external framework. Derive lens topics the same way: if the doc has sections on "integration with X," "cost efficiency," "developer experience," each is a candidate topic in its own right, not folded into a generic bucket. Cross-reference the backlog-state pass so each topic's write-up notes what's already known vs. still open about it.

## Output format

Present both parts conversationally for the user to review — nothing is filed, nothing is written to disk. This is a checkpoint before `bh:brainstorm` fans out real work against it.

## Handoff

Once the user is satisfied with the overview and topic list, hand off to the `bh:brainstorm` skill, which fans out one `bh:ideator` sub-agent per lens topic, seeded with the overview as shared context.
