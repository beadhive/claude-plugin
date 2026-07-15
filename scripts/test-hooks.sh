#!/usr/bin/env bash
# Self-test for the plugin's PreToolUse hook scripts.
set -u
cd "$(dirname "$0")/.."
STEER=beadhive/scripts/bd-steer.sh
APPROVE=beadhive/scripts/approve-readonly.sh
fail=0

run() { # run <script> <tool_name> <command> -> HINT | ALLOW | PASS
  local out
  out=$(jq -n --arg t "$2" --arg c "$3" '{tool_name:$t,tool_input:{command:$c}}' | "$1")
  if [[ "$out" == *'"permissionDecision":"allow"'* ]]; then echo ALLOW
  elif [[ "$out" == *additionalContext* ]]; then echo HINT
  else echo PASS; fi
}

t() { # t <script> <tool_name> <command> <expected>
  local got; got=$(run "$1" "$2" "$3")
  if [[ "$got" != "$4" ]]; then
    echo "FAIL: $2 '$3' -> $got (want $4)"; fail=1
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
t "$APPROVE" Bash 'bh rig ls'                     ALLOW

# approve: mutating, compound, or unrelated falls through to a prompt
t "$APPROVE" Bash 'bd update x --status done'     PASS
t "$APPROVE" Bash 'bd create foo'                 PASS
t "$APPROVE" Bash 'bd delete x'                   PASS
t "$APPROVE" Bash 'bh work merge'                 PASS
t "$APPROVE" Bash 'bh rig onboard github/x/y'     PASS
t "$APPROVE" Bash 'bh config set a b'             PASS
t "$APPROVE" Bash 'bd show x && rm -rf /'         PASS
t "$APPROVE" Bash 'bd list > /tmp/x'              PASS
t "$APPROVE" Bash 'bd list | tee /tmp/x'          PASS
t "$APPROVE" Bash 'git status'                    PASS

# approve: read-only bh MCP tools (matcher pre-scopes; script trusts mcp__*)
t "$APPROVE" mcp__plugin_bh_bh__rigs_status ''    ALLOW
t "$APPROVE" mcp__bh__plan_check ''               ALLOW

[[ $fail -eq 0 ]] && echo "hooks: all cases pass"
exit $fail
