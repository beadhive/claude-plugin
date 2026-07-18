#!/usr/bin/env bash
# Self-test for the plugin's PreToolUse hook scripts.
set -u
cd "$(dirname "$0")/.."
STEER=beadhive/scripts/bd-steer.sh
APPROVE=beadhive/scripts/approve-readonly.sh
PREFLIGHT=beadhive/scripts/bh-preflight.sh
PLUGIN_JSON=beadhive/.claude-plugin/plugin.json
fail=0
test_tmp=$(mktemp -d)
orig_plugin=$(mktemp)
cp "$PLUGIN_JSON" "$orig_plugin"
trap 'cp "$orig_plugin" "$PLUGIN_JSON"; rm -rf "$test_tmp" "$orig_plugin"' EXIT
export TMPDIR="$test_tmp"

run() { # run <script> <tool_name> <command> -> HINT | ALLOW | PASS
  local out
  out=$(jq -n --arg t "$2" --arg c "$3" --arg sid "${4:-test-session}" \
    '{session_id:$sid,tool_name:$t,tool_input:{command:$c}}' | "$1")
  if [[ "$out" == *'"permissionDecision":"allow"'* ]]; then echo ALLOW
  elif [[ "$out" == *'"permissionDecision":"deny"'* ]]; then echo DENY
  elif [[ "$out" == *additionalContext* ]]; then echo HINT
  else echo PASS; fi
}

t() { # t <script> <tool_name> <command> <expected> [session]
  local got; got=$(run "$1" "$2" "$3" "${5:-test-session}")
  if [[ "$got" != "$4" ]]; then
    echo "FAIL: $2 '$3' -> $got (want $4)"; fail=1
  fi
}

preflight() { # preflight <session_id> <path> -> HINT | PASS
  local out
  out=$(jq -n --arg sid "$1" '{session_id:$sid}' | PATH="$2" "$PREFLIGHT")
  if [[ "$out" == *additionalContext* ]]; then echo HINT; else echo PASS; fi
}

stub_path() { # stub_path <version|absent> <include_jq>
  local bin="$test_tmp/bin-$1-$2"
  mkdir -p "$bin"
  if [[ "$1" != absent ]]; then
    printf '#!/usr/bin/env bash\necho "bh version %s"\n' "$1" >"$bin/bh"
    chmod +x "$bin/bh"
  fi
  if [[ "$2" == jq && -n "$(command -v jq)" ]]; then
    ln -sf "$(command -v jq)" "$bin/jq"
  fi
  printf '%s:/usr/bin:/bin' "$bin"
}

expect_preflight() { # expect_preflight <session> <version|absent> <include_jq> <expected>
  local path got
  path=$(stub_path "$2" "$3")
  got=$(preflight "$1" "$path")
  if [[ "$got" != "$4" ]]; then
    echo "FAIL: preflight $2 jq=$3 -> $got (want $4)"; fail=1
  fi
}

# steer: hint on direct bd, silent otherwise
t "$STEER" Bash 'bd show x'            HINT
t "$STEER" Bash 'cd /tmp && bd list'   HINT
t "$STEER" Bash 'bh bd show x'         PASS
t "$STEER" Bash 'git log'              PASS

# approve: read-only bd/bh allowed
t "$APPROVE" Bash 'bd show x'                     ALLOW
t "$APPROVE" Bash 'bd list --json'                ALLOW
t "$APPROVE" Bash 'bd --help'                     ALLOW
t "$APPROVE" Bash 'bh bd list'                    ALLOW
t "$APPROVE" Bash 'bh -r beadhive/foo bd show y'  ALLOW
t "$APPROVE" Bash 'bh --all bd list'              ALLOW
t "$APPROVE" Bash 'bh work check'                 ALLOW
t "$APPROVE" Bash 'bh work --help'                ALLOW
t "$APPROVE" Bash 'bh plan show'                  ALLOW
t "$APPROVE" Bash 'bh hive ls'                    ALLOW

# approve: mutating, compound, or unrelated falls through to a prompt
t "$APPROVE" Bash 'bd update x --status done'     PASS
t "$APPROVE" Bash 'bd create foo'                 PASS
t "$APPROVE" Bash 'bd delete x'                   PASS
t "$APPROVE" Bash 'bh work merge'                 PASS
t "$APPROVE" Bash 'bh hive onboard github/x/y'    PASS
t "$APPROVE" Bash 'bh config set a b'             PASS
t "$APPROVE" Bash 'bd show x && rm -rf /'         PASS
t "$APPROVE" Bash 'bd list > /tmp/x'              PASS
t "$APPROVE" Bash 'bd list | tee /tmp/x'          PASS
t "$APPROVE" Bash 'git status'                    PASS

# approve: read-only bh MCP tools (matcher pre-scopes; script trusts mcp__*)
t "$APPROVE" mcp__plugin_bh_bh__hives_status ''   ALLOW
t "$APPROVE" mcp__bh__plan_check ''               ALLOW

# preflight: missing/too-old blocks, lower-bound-compatible versions pass.
expect_preflight missing absent jq HINT
t "$APPROVE" Bash 'bh work ready' DENY missing
t "$APPROVE" Bash 'bd list' DENY missing
t "$APPROVE" mcp__plugin_bh_bh__plan_check '' DENY missing

expect_preflight old 0.2.0 jq HINT
t "$APPROVE" Bash 'bh work ready' DENY old

expect_preflight ok 0.3.0 jq PASS
t "$APPROVE" Bash 'bh work ready' ALLOW ok

expect_preflight future 0.4.0 jq PASS
t "$APPROVE" Bash 'bh work ready' ALLOW future

# preflight reads plugin.json when jq is available.
python3 - <<'PY'
import json
path = 'beadhive/.claude-plugin/plugin.json'
data = json.load(open(path))
data['requires']['bh'] = '>=0.4.0'
json.dump(data, open(path, 'w'), indent=2)
PY
expect_preflight manifest 0.3.0 jq HINT
cp "$orig_plugin" "$PLUGIN_JSON"

# preflight falls back to the hardcoded range when jq is unavailable.
expect_preflight nojq 0.3.0 nojq PASS

[[ $fail -eq 0 ]] && echo "hooks: all cases pass"
exit $fail
