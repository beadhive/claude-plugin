---
name: commit-conventions
description: >-
  This repo's commit-type and release rules. Use before writing any commit message in this
  repo, when choosing between feat/fix/refactor/chore, when running `just bump` / `cz bump`,
  or when preparing a release. Commit types drive the version bump, so typing matters.
---

# Commit types drive releases — default DOWN, not up

`cz bump` (see `.cz.toml`, `just bump-dry`) computes the version from commit types since the
last tag: `feat` → MINOR, `fix`/`refactor`/`perf` → PATCH, everything else → no bump. The
release takes the **highest** increment found, so one mistyped `feat` inflates the whole
release. When unsure, pick the *lower* type.

Decision test — from the perspective of someone who has the plugin installed:

| Would they notice… | Type |
|---|---|
| a new capability (new agent, new skill, new MCP tool, new command, changed install coordinates) | `feat` |
| something wrong now behaving correctly (broken link, wrong command in a skill, stale name an agent acts on) | `fix` |
| skill/agent text restructured with no behavior change (progressive-disclosure splits, rewording) | `refactor` |
| nothing at all (README, repo docs, lint config, justfile, CI, .cz.toml, tag/version housekeeping) | `chore` / `docs` / `ci` |

Explicitly NOT `feat`: adding a README or LICENSE, moving internal docs, adding lint/tooling,
reorganizing files, expanding a skill's prose. New *content* is not a new *capability*.

`feat` is reserved for changes a release announcement would mention. If the sentence "users can
now …" doesn't hold, it isn't a `feat`.

Breaking changes (renamed skill/agent a user may reference, removed tool, changed marketplace
name) get a `!` or `BREAKING CHANGE:` footer — at 0.x cz maps these to MINOR, from 1.0 to MAJOR.

## Release flow

- `just check` must pass before any commit (JSON manifests, links, residue grep, markdownlint).
- `just bump-dry` previews the next version; `just bump` writes plugin.json +
  marketplace.json + .cz.toml, updates the changelog, commits, and tags.
- Tags stay where the release was cut — never move a tag forward.
- Push releases with `git push --follow-tags`.
