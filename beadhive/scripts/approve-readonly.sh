#!/usr/bin/env bash
# Auto-approve read-only bd/bh calls. Anything not recognized falls through
# to the normal permission flow, so mutating verbs still prompt.
command -v jq >/dev/null 2>&1 || exit 0
input=$(cat)
tool=$(jq -r '.tool_name // empty' <<<"$input")

allow() {
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"read-only bd/bh call"}}'
  exit 0
}

# MCP calls: the hooks.json matcher already scopes this to the read-only tools
[[ "$tool" == mcp__* ]] && allow
[[ "$tool" == "Bash" ]] || exit 0

cmd=$(jq -r '.tool_input.command // empty' <<<"$input")

# single simple command only — chaining, pipes, redirects, and substitution
# all fall through to a prompt (conservative: quoted operators also bail)
[[ "$cmd" == *$'\n'* ]] && exit 0
case "$cmd" in
  *'&&'*|*'||'*|*';'*|*'|'*|*'>'*|*'<'*|*'$('*|*'`'*) exit 0;;
esac

read -ra w <<<"$cmd"

# normalize `bh [-r RIG|--rig RIG|-a|--all] ...` down to its subject
if [[ "${w[0]:-}" == bh ]]; then
  w=("${w[@]:1}")
  while [[ "${w[0]:-}" == -r || "${w[0]:-}" == --rig ]]; do w=("${w[@]:2}"); done
  while [[ "${w[0]:-}" == -a || "${w[0]:-}" == --all ]]; do w=("${w[@]:1}"); done
  case "${w[0]:-}" in
    ""|--help|-V|--version|report-target) allow;;
    bd) ;; # passthrough — checked against the bd verb list below
    work|plan|rig|worktree|labels|hq)
      [[ "${w[1]:-}" == --help ]] && allow
      case "${w[0]} ${w[1]:-}" in
        "work check"|"work ready"|"work show"|"plan show"|"plan check"|\
        "rig ls"|"rig ready"|"rig survey"|"rig prefix"|"rig classify"|\
        "worktree ls") allow;;
      esac
      exit 0;;
    *) exit 0;;
  esac
fi

if [[ "${w[0]:-}" == bd ]]; then
  case "${w[1]:-}" in
    show|list|ready|blocked|stats|search|children|count|info|version|help|--help|-h) allow;;
  esac
fi
exit 0
