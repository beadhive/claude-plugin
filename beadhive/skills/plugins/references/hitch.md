# agent-hitch integration reference

Use this reference for the agent-hitch integration surface. It follows the shared contract in the
[bh plugins router](../SKILL.md): purpose, prerequisites and gating, ownership boundary, normal
workflow, diagnostics, cleanup and safety, limitations, and deeper guidance.

## Purpose and enablement gate

[agent-hitch](https://github.com/briancripe/agent-hitch) resolves a Hitch Pack profile into a
harness-specific Config Directory and launches that harness against the resolved configuration.
Beadhive exposes this as an optional, explicit launch integration. It is disabled by default and
does not change the normal Beadhive launch path when it is off.

Enable it in Beadhive configuration only when this host has a Hitch checkout and the operator wants
to launch through Hitch:

```yaml
hitch:
  enabled: true
  repo: ~/workspace/github/briancripe/agent-hitch
  # command: hitch       # optional executable/path override
  # root: ~/.beadhive/hitch  # persistent Config Directory root override
```

The flag is layered: a hive-specific `hitch.enabled` value overrides the global value, and the
default is `false`. Hitch has no AND-gate on git-workspace, Orca, or Observaloop. `hitch.repo` is
required to launch and must be a checkout containing the profile and catalog files that Hitch
expects (`profiles/local.yaml`, `catalogs/local.yaml`, and the referenced `packs/`). Beadhive does
not install or update that checkout.

## Target and profile model

The `up` command takes two required positional values:

```text
bh plugin hitch up <target> <profile>
```

`target` is the Beadhive-side harness name. Probe the installed wrapper before relying on the
current set:

```bash
bh plugin hitch --help
bh plugin hitch up --help
```

The installed help currently lists `claude`, `opencode`, and `codex`. Beadhive translates those
names to the native Hitch target names; do not pass a native name to the Beadhive wrapper unless
the installed `bh plugin hitch up --help` says it accepts it. Hitch itself can still reject a
target or a requested launch mode, so the native help and capability diagnostics remain the final
authority.

`profile` is a name declared by the configured checkout's profile file. It selects one or more
packs; it is not a Beadhive seat, branch, bead, or worktree identifier. Do not guess profile names
from this document. Inspect the checkout and use Hitch's installed profile help/preflight commands:

```bash
hitch profile --help
hitch profile preflight --help
```

## Normal workflow

1. Probe the installed syntax and target surface:

   ```bash
   bh plugin --help
   bh plugin hitch --help
   bh plugin hitch up --help
   ```

2. Check optional integration readiness without launching a provider:

   ```bash
   bh hive ready --verbose
   bh doctor --help
   ```

   With Hitch disabled, readiness is `na` and does not probe the executable or checkout. With it
   enabled, readiness checks the configured command and repository files; `bh doctor --seats` (if
   listed by the installed help) adds per-seat/profile preflight detail.

3. Launch explicitly, using a profile that exists in `hitch.repo`:

   ```bash
   bh plugin hitch up claude developer
   ```

   The wrapper verifies the enablement gate, target, `hitch` executable, and repository path,
   then invokes native `hitch up` with absolute profile/catalog paths and the configured root. It
   hands off with inherited standard input/output/error and returns Hitch's exit code unchanged.
   A failed preflight therefore fails the launch; it does not fall back to ambient harness config
   or to another Beadhive launcher.

4. If the installed help offers them, use the native launch controls deliberately. In the current
   wrapper these include `--workspace`, `--task`, `--detached`/`-d`, `--role`, and
   `--explain`/`--dry-run`. `--explain` writes and prints a redacted launch manifest without
   starting the provider. `--role` chooses a declared agent inside the selected profile; it does
   not choose the profile itself. Treat every option as version-sensitive and re-check help after
   upgrading either CLI.

## Ownership boundary

| Concern | Owner | Boundary |
| --- | --- | --- |
| `hitch.enabled`, `hitch.repo`, `hitch.command`, and `hitch.root` | Beadhive configuration | Global defaults and hive overrides; no implicit installation or checkout mutation. |
| Profile composition, target capability checks, preflight, Config Directory build, and provider launch | agent-hitch | Hitch's installed CLI and adapters decide what a profile/target can do. |
| Pack contents, profile/catalog edits, provider binaries, credentials, and provider-native state | Operator / native tool | Repair these in the Hitch checkout or native harness, not in Beadhive's config. |
| Git hives, branches, beads, and worktrees | Beadhive | Hitch receives a workspace; it does not own Beadhive worktree or branch lifecycle. |

For the current Beadhive adapter, the default Hitch root is `~/.beadhive/hitch` and is persistent;
`hitch.root` can relocate it. This root is independent of `worktrees.ephemeral`: a Config Directory
may contain provider authentication state and is intentionally not recreated for every worktree.
Hitch decides when a profile/target output is built or reused. Do not edit generated files or copy
the operator's personal harness directory into the root by hand.

## Readiness and lifecycle boundaries

Readiness is a diagnostic, not a launch or provisioning hook. When enabled, Beadhive checks for the
configured Hitch command and the required profile/catalog files. A missing command, missing
repository, or malformed checkout is reported as a warning/missing prerequisite; Beadhive does
not silently claim that a provider can run. Profile-level runnability is Hitch's own
`profile preflight` result. A nonzero preflight reports a blocker; a successful preflight may still
report a reduced target capability. Use the exact target name printed by the installed native help
when running preflight directly.

Hitch has no Beadhive `onboard` hook, `retire` hook, or worktree create/remove delegation. Enabling
it does not build a Config Directory during `bh hive onboard`, `bh hive retire`, `bh work claim`,
or worktree provisioning. The only lifecycle action documented here is the explicit `up` command.
There is no `bh plugin hitch down` command in the current wrapper help; do not invent one.

## Headless and non-TTY limitations

The Beadhive wrapper inherits stdio; it does not allocate a pseudo-terminal. An attached interactive
launch therefore needs the target/provider's normal terminal support. In CI, pipes, and other
non-TTY contexts, do not expect an interactive prompt to become usable merely because it was
started through `bh`.

The installed Hitch help describes three modes: attached interactive (no mode option), attached
headless (`--task`), and detached headless (`--task -d`). The current `bh` wrapper exposes
`--task` and `--detached`/`-d`; Hitch refuses detached mode without a task. Whether a target supports
each mode is declared by the installed native adapter, not by this reference. Probe
`hitch up --help` and let Hitch's refusal explain unsupported combinations. For unattended runs,
provide an explicit task and use detached mode only when both installed helps and the target's
capability report support it.

## Diagnostics and failure recovery

Start with read-only probes, keeping the output from the failing command:

```bash
bh plugin hitch up --help
bh hive ready --verbose
bh doctor --help
hitch status --help
hitch profile preflight --help
```

Common failures have distinct owners:

- **Integration disabled** — set the intended global or hive-specific `hitch.enabled` value; no
  provider subprocess is started while it is false.
- **Unknown target/profile** — compare target syntax with installed `bh plugin hitch up --help`;
  verify the profile is declared in `profiles/local.yaml`.
- **Hitch not found** — install agent-hitch or correct `hitch.command`; confirm with `command -v`
  and `hitch --help`.
- **Repository/configuration failure** — correct `hitch.repo`, then verify
  `profiles/local.yaml`, `catalogs/local.yaml`, and referenced packs are readable.
- **Preflight or provider failure** — run the native preflight for the selected target/profile and
  follow the named missing binary, unsupported platform, pack, or credential diagnostic. Hitch's
  nonzero status is intentionally propagated by `bh`; do not work around it by falling back to a
  personal harness config.
- **Authentication or provider-native state** — authenticate/configure the provider inside the
  Config Directory it uses. Beadhive does not copy `~/.claude`, `~/.codex`, or another native
  home into that directory.

Use `--explain`/`--dry-run` when the installed help lists it to inspect a redacted launch manifest
without starting a provider. Avoid deleting the persistent Hitch root as a first diagnostic:
doing so can discard native authentication and run state. If cleanup is necessary, inspect the
installed Hitch `config-dir` and `run` help and use native Hitch commands for native state.

## Deeper guidance

For pack authoring, target support, installation, and exhaustive syntax, use the
[agent-hitch repository](https://github.com/briancripe/agent-hitch) and its installed `hitch
--help`, `hitch up --help`, and `hitch profile --help`. Return to the [plugin router](../SKILL.md)
when operating another Beadhive integration.
