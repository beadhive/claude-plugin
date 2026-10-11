#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

for name in RELEASE_PAYLOAD_CANDIDATE RELEASE_PROMOTION_CANDIDATE RELEASE_ARTIFACT APPROVED_PAYLOAD_CANDIDATE_DIGEST APPROVED_PROMOTION_CANDIDATE_DIGEST; do
  if [[ -z "${!name:-}" ]]; then
    echo "candidate QA unavailable: set $name from the allocated, independently reviewed release" >&2
    exit 2
  fi
done

args=(--payload-candidate "$RELEASE_PAYLOAD_CANDIDATE"
  --expected-payload-candidate-digest "$APPROVED_PAYLOAD_CANDIDATE_DIGEST"
  --promotion-candidate "$RELEASE_PROMOTION_CANDIDATE"
  --expected-promotion-candidate-digest "$APPROVED_PROMOTION_CANDIDATE_DIGEST"
  --artifact "$RELEASE_ARTIFACT" --qa-root .)

if [[ -n "${RELEASE_RECEIPT:-}" || -n "${RELEASE_PLAN:-}" || ( -n "${RELEASE_DESTINATION_REPO:-}" && -z "${RELEASE_AGF_DELIVERY:-}" ) || -n "${APPROVED_RECEIPT_DIGEST:-}" || -n "${APPROVED_PLAN_DIGEST:-}" || -n "${RELEASE_RECEIPT_MODE:-}" ]]; then
  for name in RELEASE_RECEIPT RELEASE_PLAN RELEASE_DESTINATION_REPO APPROVED_RECEIPT_DIGEST APPROVED_PLAN_DIGEST RELEASE_RECEIPT_MODE; do
    if [[ -z "${!name:-}" ]]; then
      echo "promotion metadata check unavailable: set $name along with all receipt-stage inputs" >&2
      exit 2
    fi
  done
  args+=(--receipt "$RELEASE_RECEIPT" --expected-receipt-digest "$APPROVED_RECEIPT_DIGEST"
    --promotion-plan "$RELEASE_PLAN" --expected-plan-digest "$APPROVED_PLAN_DIGEST"
    --destination-repo "$RELEASE_DESTINATION_REPO" --receipt-mode "$RELEASE_RECEIPT_MODE")
fi

if [[ -n "${RELEASE_AGF_DELIVERY:-}" || -n "${APPROVED_AGF_DELIVERY_DIGEST:-}" || -n "${RELEASE_AGF_PLAN:-}" || -n "${APPROVED_AGF_PLAN_DIGEST:-}" ]]; then
  for name in RELEASE_AGF_DELIVERY APPROVED_AGF_DELIVERY_DIGEST RELEASE_AGF_PLAN APPROVED_AGF_PLAN_DIGEST RELEASE_DESTINATION_REPO; do
    [[ -n "${!name:-}" ]] || { echo "AGF evidence check unavailable: set $name" >&2; exit 2; }
  done
  [[ -z "${RELEASE_RECEIPT:-}${RELEASE_PLAN:-}${RELEASE_RECEIPT_MODE:-}" ]] || { echo "AGF and legacy Hitch stages are separate" >&2; exit 2; }
  args+=(--agf-delivery "$RELEASE_AGF_DELIVERY" --expected-agf-delivery-digest "$APPROVED_AGF_DELIVERY_DIGEST"
    --agf-plan "$RELEASE_AGF_PLAN" --expected-agf-plan-digest "$APPROVED_AGF_PLAN_DIGEST"
    --destination-repo "$RELEASE_DESTINATION_REPO")
fi

exec python3 scripts/check_release_candidate.py "${args[@]}"
