#!/usr/bin/env bash
# Auto-approve read-only bd/bh calls. Anything not recognized falls through
# to the normal permission flow, so mutating verbs still prompt.
command -v jq >/dev/null 2>&1 || exit 0
input=$(cat)
tool=$(jq -r '.tool_name // empty' <<<"$input")
session_id=$(jq -r '.session_id // empty' <<<"$input")

sentinel_path() {
  [[ -n "$session_id" ]] || return 1
  local safe_session
  safe_session=$(tr -c '[:alnum:]_.-' '_' <<<"$session_id")
  printf '%s\n' "${TMPDIR:-/tmp}/beadhive-preflight/$safe_session.env"
}

sentinel_value() {
  local key=$1 sentinel
  sentinel=$(sentinel_path) || return 1
  [[ -f "$sentinel" ]] || return 1
  grep -E "^$key=" "$sentinel" | head -1 | cut -d= -f2-
}

allow() {
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"read-only bd/bh call"}}'
  exit 0
}

deny_preflight() {
  local installed required
  installed=$(sentinel_value installed || true)
  required=$(sentinel_value required || true)
  [[ -n "$installed" ]] || installed=installed
  [[ -n "$required" ]] || required='>=0.3.0'
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"bh %s does not satisfy required %s - upgrade first; see https://github.com/beadhive/beadhive/blob/main/INSTALL.md"}}\n' "$installed" "$required"
  exit 0
}

preflight_verdict=$(sentinel_value verdict || true)

case "$tool" in
  mcp__*)
    [[ -n "$preflight_verdict" && "$preflight_verdict" != ok ]] && deny_preflight
    case "$tool" in
      mcp__*__plan_check|mcp__*__hives_status|mcp__*__hives_available|mcp__*__rigs_status|mcp__*__rigs_available) allow;;
    esac
    exit 0;;
esac

[[ "$tool" == "Bash" ]] || exit 0

cmd=$(jq -r '.tool_input.command // empty' <<<"$input")

if [[ -n "$preflight_verdict" && "$preflight_verdict" != ok ]] && \
  grep -qE '(^|[;&|][;&|]?[[:space:]]*)(bh|bd)([[:space:]]|$)' <<<"$cmd"; then
  deny_preflight
fi

# single simple command only — chaining, pipes, redirects, and substitution
# all fall through to a prompt (conservative: quoted operators also bail)
[[ "$cmd" == *$'\n'* ]] && exit 0
case "$cmd" in
  *'&&'*|*'||'*|*';'*|*'|'*|*'>'*|*'<'*|*'$('*|*'`'*) exit 0;;
esac

read -ra w <<<"$cmd"

# normalize `bh [-r HIVE|--hive HIVE|-a|--all] ...` down to its subject
if [[ "${w[0]:-}" == bh ]]; then
  w=("${w[@]:1}")
  while [[ "${w[0]:-}" == -r || "${w[0]:-}" == --hive ]]; do w=("${w[@]:2}"); done
  while [[ "${w[0]:-}" == -a || "${w[0]:-}" == --all ]]; do w=("${w[@]:1}"); done
  case "${w[0]:-}" in
    ""|--help|-V|--version|report-target) allow;;
    bd) ;; # passthrough — checked against the bd verb list below
    work|plan|hive|worktree|labels|hq)
      [[ "${w[1]:-}" == --help ]] && allow
      case "${w[0]} ${w[1]:-}" in
        "work check"|"work ready"|"work show"|"plan show"|"plan check"|\
        "hive ls"|"hive ready"|"hive survey"|"hive prefix"|"hive classify"|\
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
