#!/usr/bin/env bash
# SessionStart preflight for the external bh CLI. Computes the verdict once,
# writes a session sentinel, and emits an advisory only when the CLI is missing
# or too old for this plugin.
set -u

input=$(cat)
plugin_root=$(cd "$(dirname "$0")/.." && pwd)
manifest="$plugin_root/.claude-plugin/plugin.json"
required=">=0.3.0"

json_string() { # json_string <key>
  local key=$1
  if command -v jq >/dev/null 2>&1; then
    jq -r --arg key "$key" '.[$key] // empty' <<<"$input" 2>/dev/null
  else
    grep -oE '"'"$key"'"[[:space:]]*:[[:space:]]*"[^"]*"' <<<"$input" | \
      grep -oE '"[^"]*"$' | tr -d '"'
  fi
}

if command -v jq >/dev/null 2>&1; then
  from_manifest=$(jq -r '.requires.bh // empty' "$manifest" 2>/dev/null || true)
  [[ -n "$from_manifest" ]] && required=$from_manifest
fi

min=${required#>=}
[[ "$min" == "$required" || -z "$min" ]] && min="0.3.0"

session_id=$(json_string session_id)
[[ -z "$session_id" ]] && session_id="unknown"
safe_session=$(tr -c '[:alnum:]_.-' '_' <<<"$session_id")
sentinel_dir="${TMPDIR:-/tmp}/beadhive-preflight"
sentinel="$sentinel_dir/$safe_session.env"
mkdir -p "$sentinel_dir" 2>/dev/null || exit 0

verdict=ok
installed=""
if ! command -v bh >/dev/null 2>&1; then
  verdict=missing
  installed=missing
else
  installed=$(bh --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
  if [[ -z "$installed" ]]; then
    verdict=too-old
    installed=unknown
  elif [[ "$(printf '%s\n%s\n' "$min" "$installed" | sort -V | head -1)" != "$min" ]]; then
    verdict=too-old
  fi
fi

{
  printf 'verdict=%s\n' "$verdict"
  printf 'installed=%s\n' "$installed"
  printf 'required=%s\n' "$required"
  printf 'min=%s\n' "$min"
} >"$sentinel" 2>/dev/null || exit 0

[[ "$verdict" == ok ]] && exit 0

reason="bh $installed does not satisfy required $required - upgrade first; see https://github.com/beadhive/beadhive/blob/main/INSTALL.md or run /setup."
printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$reason"
