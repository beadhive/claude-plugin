#!/usr/bin/env bash
# Verify every relative markdown link in the plugin resolves to a real file.
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0
while IFS= read -r f; do
  d=$(dirname "$f")
  while IFS= read -r l; do
    case "$l" in http* | mailto*) continue ;; esac
    [ -e "$d/$l" ] || {
      echo "BROKEN: $f -> $l"
      fail=1
    }
  done < <(grep -oE '\]\([^)#]+\)' "$f" | sed 's/](\(.*\))/\1/')
done < <(find beadhive README.md docs -name '*.md' 2>/dev/null)

[ "$fail" -eq 0 ] && echo "links: all relative links resolve"
exit "$fail"
