#!/usr/bin/env bash
# Reject onboarding regressions: local skills are bh-namespaced and the external
# git-workspace plugin has a clear, non-invented source boundary.
set -eu
cd "$(dirname "$0")/.."

files=(README.md beadhive/skills/setup/SKILL.md beadhive/skills/setup-git-workspace/SKILL.md)
fail=0
if grep -nE 'briancripe/claude-plugins|git-workspace@briancripe-plugins' "${files[@]}"; then
  echo "onboarding: stale git-workspace marketplace coordinates found" >&2
  fail=1
fi
if ! grep -qF 'does not publish or verify a source for that external plugin' beadhive/skills/setup-git-workspace/SKILL.md; then
  echo "onboarding: external git-workspace plugin source boundary is undocumented" >&2
  fail=1
fi
if grep -nF 'https://github.com/orf/git-workspace' beadhive/skills/setup-git-workspace/SKILL.md; then
  echo "onboarding: unverified external git-workspace source found" >&2
  fail=1
fi
if grep -nE '/(setup|setup-git-workspace)([[:space:]`]|$)' "${files[@]}"; then
  echo "onboarding: bare local skill invocation found (use /bh:<skill>)" >&2
  fail=1
fi
if [[ $fail -eq 0 ]]; then
  echo "onboarding: coordinates and invocations clean"
fi
exit "$fail"
