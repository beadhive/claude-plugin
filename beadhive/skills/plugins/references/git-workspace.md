# git-workspace integration reference

Use this reference for the git-workspace integration surface. It follows the shared contract in
the [bh plugins router](../SKILL.md): purpose, prerequisites and gating, ownership boundary,
normal workflow, diagnostics, cleanup and safety, limitations, and deeper guidance.

## Purpose and required dependency

git-workspace is the workspace manager behind Beadhive's repository layout. For this version of
`bh`, it is a **required workspace dependency**, not an optional registry plugin like the other
integrations in this router. The `bh plugin git-workspace` namespace is the Beadhive inspection
surface mounted over that dependency; it does not make git-workspace optional or replace the
native tool.

Use this reference when an existing workspace needs inspection, group/auth diagnostics, or a
handoff to native git-workspace. For a first machine setup, load the
[bh:setup-git-workspace walkthrough](../../setup-git-workspace/SKILL.md) instead. It chooses the
safe path for an already-configured workspace, an existing directory of repos, or a greenfield
workspace.

## Prerequisites and gating

Probe the installed surfaces before suggesting a version-specific command:

```bash
command -v bh
command -v git-workspace
bh plugin --help
bh plugin git-workspace --help
```

`bh setup check` is the canonical post-bh dependency check. It reports a missing
git-workspace binary; do not reimplement that dependency gate in this reference. A usable
workspace also needs `GIT_WORKSPACE` (or git-workspace's documented default), a readable
`workspace.toml`, and provider credentials for every configured group. The walkthrough covers
those first-time checks and safe remediation.

## Repo-group identity

Beadhive identifies a repository by the three-level triplet
`<group>/<account>/<repo>` under `$GIT_WORKSPACE`:

```text
$GIT_WORKSPACE/<group>/<account>/<repo>
```

In `workspace.toml`, each `[[provider]]` block declares one **repo group**:

- `provider` is the auth/fetch mechanism, such as `github` or `gitlab`;
- `name` is the account, organization, or group queried through that mechanism;
- `path` is the on-disk group folder, the first segment of the triplet.

Do not use “provider” as a synonym for the group. Several groups can use the same provider,
and the group path is part of the hive identity. `bh plugin git-workspace groups` prints the
groups known by the integration, including their provider, account, and filters. Use its
installed `--help` output for options; this command is an inspection probe.

## Ownership boundary

Beadhive reads the workspace configuration and lockfile metadata to discover repo groups,
resolve `<group>/<account>/<repo>` paths, and diagnose whether the on-disk workspace matches
the layout it requires. `bh` does not write `workspace.toml`, rewrite the lockfile, clone or
archive repositories, or manage provider tokens. The native git-workspace tool owns those
configuration/lockfile writes and provider API operations.

Consequently:

- use `bh plugin git-workspace groups`, `bh doctor`, and `bh hive survey` to inspect;
- use native git-workspace commands for intentional group/config/update mutations;
- use `bh hive onboard`, `bh hive retire`, and Beadhive worktree commands for Beadhive's hive,
  registry, branch, and worktree lifecycle.

Do not repair a group by hand in a Beadhive registry file, and do not treat a successful
`groups` listing as proof that provider authentication or every clone is healthy.

## Normal workflow

Start read-only and make the ownership handoff explicit:

```bash
# Beadhive integration and group inspection (read-only)
bh plugin git-workspace groups
bh doctor

# Native workspace inspection (read-only; syntax is version-dependent)
git-workspace --help
git workspace list
```

If the workspace is not configured, or if this is the user's first setup, stop and load
[bh:setup-git-workspace](../../setup-git-workspace/SKILL.md). That walkthrough routes to the
external upstream skills as appropriate:

| Need | Handoff |
|---|---|
| Install git-workspace and configure credentials | `git-workspace:install` |
| Import existing repos safely before an update | `git-workspace:import` |
| Define repo groups and provider filters | `git-workspace:providers` |
| Understand the complete first-timer flow | `bh:setup-git-workspace` |

Those `git-workspace:*` skills are supplied by the external git-workspace plugin distribution;
they are not shipped by this Beadhive Claude plugin. Follow the installed distribution's source
and syntax, and return here for Beadhive diagnostics after it is configured.

Only after the import safety gate is green and the operator has confirmed the target should a
native update be run. Inspect the exact installed help first:

```bash
git-workspace update --help
# MUTATES: use the native update command only after the import/backup checks.
git workspace update
```

An update can clone new repositories and move no-longer-tracked repositories to the native
archive location. It is not a read-only Beadhive probe.

## Provider and auth diagnostics

Run `bh doctor` for the per-group auth section. It reports the effective Git identity and
signing key, `insteadOf` URL aliases, and `includeIf gitdir:` scoping for each group. It also
warns when lockfile paths are nested deeper than the required triplet. Use these checks when a
group appears in `groups` but onboarding, cloning, or signing fails:

```bash
bh doctor
bh plugin git-workspace groups
bh hive survey --available
```

Provider APIs still require their native credentials. For example, the walkthrough documents
`GITHUB_TOKEN` for GitHub groups and `GITLAB_TOKEN` for GitLab groups. Check that a token is
present in the shell or approved credential store without printing its value; never commit a
token to `workspace.toml`, a dotfiles repository, or a hive. After correcting native auth,
repeat the read-only probes before retrying an update or `bh hive onboard`.

## Cleanup and safety

The `groups`, `doctor`, `survey`, and native list/status probes above do not mutate the
workspace. Native config, group, update, import, and archive operations do. Before importing a
directory containing existing repositories, use `git-workspace:import`; it classifies dirty or
unpublished work, creates the required backups, and verifies safety before any update. Never
point `GIT_WORKSPACE` at a repository itself, and never run an update merely to test this
reference.

Beadhive's hive retirement and worktree cleanup have their own confirmation and retention
rules. They do not grant permission to delete native git-workspace configuration or lockfile
state. Confirm the exact repo group and native command help before any archive, move, or remove
operation.

## Current limitations and deeper guidance

The integration reports what the installed `bh` and git-workspace versions expose; command
flags, provider names, lockfile details, and supported filters can change. Probe `bh plugin
git-workspace --help` and `git-workspace <subcommand> --help` rather than guessing flags.
`bh` validates the three-level path contract but does not own the native workspace's complete
schema, clone policy, archive policy, provider APIs, or credentials.

For installation, import, provider schema, and first-time setup, follow the routed
`git-workspace:*` skills and the [bh:setup-git-workspace walkthrough](../../setup-git-workspace/SKILL.md).
For Beadhive registry or hive lifecycle questions, return to the control-plane guidance; for
this integration's stable intent and ownership boundary, return to the [bh plugins router](../SKILL.md).
