#!/usr/bin/env bash
# Guard the canonical operator contract and the two deliberately opt-in style variants.
set -euo pipefail
cd "$(dirname "$0")/.."

contract="beadhive/OPERATOR-COMMUNICATION.md"
brief="beadhive/output-styles/beadhive-operator-brief.md"
verbose="beadhive/output-styles/beadhive-operator-brief-verbose.md"
skill="beadhive/skills/operator-communication/SKILL.md"

extract() {
  local file=$1 start=$2 end=$3
  sed -n "/$start/,/$end/p" "$file"
}

require() {
  grep -Fq -- "$2" "$1" || { echo "missing '$2' in $1" >&2; exit 1; }
}

for style in "$brief" "$verbose"; do
  require "$style" "keep-coding-instructions: true"
  require "$style" "force-for-plugin: false"
  require "$style" "bh:operator-communication"
  ! grep -Fq "## Decision ask" "$style"
  ! grep -Fq "## Status summary" "$style"
done

require "$brief" "name: Beadhive Operator Brief (Concise, Recommended)"
require "$verbose" "name: Beadhive Operator Brief (Verbose Motivation)"
require "$contract" "The concise form is the recommended default."

for marker in shared-rules concise-motivation verbose-motivation; do
  case "$marker" in
    shared-rules)
      expected=$(extract "$contract" "<!-- $marker:start -->" "<!-- $marker:end -->")
      [ "$expected" = "$(extract "$brief" "<!-- $marker:start -->" "<!-- $marker:end -->")" ]
      [ "$expected" = "$(extract "$verbose" "<!-- $marker:start -->" "<!-- $marker:end -->")" ]
      ;;
    concise-motivation)
      expected=$(extract "$contract" "<!-- $marker:start -->" "<!-- $marker:end -->")
      [ "$expected" = "$(extract "$brief" "<!-- $marker:start -->" "<!-- $marker:end -->")" ]
      ;;
    verbose-motivation)
      expected=$(extract "$contract" "<!-- $marker:start -->" "<!-- $marker:end -->")
      [ "$expected" = "$(extract "$verbose" "<!-- $marker:start -->" "<!-- $marker:end -->")" ]
      ;;
  esac
done

require "$skill" "## Decision ask"
require "$skill" "## Status summary"
require "$skill" "AskUserQuestion"
require "$skill" "Worked lifecycle example"

for role in control dispatcher planner reviewer; do
  require "beadhive/skills/$role/SKILL.md" "bh:operator-communication"
done
for agent in supervisor dispatcher planner reviewer; do
  require "beadhive/agents/$agent.md" "bh:operator-communication"
done

echo "operator communication: contract and wiring valid"
