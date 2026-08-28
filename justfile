# list recipes
default:
    @just --list

# fast gate: manifests parse + links resolve + no legacy-name regressions + hook self-tests + markdown lint + type-check
[group('check')]
check: check-json check-links check-residue check-onboarding check-hooks check-backfill lint-md check-types

# ensure onboarding docs keep local skill namespaced and external coordinates explicit
[group('check')]
check-onboarding:
    ./scripts/check-onboarding.sh

# self-test the PreToolUse hook scripts (bd steering + read-only auto-approve)
[group('check')]
check-hooks:
    ./scripts/test-hooks.sh

# exercise empty/missing-corpus behavior in the backfill reconcile helper
[group('check')]
check-backfill:
    ./scripts/test-backfill.sh

# type-check the retro skill's python scripts, failing on unused imports/vars (scoped pyrightconfig.json)
[group('check')]
check-types:
    uvx pyright -p beadhive/skills/retro/scripts/pyrightconfig.json beadhive/skills/retro/scripts/

# validate the three JSON manifests parse
[group('check')]
check-json:
    python3 -c "import json; [json.load(open(f)) for f in ['.claude-plugin/marketplace.json', 'beadhive/.claude-plugin/plugin.json', 'beadhive/.mcp.json']]; print('json: manifests valid')"

# verify every relative markdown link resolves
[group('check')]
check-links:
    ./scripts/check-links.sh

# grep for retired-name / stale-path regressions (patterns fixed pre-0.1.0)
[group('check')]
check-residue:
    ! grep -rnE 'bh@workspace|~/\.ws|WS_[A-Z_]+|crew/|coord/|superintendent|agf-and-planes|/Users/' beadhive README.md --include='*.md'
    @echo "residue: clean"

# lint markdown docs (config: .markdownlint-cli2.jsonc)
[group('check')]
lint-md:
    markdownlint-cli2

# launch an interactive Claude session that reviews the plugin with the plugin-dev tooling
[group('review')]
review:
    claude "Use the plugin-dev:plugin-structure and plugin-dev:skill-development skills for review criteria, then run the plugin-dev:plugin-validator and plugin-dev:skill-reviewer agents over this repo (marketplace root + the beadhive/ plugin). Compile a combined report ranked by severity, then discuss findings and direction with me before changing anything."

# preview the next version bump from conventional commits (no writes)
[group('release')]
bump-dry:
    uvx --from commitizen cz bump --dry-run

# bump version (plugin.json + marketplace.json + .cz.toml), update changelog, commit + tag
[group('release')]
bump:
    uvx --from commitizen cz bump
