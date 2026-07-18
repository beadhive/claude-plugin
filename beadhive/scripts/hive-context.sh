#!/usr/bin/env bash
# SessionStart hook: inject AGF steering for a zero-footprint hive straight from
# the registry, so a registered repo carrying NO plugin/AGF files still gets
# steered. `bh hive context --hook-json` prints SessionStart hookSpecificOutput
# JSON when cwd resolves to a registered hive, and nothing otherwise.
#
# Guarded so a missing bh or a pre-0.3.0 build (no `hive context` verb) is a
# silent no-op, never a broken session start.
#
# ponytail: harness reach is Claude-only here — this injects live context for
# Claude Code. Codex/other harnesses still need the on-disk AGENTS.md written by
# `bh hive onboard --furnish`/`--agents`; the registry-only path does not cover
# them.
command -v bh >/dev/null 2>&1 || exit 0
bh hive context --hook-json 2>/dev/null || exit 0
exit 0
