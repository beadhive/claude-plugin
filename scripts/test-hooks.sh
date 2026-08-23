#!/usr/bin/env bash
# Self-test for the plugin's PreToolUse hook scripts.
set -u
cd "$(dirname "$0")/.."
STEER=beadhive/scripts/bd-steer.sh
APPROVE=beadhive/scripts/approve-readonly.sh
PREFLIGHT=beadhive/scripts/bh-preflight.sh
COMPATIBILITY=beadhive/scripts/bh-compatibility.sh
fail=0
test_tmp=$(mktemp -d)
orig_compatibility=$(mktemp)
cp "$COMPATIBILITY" "$orig_compatibility"
trap 'cp "$orig_compatibility" "$COMPATIBILITY"; rm -rf "$test_tmp" "$orig_compatibility"' EXIT
export TMPDIR="$test_tmp"

run() { # run <script> <tool_name> <command> [session] [path] -> HINT | ALLOW | DENY | PASS
  local out
  out=$(jq -n --arg t "$2" --arg c "$3" --arg sid "${4:-test-session}" \
    '{session_id:$sid,tool_name:$t,tool_input:{command:$c}}' | PATH="${5:-$PATH}" "$1")
  if [[ "$out" == *'"permissionDecision":"allow"'* ]]; then echo ALLOW
  elif [[ "$out" == *'"permissionDecision":"deny"'* ]]; then echo DENY
  elif [[ "$out" == *additionalContext* ]]; then echo HINT
  else echo PASS; fi
}

t() { # t <script> <tool_name> <command> <expected> [session] [path]
  local got; got=$(run "$1" "$2" "$3" "${5:-test-session}" "${6:-}")
  if [[ "$got" != "$4" ]]; then
    echo "FAIL: $2 '$3' -> $got (want $4)"; fail=1
  fi
}

tc() { # tc <script> <tool_name> <command> <substring> <yes|no> [path] -> asserts substring in/out of raw output
  local out
  out=$(jq -n --arg t "$2" --arg c "$3" --arg sid test-session \
    '{session_id:$sid,tool_name:$t,tool_input:{command:$c}}' | PATH="${6:-$PATH}" "$1")
  if [[ "$5" == yes && "$out" != *"$4"* ]]; then
    echo "FAIL: expected '$3' hint to mention '$4' (got: $out)"; fail=1
  fi
  if [[ "$5" == no && "$out" == *"$4"* ]]; then
    echo "FAIL: expected '$3' hint to NOT mention '$4' (got: $out)"; fail=1
  fi
}

stub_bv_path() { # stub_bv_path <present|absent> -> PATH string, jq+bh always available
  local bin="$test_tmp/bin-bv-$1"
  mkdir -p "$bin"
  if [[ "$1" == present ]]; then
    printf '#!/usr/bin/env bash\necho "bv stub"\n' >"$bin/bv"
    chmod +x "$bin/bv"
  fi
  ln -sf "$(command -v jq)" "$bin/jq" 2>/dev/null
  ln -sf "$(command -v bh)" "$bin/bh" 2>/dev/null
  printf '%s:/usr/bin:/bin' "$bin"
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

# steer: triage-shaped bd calls conditionally mention bv when it's on PATH
tc "$STEER" Bash 'bd ready'  'bv' yes "$(stub_bv_path present)"
tc "$STEER" Bash 'bd ready'  'bv' no  "$(stub_bv_path absent)"
tc "$STEER" Bash 'bd show x' 'bv' no  "$(stub_bv_path present)"
t  "$STEER" Bash 'bh bd ready' PASS

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
t "$APPROVE" Bash 'bh hive list'                  ALLOW

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

# preflight reads the repository-owned compatibility constant.
sed 's/BH_REQUIRED_VERSION=">=0.3.0"/BH_REQUIRED_VERSION=">=0.4.0"/' "$orig_compatibility" >"$COMPATIBILITY"
expect_preflight manifest 0.3.0 jq HINT
cp "$orig_compatibility" "$COMPATIBILITY"

# Compatibility enforcement does not depend on jq.
expect_preflight nojq 0.3.0 nojq PASS

[[ $fail -eq 0 ]] && echo "hooks: all cases pass"
exit $fail
