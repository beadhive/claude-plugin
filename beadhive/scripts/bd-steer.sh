#!/usr/bin/env bash
# Non-blocking steering hint: nudge direct `bd` calls toward the hive-aware
# `bh bd` passthrough. For triage/groom/plan/schedule shaped calls, also
# points at bv's --robot-* output when bv is installed (later: a bh verb
# that wraps bv, preferred over raw bv once one exists). Never blocks and
# never changes the permission decision.
command -v jq >/dev/null 2>&1 || exit 0
cmd=$(jq -r '.tool_input.command // empty' 2>/dev/null)
# ponytail: matches `bd` at command start or after ;|&& — misses `FOO=1 bd`, fine
grep -qE '(^|[;&|][;&|]?[[:space:]]*)bd[[:space:]]' <<<"$cmd" || exit 0

msg='beadhive plugin: prefer the `bh bd <args>` passthrough over direct `bd`. It is hive-aware — `bd create` auto-applies provider/org/repo, and `-r <hive>`/`--all` route the call across hives — so direct `bd` can hit the wrong database. This call was not blocked; switch to `bh bd` for subsequent calls.'

if grep -qE '(^|[;&|][;&|]?[[:space:]]*)bd[[:space:]]+(ready|list|blocked|stale|orphans)([[:space:]]|$)' <<<"$cmd" \
  && command -v bv >/dev/null 2>&1; then
  # ponytail: stub for a future `bh config get integrations.bv.enabled` — bh
  # has no such key yet, so an absent/errored read is treated as enabled;
  # only an explicit "false" opts out. Once a bh verb wraps bv, prefer
  # steering there over raw bv, same as bh over raw bd above.
  enabled=$(bh config get integrations.bv.enabled 2>/dev/null)
  if [[ "$enabled" != false ]]; then
    msg+=' For triage/grooming/planning/scheduling, bv is installed — prefer its --robot-triage/--robot-next/--robot-plan/--robot-insights output over bd queries (the triage skill).'
  fi
fi

jq -n --arg msg "$msg" '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:$msg}}'
exit 0
