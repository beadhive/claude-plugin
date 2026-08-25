# Orca integration reference

Use Orca when a Beadhive-managed clone should also appear in Orca's repository registry.
Orca registration and worktree delegation are separate opt-ins: registration makes a clone
visible to Orca; delegation asks Orca to perform selected Beadhive worktree operations. It does
not transfer ownership of Beadhive branches, seat paths, or worktree lifecycle to Orca.

This is a focused operating contract. Start with the [plugin router](../SKILL.md), then use
installed help as the syntax authority before running a command:

```bash
bh plugin orca --help
bh plugin orca sync --help
bh plugin orca fix-settings --help
```

## Enablement and ownership

Orca is disabled unless `orca.enabled` is true. That flag is the only plugin gate;
git-workspace is a required Beadhive dependency, not a second Orca gate. Set a fleet default in
Beadhive configuration, or write a hive-specific override on its `managed_repos` entry:

```yaml
orca:
  enabled: true
  # data_path: ~/.config/orca/orca-data.json
  # worktrees: true
  # worktrees:
  #   enabled: true
  #   fallback: false
```

`bh hive enable orca HIVE_ID` and `bh hive disable orca HIVE_ID` **mutate** that hive's
`managed_repos` entry. Omit `HIVE_ID` only when the current directory identifies the intended
hive. A hive's `orca.worktrees` setting (a boolean or `{enabled: ...}` mapping) overrides the
fleet setting. `orca.worktrees.fallback` is fleet-wide only.

Beadhive reads Orca's `repos` list and reads `settings.autoRenameBranchFromWork`. It registers
through the Orca CLI rather than editing registrations by hand. Beadhive deliberately does not
read or write Orca's `projects`, `projectHostSetups`, or any Orca orchestration database. The
one narrow exception is described under [Worktree delegation](#worktree-delegation): it uses
Orca CLI project-setup commands for onboarding bookkeeping, never direct JSON edits to those
collections.

## Registration and sync

Onboarding can explicitly enable and invoke Orca's registration hook:

```bash
# MUTATES hive configuration and may register the clone with Orca.
bh hive onboard PROVIDER/ORG/REPO --plugin orca
```

`--plugin orca` runs the hook even if the config flag was previously off. Enabling Orca in
configuration also makes the normal onboard lifecycle register a newly onboarded clone. Orca
problems are best-effort at this boundary: a missing CLI, unreadable state file, or failed Orca
subprocess reports a warning and does not abort onboarding.

To reconcile existing clones, preview first:

```bash
# Read-only preview: walks on-disk $GIT_WORKSPACE/GROUP/ORG/REPO clones.
bh plugin orca sync --dry-run

# MUTATES Orca's repo registry for clones it does not already know.
bh plugin orca sync
```

`sync` discovers only clones exactly three levels beneath `$GIT_WORKSPACE` that contain `.git`.
It is idempotent: after a successful run, the next run adds no already-registered path. A
missing Orca runtime or state source is still a warning at sync time, not a reason to block the
rest of the hive workflow.

When worktree delegation is enabled, a non-dry-run onboard or sync also *best-effort* asks Orca
to set the hive project's worktree base path. This wiring may warn and continue when Orca is
unavailable, no matching project setup exists, or the setup update fails. It is registration
bookkeeping, not proof that delegated worktrees are ready.

## Settings safety fence

Orca's global `settings.autoRenameBranchFromWork` should be off when delegation is used. If it
is on, Orca may rename a Beadhive branch after agent startup and break Beadhive's
`wt/bead/<type>/<id>` convention. Onboard and sync only tell the operator to change the setting
in Orca's Settings UI; they do not modify it.

Use the dedicated repair only after checking the installed help and confirming that the Orca
runtime is down (for example, inspect the native CLI's `orca status --help` before using its
version-specific status syntax):

```bash
# MUTATES only settings.autoRenameBranchFromWork in orca-data.json.
bh plugin orca fix-settings
```

`fix-settings` refuses when `orca status` says the runtime is up, prints the same Settings-UI
instruction, and exits unsuccessfully. That refusal is a write fence: do not work around it by
editing the JSON while the application may hold it open. With the runtime down, it atomically
writes the setting as `false` and preserves every other key in the data file.

## Worktree delegation

Set `orca.worktrees` to true only for hives where Orca should create and remove **new-branch**
Beadhive worktrees. This option is AND-gated by `orca.enabled`; worktree delegation is off if
Orca itself is disabled.

```bash
# Inspect the exact local worktree syntax first.
bh worktree --help
bh worktree add --help

# MUTATES: creates a Beadhive-managed worktree; it may be delegated to Orca.
bh worktree add --bead BEAD_ID
```

Beadhive continues to own the branch name, `wt/bead/<type>/<id>` layout, and the decision to
create, keep, or prune a worktree. Orca performs only delegated new-branch create/remove calls
so its own UI can show that worktree. Reattaching an existing branch always stays native Git,
even when delegation is configured; clean `verify-*` worktrees used by `bh work check` and
`bh work submit` also always stay native.

Delegated create and remove fail closed by default. If Orca is down, returns a bad result, or
does not honor the expected path/branch, Beadhive raises rather than silently pretending native
Git succeeded. Set the global `orca.worktrees.fallback: true` only when a warning followed by a
native-Git fallback is the intended operational policy.

Removal has an important branch-retention distinction:

- `bh worktree rm` is the durable-branch path. Beadhive detaches first so Orca's removal does
  not delete the branch.
- `bh worktree prune` is for already-merged disposable branches. It does not detach first, so
  Orca's cleanup matches native prune behavior.

Both commands mutate worktree state. Inspect their installed help, and use the native Beadhive
commands rather than calling `orca worktree` directly for a managed seat:

```bash
bh worktree rm --help
bh worktree prune --help
```

## Readiness and diagnostics

Use Beadhive's read-only readiness report before relying on delegation:

```bash
bh hive ready --verbose
bh worktree list
bh worktree status
bh plugin orca sync --dry-run
```

With Orca enabled, readiness reports whether the hive clone is registered. With worktree
delegation enabled, it additionally reports `ok` only when the Orca runtime is reachable and
`autoRenameBranchFromWork` is off. A `warn` identifies either a down runtime (delegated
operations will hard-fail, or fall back if that global policy is enabled) or auto-rename being
on. Readiness, onboard, retire, and sync stay warning-only for normal Orca availability
problems; only delegated create/remove intentionally enforce the hard boundary.

For a native Orca diagnostic, first inspect `orca --help` and `orca status --help`; do not copy
flags from this reference into a different Orca version. If the data file is unreadable or the
CLI is missing, correct the native Orca installation/state problem, then re-run the read-only
checks above.

## Retire boundary

Retiring a hive does not deregister it from Orca. Beadhive only names the manual Orca operation
because automatically deleting a project setup could discard state the operator meant to keep.
Before retirement, use `bh hive retire --help`; its default is a dry-run safety plan and the
non-dry-run forms can archive or, when explicitly selected, purge a clone.

After a deliberate retirement, inspect installed Orca help before running its native
de-registration flow. Beadhive's current guidance is to find the setup with
`orca project setups --json`, then run `orca project setup-delete --setup SETUP_ID` **only after
confirming the target**. That native command mutates Orca project-setup state. Do not remove
entries directly from `orca-data.json`, and do not treat retirement as a request to delete
unrelated Orca projects or host setup data.

## Limits

Orca registration is a convenience integration, not a replacement for git-workspace, Git, or
Beadhive worktree management. Beadhive never owns Orca's project definitions, host setups,
orchestration database, or broader native settings. For exhaustive native installation and CLI
usage, use Orca's own installed `--help` and documentation; return to the
[plugin router](../SKILL.md) to operate another Beadhive integration.
