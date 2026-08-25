# Herdr integration reference

Use this reference for `bh plugin herdr`: Beadhive's opt-in, persistent terminal-agent
surface. It follows the shared contract in the [bh plugins router](../SKILL.md).

## Purpose and choice of execution surface

Normal Task/Agent fanout is the default for ordinary, fire-and-forget subagent work. Choose
Herdr only when an operator explicitly needs a separately running, persistent agent that can
be inspected, steered, or attached to in a real terminal pane. Herdr complements Task/Agent;
it does not intercept Task calls, automatically route ready beads, or advance bead state.

`bh` remains the durable authority for beads, branches, and managed worktrees. Herdr is the
live terminal/process controller. In particular, use `bh work` to claim, resume, submit, and
clean up a bead; do not use Herdr worktree commands for a managed bead.

## Prerequisites and safe probes

The installed CLIs are the syntax authority. Do not pin this workflow to a Herdr version or
installation path; establish what is available first:

```bash
herdr --version
herdr --help
bh plugin herdr --help
bh plugin herdr status
```

`status` reports both server health and the installed agent integrations. A missing `herdr`
binary, stopped server, or unavailable integration is a stop-and-fix condition before spawning
or dispatching. To inspect supported harness kinds in the installed Herdr, use:

```bash
herdr agent start --help
```

Install exactly the harness being used; installation is explicit and per kind:

```bash
bh plugin herdr integrate claude
# or
bh plugin herdr integrate codex
```

Then run `bh plugin herdr status` again and confirm that integration is present. Do not
auto-install every supported harness, and do not assume an integration exists because its
executable is installed.

### The `bh-supervisor` session

Every Beadhive Herdr operation is scoped to the dedicated `bh-supervisor` session. It never
uses, enumerates, focuses, renames, or closes the operator's `default` session.

Start or attach the supervisor session interactively when a human needs to see it:

```bash
herdr --session bh-supervisor
# equivalently, when it already exists:
herdr session attach bh-supervisor
```

Leave the client with Herdr's normal UI exit/detach action; that detaches the human client
while leaving the persistent server, session, and panes running. Do **not** use
`herdr session stop bh-supervisor` merely to detach: stopping a session is a destructive
teardown operation. Confirm the state with `herdr status` or `bh plugin herdr status` before
returning to the automated workflow.

`HERDR_ENV=1` has an important but narrow meaning. Herdr's native agent skill treats it as a
convention that an agent is running inside a Herdr-managed pane and should control that current
session. It is **not** socket-level authorization: a supervisor process outside a Herdr pane
can technically reach the server. Beadhive deliberately contains that power by using the named
`bh-supervisor` session and non-focusing pane creation, never by treating `HERDR_ENV` as an
access-control boundary.

For native, in-pane pane/agent control, load the installed native instructions with
`herdr --skill` and follow them. This reference describes the `bh plugin herdr` wrapper; it is
not a substitute for Herdr's own current command manual.

## Ownership and identity boundaries

- **`bh` owns lifecycle.** A bead must already be claimed and its managed `bh` worktree must
  already exist. `spawn` only resolves that worktree as the pane's current directory. It never
  claims a bead, creates a worktree, or creates another checkout.
- **Herdr owns live panes and lifecycle signals.** Its states (`idle`, `working`, `blocked`,
  and so on) are operational evidence, not bead-state transitions.
- **Names make ownership visible.** A successful spawn reserves the deterministic target
  `bh-<bead-id>` (for example, bead `bh-cp-czm.2` becomes
  `bh-bh-cp-czm.2`), and gives the pane the same visible name. `ps` derives the hive/bead view
  from those live names; manually created or unrecognized agents remain `unmanaged`.

The naming rule is for recognition, not prediction. Always copy the `target=` value printed by
`spawn` and use that exact emitted target for later commands. Do not make an agent guess a
target from the bead ID or from sidebar order.

## Live test / demo loop

This is a **stateful, live operation**, not an automated documentation test. It creates a real
external pane and runs a real agent. Do not run it merely to validate this file, particularly
when the server is stopped. Documentation checks should validate links and Markdown shape
without launching Herdr.

First claim the bead through normal Beadhive lifecycle tooling so its managed worktree exists.
From a second shell, run the loop below. Replace the placeholders, and copy the actual target
printed by `spawn` rather than substituting an inferred value.

```bash
# Start or attach Herdr; leave its server and session running.
herdr --session bh-supervisor

# In another shell, install the integration for the harness under test.
bh plugin herdr integrate codex
# or: bh plugin herdr integrate claude
bh plugin herdr status

# The bead is already claimed and has an existing bh-managed worktree.
bh plugin herdr spawn --hive bh --bead <claimed-bead-id> --kind codex

# Copy the target printed by spawn, then use it exactly as emitted.
bh plugin herdr ps
bh plugin herdr dispatch <target> "Reply with exactly HERDR_TEST_OK."
bh plugin herdr watch <target> --timeout 120

# This prints a human command; it does not attach this shell itself.
bh plugin herdr attach <target>

# When the live pane is no longer needed, close only that proven bh-owned pane.
bh plugin herdr reap <target>
```

Expected observations, in order:

1. `status` shows a live server and the selected harness integration.
2. `spawn` creates or reuses the isolated `bh:<hive>` workspace, splits a non-focused pane,
   starts the deterministic `bh-<bead-id>` agent, runs a warm-up, and prints its `target`, pane
   ID, workspace, and bead. The warm-up sends a harmless prompt and verifies its visible output;
   it exists because first-run Claude/Codex UI can consume an otherwise successful-looking first
   prompt. If warm-up or setup fails, the newly created pane is best-effort closed.
3. `ps` lists live agents with their visible hive, bead, and state. Its output is the safe
   dashboard for confirming the emitted target is still present.
4. `dispatch` proves delivery, rather than trusting a settled lifecycle state: it reads visible
   pane content before and after the prompt, and succeeds only when a new occurrence of the
   exact prompt is visible. It has a fixed 60-second wait. A failure means the prompt may have
   been intercepted by onboarding or another UI; inspect/attach before trying again.
5. `watch` waits for Herdr's `blocked` state (or reports a bounded timeout). A blocked agent is
   asking for intervention; inspect it rather than blindly sending input.
6. `attach` only prints `herdr --session bh-supervisor agent attach <target>` for a human to
   copy and run. `bh` never takes over the caller's TTY.
7. `reap` closes the agent's pane, not its workspace or worktree. It acts only when live records
   uniquely prove the target is a currently live, bh-owned pane with a matching visible name.

## Compact command guide

| Command | Prerequisites and inputs | Result and safety boundary |
|---|---|---|
| `status` | None; safe probe. | Reports server health and installed integrations. A down server does not create one. |
| `integrate KIND` | `herdr` on `PATH`; `KIND` must appear in installed `herdr agent start --help`. | Explicitly installs lifecycle hooks for one harness (such as `claude` or `codex`). Recheck `status`; unsupported kinds fail with the discovered list. |
| `spawn --hive H --bead B --kind K` | Live server, installed harness integration, and an **already-claimed** bead with an existing managed `bh` worktree. | Creates/reuses `bh:H`, splits a non-focused pane, starts/names the target, and warms it up. Never claims or provisions a worktree. Fails clearly if the worktree is absent. |
| `ps` | Live server. | Lists live agent names plus parsed hive/bead identity and state. Unrecognized identities are explicitly unmanaged. |
| `dispatch TARGET PROMPT` | Live server and a live target. | Reads pane content before/after prompting and verifies a new real turn; its prompt wait is fixed at 60 seconds. A lifecycle `done` alone is not delivery proof. |
| `watch TARGET [--timeout SECONDS]` | `herdr` on `PATH`, live server, and a target. | Delegates to Herdr waiting until `blocked`; an optional timeout is bounded and converted to Herdr's native unit. |
| `attach TARGET` | A target string. | Prints, but never executes, the session-scoped command for a human attach. It does not inspect or alter Herdr state. |
| `reap TARGET` | Live server and one uniquely proven live bh-owned target. | Closes exactly the matching pane without focus. It refuses ambiguous, stale, terminal, renamed, or unmanaged records and never removes a workspace/worktree. |

## Diagnostics and safe teardown

Start diagnostics with `bh plugin herdr status`, then `bh plugin herdr ps`. If the server is
down, start/attach the named supervisor session and repeat the status probe. If integration is
missing, install only the selected harness. If `spawn` says the worktree is absent, return to
`bh work` and claim/resume the bead—do not create a checkout through Herdr.

If dispatch cannot prove a new prompt appeared, or `watch` reports `blocked`, print the attach
command and let a human inspect the live pane. Native in-pane investigation belongs to
`herdr --skill`; do not infer success from `done` or send approval answers blindly.

Safe cleanup is intentionally narrow: after the pane is no longer needed, run `reap` using the
target that `spawn` emitted. It only closes a uniquely verified bh-owned pane. It does not
remove the shared hive workspace, detach/delete the Herdr session, remove the managed
worktree, change a bead, or submit work. Continue normal Beadhive lifecycle cleanup through
`bh work`.

For upstream setup, configuration, and exhaustive native controls, use
[Herdr's agent guide](https://herdr.dev/agent-guide.md) and the installed `herdr --help` /
`herdr --skill` output.
