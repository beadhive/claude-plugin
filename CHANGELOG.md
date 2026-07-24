## v0.4.0 (2026-07-23)

### Feat

- **beadhive-retro**: classify tool calls into beadhive/raw-beads/raw-git/other
- **retro**: ship scripted charted-artifact renderer, fix SKILL.md form-map gaps
- **retro**: brand + chart the report artifact by default
- **retro-skill**: add opt-in stdlib HTML report artifact (bh-cp-6sg)
- **retro-skill**: default pipeline output to ~/.beadhive/retros/<run-id>/ run folders (bh-cp-8hd)
- **beadhive-retro**: add models, cost, meta families to analyze.py (bh-cp-ory.3)
- **beadhive-retro**: capture Claude Code version into ccVersions in extract.py (bh-cp-ory.2)
- **beadhive-retro**: add pricing.json + metrics.md docs for model/cost/recommendations (bh-cp-ory.1)
- **beadhive-retro**: wire identify/extract/analyze into a runnable skill (bh-cp-jlk.5)
- **beadhive-retro**: add analyze.py metric aggregation (bh-cp-jlk.4)
- **beadhive-retro**: add extract.py transcript normalization (bh-cp-jlk.3)
- **beadhive-retro**: add identify.py session identification + window resolution (bh-cp-jlk.2)
- **beadhive-retro**: define metric formulas and classification heuristics (bh-cp-jlk.1)
- **plugin**: steer bead triage toward bv when installed

### Fix

- **retro**: filter <synthetic> sentinel from model-usage displays
- **beadhive-retro**: gate unpriced-cost copy on token volume, not model-list length
- **beadhive-retro**: full-width charts, rich recommendations, tool-class coloring
- **retro**: render_artifact.py chart/section fixes from artifact review
- **retro**: price fable in pricing.json, keep synthetic explicitly unpriced
- **retro**: capture distinct bh/plugin/bd version fields in meta
- **retro-skill**: remove unused vars/imports in identify.py (bh-cp-rxc)
- **retro-skill**: resolve pyright type/lint issues in analyze.py
- **beadhive-retro**: stop truncating bead ids in bd/bh commands, link create-time ids from tool_result (bh-cp-jlk.6)

## v0.3.0 (2026-07-17)

### Feat

- **plugin**: align hooks and skills with hive verbs
- **plugin**: gate unsupported bh runtime

### Fix

- **plugin**: use released hive command names

## v0.2.0 (2026-07-15)

### Feat

- **plugin**: planning-seat output style pins the seat contract per session (bh-cp-njh.5)
- **commands**: /bh:groom backlog-wide reconciliation (bh-cp-njh.4)
- **commands**: /bh:replan single-molecule re-entry (bh-cp-njh.3)
- **commands**: /bh:plan planning-seat entry point (bh-cp-njh.2)

## v0.1.3 (2026-07-15)

### Fix

- auto-approve read-only bd/bh calls via PreToolUse hook (bh-cp-1rx)

## v0.1.2 (2026-07-15)

### Fix

- PreToolUse hook steering direct bd calls toward bh bd passthrough

## v0.1.1 (2026-07-11)

### Fix

- **setup**: correct install coordinates and canonical paths
- **concepts**: rename agf-and-planes -> beadflow-and-planes, strip Gas Town, drop out-of-tree links
- **skills**: retire legacy names across role skills and verb reference

### Refactor

- **dispatcher**: split SKILL.md into lean body + references/

## v0.1.0 (2026-07-11)

### Feat

- **marketplace**: add self-vending root marketplace.json for ./bh
- **plugin**: rename agf -> bh (plugin.json, keywords, dir structure)
- **skills**: rename skill dirs + agf:coordinator → agf:dispatcher
- **agents**: add warden agent def + reconcile contributor boundary
- **plugin**: declare the ws MCP server in the plugin manifest
- **skills**: add setup-git-workspace sub-skill — first-timer git-workspace walkthrough
- **skills**: add setup skill — Phase 0-4 onboarding driver, fresh Mac to configured workspace
- **hq**: promote ws hq as operator surface; deprecate ws hub alias
- **triage**: source-agnostic intake triage surface + dispositions
- **backfill**: reconcile.sh --docs <dir> for arbitrary prose doc trees
- **backfill**: backfill Guide + reconcile tool (validated on the observaloop pilot)
- **plugin**: build agf plugin package + marketplace manifest (9 agents, 8 skills, agf:-scoped skill refs)

### Fix

- **mcp**: switch the plugin from gated 'ws mcp serve' to ungated 'ws-mcp'
- **setup**: correct Phase 0 marketplace command and drop workspace.root bullet
- **backfill**: reconcile reads block-style depends_on; document parent-child edges

### Refactor

- **mcp**: rename resource URI scheme ws:// -> beadhive://
- **seats**: remove epic-coordinator agent defs (folded into dispatcher)
- **agents**: reviewer/merger/planner/analyst reference dispatcher
- **agents**: developer def to dev/ prefix, ephemeral bead scope
- **agents**: split superintendent.md into four control-plane seats
- **agents**: rename coordinator.md to dispatcher.md, encode scope x mode
