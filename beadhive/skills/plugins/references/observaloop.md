# Observaloop integration reference

Use this reference for the Observaloop integration surface. It follows the shared contract in the
[bh plugins router](../SKILL.md): purpose, prerequisites and gating, ownership boundary, normal
workflow, diagnostics, cleanup and safety, limitations, and deeper guidance.

## Purpose and boundary

Observaloop gives a hive a named, isolated OpenTelemetry collector profile. Beadhive derives that
name from the hive prefix, then routes telemetry from the hive's managed worktrees to the profile.
The profile is a native Observaloop process and configuration lifecycle; it is not a Bead, a
dashboard, or a per-command switch.

Keep these three layers separate:

| Layer | What it controls | Typical action |
| --- | --- | --- |
| Beadhive telemetry | Whether `bh` emits OTLP signals and its base configuration | Set `otel.enabled`, endpoint, and protocol. |
| Observaloop profile | The hive's collector, OTLP ports, and profile-specific routing | Provision it during onboard/init with `--observaloop`. |
| Plugin command surface | The small Beadhive control surface for the current hive profile | Inspect with `status`; intentionally stop it with `down`. |

Enabling telemetry alone does **not** create or start an Observaloop profile. Conversely, a
profile is useful only when OTel is enabled: `observaloop.enabled` is coupled to
`otel.enabled`, and is treated as off when OTel is off. A profile may have a manifest and an
endpoint while its collector is stopped; an address is not evidence that anything is listening.

Beadhive owns the hive naming, its OTel configuration, worktree endpoint overlay, and its
dashboard/preset attempt. Observaloop owns the shared observability stack, profile manifests,
collector processes, and native diagnostics. Do not manually edit Beadhive's worktree overlay;
use the configuration and lifecycle paths below.

## Prerequisites and configuration

Probe the installed binary before proposing a mutating operation; it is the syntax authority for
the version on this host:

```bash
bh plugin --help
bh plugin observaloop --help
bh config show
```

The following must be true before a profile can route Beadhive telemetry:

- `bh` is installed with its OTel support. The [setup guide](../../setup/SKILL.md#phase-2--install-bh-pre-bh)
  shows the supported `beadhive[otel]` installation.
- OTel is enabled and has a deliberate endpoint/protocol configuration. Use `grpc` or
  `http/protobuf`; do not rely on a guessed protocol.
- The Observaloop Claude plugin/MCP server is installed and reachable, or
  `observaloop.command` names a working launch command. Its container runtime and shared stack
  must also be usable.
- The hive is registered well enough for Beadhive to derive its profile name from the hive prefix.

Configure and read back the state before provisioning:

```bash
bh config set otel.enabled true
bh config set otel.endpoint <otlp-endpoint>
bh config set otel.protocol grpc             # or http/protobuf
bh config set observaloop.enabled true
bh config get otel.enabled
bh config get observaloop.enabled
```

`otel.endpoint` is the base export configuration. For a running Observaloop-enabled hive,
Beadhive writes a local, ignored endpoint overlay when it creates a managed worktree, so that
worktree's `bh` telemetry reaches the hive profile and carries the profile identity. An explicit
environment value still takes precedence. This is why a profile process must be ready, not merely
configured.

## Provision a hive profile

For a new hive, enable the configuration and include `--observaloop` when onboarding. Add
`--furnish` when the hive should also receive tracked in-repo AGF furniture; furnishing and
profile provisioning are related setup work, but they are not the same lifecycle.

```bash
bh hive onboard <provider/org/repo> --furnish --observaloop
```

For an existing hive, run the init path from its main checkout after configuring OTel and
Observaloop:

```bash
bh hive init --observaloop
```

That path ensures the derived profile, brings its collector up, and best-effort applies the
Beadhive collector preset and Grafana dashboard. A missing plugin, container runtime, collector,
or visualizer warns and lets hive setup continue; fix the prerequisite and re-run the provisioning
step rather than assuming a partial attempt is healthy.

## Status, scope, and readiness

`status` is read-only and reports the profile derived for the **current hive**, whether the
integration is enabled and available, its running state, and the protocol-matched endpoint:

```bash
bh plugin observaloop status
bh hive ready -v
bh doctor
```

A hive has one profile shared by its ordinary managed worktrees. It is not one profile per Bead,
seat, or worktree. Worktree creation may ensure the shared profile is running and then write the
local `.bh/otel.env` routing overlay; temporary validation checkouts are not provisioned as
profiles. Run `status` from the main checkout or any worktree belonging to the hive whose profile
you intend to inspect.

Use the result as a probe, not as a start command:

- `enabled=no` means enable both the OTel and Observaloop configuration layers first.
- `available=no` means install/repair the Observaloop plugin or its configured MCP launch command.
- `state=down` means the profile manifest can exist without a live collector; re-run the provision
  path after checking the native stack.
- A healthy profile does not prove that a remote OTLP destination, Grafana dashboard, or every
  emitted signal is healthy. Continue with `bh hive ready -v`, `bh doctor`, and the native probes.

Native Observaloop owns deeper collector and visualizer checks. In the Observaloop MCP surface,
use its profile status, stack status, collector status, and visualizer status tools; probe the
installed native help before selecting an operation. Container/process failures, unavailable
ports, and visualizer reachability belong there. The [controller's telemetry guidance](../../control/SKILL.md#factory-telemetry--observe-and-report)
covers Beadhive-side reporting; the [Observaloop project](https://github.com/briancripe/observaloop)
covers its collector, dashboard, and query workflows without duplicating them here.

## Safe teardown and the asymmetric lifecycle

There is deliberately no `bh plugin observaloop up` verb. Starting and furnishing are owned by
`bh hive onboard --observaloop` or `bh hive init --observaloop`, which can coordinate profile
creation, profile startup, and Beadhive's optional preset/dashboard work. Do not invent an `up`
command from `status` output; use the installed CLI help and the provisioning path above.

`down` is the explicit, hive-scoped retire action:

```bash
bh plugin observaloop status
bh plugin observaloop down
bh plugin observaloop status
```

It stops the current hive profile's collector. It does not disable `otel.enabled` or
`observaloop.enabled`, delete the profile manifest, remove Beadhive configuration, or tear down
the workstation-wide Observaloop stack and its shared telemetry storage. Because every managed
worktree for that hive uses the same profile, confirm that no active worktree needs routing before
running it. Re-provision later with `bh hive init --observaloop` when the collector should return.

Treat a failed or unavailable `down` as an unknown native state: inspect `status`, then the native
profile/stack diagnostics, rather than deleting containers, profile directories, or telemetry
volumes by hand. Those resources are native-operator owned and may be shared with other profiles.

## Current limitations

- Beadhive's plugin surface intentionally exposes only `status` and `down`; native profile and
  stack operations remain in Observaloop.
- The integration is best-effort. A missing dependency or failed native call must not block normal
  Beadhive work, but it does mean telemetry routing may be off.
- Dashboard and collector-preset installation are auxiliary readiness work, not proof that telemetry
  is flowing. Prefer probe-first diagnosis over copying metric or dashboard catalogs into this
  reference.
