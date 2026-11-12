---
compatibility: "Requires bh CLI to file idea beads (the bh bd passthrough, which is off by default and must be enabled by the operator) and the Task tool to launch bh:ideator sub-agents. Task/Skill examples and the bh: namespace are Claude-specific."
name: brainstorm
description: >-
  Turn vision-scan's overview + candidate lens topics (or a fast standalone vision pass, if run
  without vision-scan first) into many candidate ideas fast, by fanning out one dedicated
  ideator sub-agent per lens topic — each seeded identically with the shared vision overview
  but blind to what sibling agents produce, so the batch stays divergent instead of converging
  on the same 2-3 obvious ideas. Dedupes across topics, then files each surviving idea as a
  lightweight tag:idea bead (not a molecule) — the hand-off to propose. Use when the user says
  "brainstorm ideas", "generate ideas from the vision", "fan out ideation", or after
  vision-scan produces an overview and topic list.
allowed-tools: Read, Grep, Glob, Bash, Task, Skill
---

# brainstorm

Parallel divergent ideation. This skill doesn't judge or prioritize ideas — that's `bh:propose`'s job. It only generates many genuinely distinct candidates and captures them as lightweight beads.

## Input

`bh:vision-scan`'s two-part output: the vision overview (shared context every `ideator` gets) and the candidate lens-topic list (the per-agent seeds). If `bh:vision-scan` wasn't run first, do a fast internal pass yourself to derive both before fanning out.

Prefer topics derived from the vision doc's own structure over a fixed generic list. A small generic backstop — unblock-a-known-blocker, extend-a-technical-capability, integrate-with-an-owned-project, integrate-with-an-external-ecosystem, reduce-operational-risk, improve-a-named-metric-or-story — only fills gaps if the doc-derived topic list is thin, and should be clearly marked as generic when used.

## Parallel fan-out

One `Task` call per lens topic, each launched as the dedicated `bh:ideator` sub-agent (`subagent_type: "bh:ideator"`, `model: opus` — see the agent definition for why). Seed each with:

- The shared vision overview, verbatim.
- Its one assigned lens topic (with `bh:vision-scan`'s why-it-matters / what's-known-vs-open note).
- A short current-state summary so it doesn't re-propose dead ideas: what's already filed/in-flight, which past spikes closed NO-GO.

Each `ideator` runs blind to what sibling agents are producing — the diversity comes from that isolation, not from raw volume. Don't loop them or let them see each other's output before returning.

## Dedup

Once all `ideator` runs return, collapse near-duplicate ideas across lens topics before filing — a quick pass comparing titles/descriptions for substantial overlap is enough; don't burn bead ids on near-copies of the same idea surfaced from two angles.

## bh availability

1. Check whether `bh` plugin skills are loaded in this session (e.g. `bh:work`, `bh:planner`); load the relevant one via the `Skill` tool.
2. Otherwise check `command -v bh`; if present, run `bh work --help`.
3. If neither is available, stop before filing — report the deduped idea list to the user instead, since nothing can be captured as a bead without `bh`.
4. Filing uses the `bh bd` passthrough, which is **disabled by default** (config key `passthrough.bd_enabled`, or `BH_BD_PASS_ENABLED=1`). If `bh bd create` answers that the passthrough is disabled, do not override it yourself — report the deduped idea list and ask the operator to enable it.

## File as idea beads

For each surviving idea, file a **lightweight** bead — not a `bh:planner` molecule:

- Title, description (the idea + its vision citation + why-now + a candidate go/no-go blocker if one is visible).
- Label `tag:idea`. Send the bead as one JSON document so prose never passes through the shell; a quoted heredoc keeps backticks and quotes in the description inert:

  ```bash
  bh bd create --json - <<'EOF'
  {"title": "<title>", "description": "<description>", "labels": ["tag:idea"]}
  EOF
  ```

  `--json` also takes a list of such objects and cannot be combined with per-field flags such as `-d` or `-l`. `bh bd create` adds the provider/org/repo identity labels itself.
- No kickoff gate, no epic scaffolding — these are pre-triage capture items.

Use `bh bd create` for this (the gated passthrough fallback `bh:planner` documents) — appropriate here specifically because nothing downstream expects molecule shape yet. This is the one place in the spike loop where `bh bd create` is the right tool instead of `bh plan file`; every other filing step goes through the planner.

## Handoff

Report the filed idea-bead ids to the user. `bh:propose` does the judgment (which ideas are worth pursuing, in what order) and the real molecule-filing mechanics from here — this skill's job ends at "many distinct ideas, captured as beads."
