# Destination-owned Claude QA overlay

The paired publisher overlays the exact paths in `destination-owned.json` beside the canonical
payload and root `release-receipt.json` payload-candidate sidecar. The publisher candidate
must independently bind every overlay file's Git mode and SHA-256. This overlay is public QA code
and documentation only; it contains no private corpus, credentials, or generated payload copy.

`check_release_candidate.py --producer-stage` checks an allocated producer payload plus its
payload-only candidate and pre-QA publisher base candidate. The regular transport mode is for the
paired caller: it requires both independently pinned candidates, the sidecar, and exact final QA
overlay closure, including the operator contract check. Receipt verification is a later optional
stage requiring independently pinned complete publisher candidate, plan, and receipt. A missing
receipt is expected before promotion and never counts as promotion acceptance.

The manually dispatched public workflow accepts only credential-free HTTPS inputs and grants
`contents: read`. It does not publish. The main `just check` remains runnable from either the
legacy public source checkout or the assembled candidate; existing hooks, onboarding, backfill,
operator, link, lint, and type checks are reused where their public inputs exist.
The Markdown linter disables only MD013 line-length findings in generated `COMPANIONS.md` files;
all other Markdown rules and relative-link checks still apply to them.
