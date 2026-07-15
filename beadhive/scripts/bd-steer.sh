#!/usr/bin/env bash
# Non-blocking steering hint: nudge direct `bd` calls toward the rig-aware
# `bh bd` passthrough. Never blocks and never changes the permission decision.
command -v jq >/dev/null 2>&1 || exit 0
cmd=$(jq -r '.tool_input.command // empty' 2>/dev/null)
# ponytail: matches `bd` at command start or after ;|&& — misses `FOO=1 bd`, fine
if grep -qE '(^|[;&|][;&|]?[[:space:]]*)bd[[:space:]]' <<<"$cmd"; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"beadhive plugin: prefer the `bh bd <args>` passthrough over direct `bd`. It is rig-aware — `bd create` auto-applies provider/org/repo, and `-r <rig>`/`--all` route the call across rigs — so direct `bd` can hit the wrong database. This call was not blocked; switch to `bh bd` for subsequent calls."}}'
fi
exit 0
