#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

for name in RELEASE_CANDIDATE RELEASE_RECEIPT RELEASE_ARTIFACT RELEASE_DESTINATION_REPO APPROVED_CANDIDATE_DIGEST APPROVED_RECEIPT_DIGEST; do
  if [[ -z "${!name:-}" ]]; then
    echo "release acceptance unavailable: set $name from the allocated, reviewed canonical release" >&2
    exit 2
  fi
done

exec python3 scripts/check_release_candidate.py \
  --candidate "$RELEASE_CANDIDATE" \
  --receipt "$RELEASE_RECEIPT" \
  --artifact "$RELEASE_ARTIFACT" \
  --expected-candidate-digest "$APPROVED_CANDIDATE_DIGEST" \
  --expected-receipt-digest "$APPROVED_RECEIPT_DIGEST" \
  --destination-repo "$RELEASE_DESTINATION_REPO"
