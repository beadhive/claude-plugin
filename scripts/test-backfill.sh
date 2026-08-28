#!/usr/bin/env bash
# Regression tests for the backfill reconcile helper.
set -u
cd "$(dirname "$0")/.."

RECONCILE=beadhive/skills/backfill/scripts/reconcile.sh
fail=0
test_tmp=$(mktemp -d)
trap 'rm -rf "$test_tmp"' EXIT

# Keep the tests independent of a live bd/Dolt service while retaining jq and system tools.
test_bin="$test_tmp/bin"
mkdir -p "$test_bin"
ln -s "$(command -v jq)" "$test_bin/jq"
test_path="$test_bin:/usr/bin:/bin"

new_hive() {
  local name="$1" hive="$test_tmp/$1"
  git init -q "$hive"
  mkdir -p "$hive/.beads" "$hive/docs/design"
  printf '%s\n' '---' '- Beads: -looks-like-an-option' '---' > "$hive/docs/design/001-example.md"
  printf '%s\n' "$hive"
}

run_reconcile() {
  local name="$1" hive="$2"
  if ! PATH="$test_path" "$RECONCILE" "$hive" > "$test_tmp/$name.out" 2> "$test_tmp/$name.err"; then
    echo "FAIL: $name exited nonzero"
    fail=1
  fi
}

expect_unmatched_without_errors() {
  local name="$1"
  if ! grep -q $'^UNMATCHED\tdocs/design/001-example.md\t-' "$test_tmp/$name.out"; then
    echo "FAIL: $name did not classify the doc as UNMATCHED"
    fail=1
  fi
  if [ -s "$test_tmp/$name.err" ]; then
    echo "FAIL: $name wrote to stderr: $(cat "$test_tmp/$name.err")"
    fail=1
  fi
}

missing_hive=$(new_hive missing-corpus)
run_reconcile missing-corpus "$missing_hive"
expect_unmatched_without_errors missing-corpus

empty_hive=$(new_hive empty-corpus)
: > "$empty_hive/.beads/issues.jsonl"
run_reconcile empty-corpus "$empty_hive"
expect_unmatched_without_errors empty-corpus

linked_hive=$(new_hive linked-corpus)
printf '%s\n' '{"id":"bh-example","title":"Example"}' > "$linked_hive/.beads/issues.jsonl"
printf '%s\n' '---' '- Beads: bh-example' '---' > "$linked_hive/docs/design/001-example.md"
run_reconcile linked-corpus "$linked_hive"
if ! grep -q $'^PRESENT-needs-stamp\tdocs/design/001-example.md\tbh-example\tfrontmatter$' "$test_tmp/linked-corpus.out"; then
  echo "FAIL: linked-corpus did not recover the frontmatter bridge"
  fail=1
fi
if [ -s "$test_tmp/linked-corpus.err" ]; then
  echo "FAIL: linked-corpus wrote to stderr: $(cat "$test_tmp/linked-corpus.err")"
  fail=1
fi

[ "$fail" -eq 0 ] && echo "backfill: all cases pass"
exit "$fail"
