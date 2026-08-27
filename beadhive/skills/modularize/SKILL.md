---
name: modularize
description: >-
  Turn an orthogonal area of an existing codebase into an explicit, independently testable
  internal module as a strict extension of bh:refactor. Use when asked to modularize a flat or
  tightly coupled repository, extract functionality behind a port or interface, isolate module
  tests and fixtures, reduce a change's test closure, or prepare a subsystem for possible future
  extraction without requiring a separate repository.
---

# Modularize

First load and follow [`bh:refactor`](../refactor/SKILL.md). Inherit its mode choice, safety
boundary, five shared phases, validation cadence, checkpoint discipline, and final handoff; do
not replace or restate them. Add only the boundary-selection pre-phase and post-migration
isolation phase below.

Read the base skill's
[flat-repository scenario](../refactor/references/flat-repository-scenario.md) when a concrete
example would help apply the pre-phase, shared execution protocol, and isolation phase together.

Modularization is stricter than moving files. It creates an enforceable contract: higher layers
depend on a named port, concrete behavior lives behind that port, and module internals never
depend back on their consumers.

## Phase 0: select a real module boundary

When a static-analysis-category plugin is enabled, read the base refactor skill's
[static-analysis guide](../refactor/references/static-analysis.md) before scoring candidates.
Use dependency, risk, coverage, context, health, and test-impact findings as candidate evidence,
not automatic boundary choices or authorization to edit. If no category plugin is ready, continue
with repository documentation, code and history inspection, runtime observations, and native
dependency and test tools; its absence must not block modularization.

Before entering the base refactor protocol, inventory candidate areas that own cohesive behavior
and could be invoked through a narrow contract. For each candidate, record evidence and score
every dimension from 0 (poor), through 1 (mixed), to 2 (strong):

| Dimension | A strong candidate scores 2 when |
| --- | --- |
| Cohesion | Its behavior serves one named capability with clear invariants. |
| Coupling | Few dependencies cross the proposed boundary, and they can cross through ports. |
| Data and side-effect ownership | The module can own or explicitly mediate its state, I/O, and external effects. |
| Port narrowness | Consumers need a small behavior-oriented contract rather than internal types or storage details. |
| Replaceable implementations | At least one concrete implementation is clear and another implementation, fake, or substitute is plausible. |
| Dependency direction | Internals can depend on inward abstractions while higher layers depend only on the public port. |
| Test-closure reduction | Most module changes could be validated internally plus at boundary tests, without exercising unrelated higher layers. |

Compare totals, but do not select by total alone. A candidate must have an enforceable port and a
one-way dependency rule; a zero for either port narrowness or dependency direction is a hard
stop. Prefer the smallest boundary that owns a complete capability and its side effects. Record
the chosen capability, score, evidence, rejected alternatives, named port, concrete
implementation, allowed dependency direction, state/side-effect ownership, current test
closure, and expected test closure.

Reject directory-only reshuffling. New folders, package names, facades that merely re-export
internals, or broad service-locator contracts do not constitute modularization when consumers
can still import internals or dependencies still point both ways. Route an unresolved boundary
or product responsibility decision back through planning.

In proposal mode, carry the assessment into the refactor request's problem evidence, north-star,
affected boundary, expected test closure, and observable acceptance criteria. In execution mode,
use it as the input to the base protocol's baseline and north-star work. If it conflicts with the
claimed bead, stop and replan rather than silently changing scope.

## Architectural lens

Use [Hexagonal Architecture](https://en.wikipedia.org/wiki/Hexagonal_architecture_(software))
as the default lens: domain behavior sits behind inward-facing ports, while replaceable adapters
connect storage, transports, frameworks, and other external concerns. Apply the useful boundary
and dependency-direction ideas without imposing ceremony or requiring every module to become a
service.

Consider [CQRS](https://en.wikipedia.org/wiki/Command_Query_Responsibility_Segregation) only when
command and query workloads genuinely need independently evolvable contracts or models, such as
at a high-scale or service boundary with materially different consistency, scaling, security, or
data-shape needs. Do not introduce CQRS for ordinary CRUD, a small in-process module, or a codebase
where duplicated models and synchronization would cost more than the separation provides.

## Run the shared refactor protocol

Execute the five phases from `bh:refactor` as written. Treat creation of the port, adaptation of
the concrete implementation, and migration of callers as small movement transitions with their
own baseline comparisons and known-good checkpoints. Keep compatibility adapters temporary and
remove them only when the bead authorizes it and evidence shows all consumers use the boundary.

After the last code-migration transition, run the isolation phase below before the base
protocol's final self-refine, full configured validation gate, and submit. The isolation work is
a required final transition and must use the selected validation cadence.

## Phase N: isolate tests and fixtures

Move module-internal tests and fixtures behind the boundary. They must exercise the concrete
implementation using only module-owned code, declared external dependencies, and injected test
adapters; they must not import, boot, or construct higher application layers.

Rewrite higher-layer tests to substitute, fake, or mock the named port. Those tests may verify
boundary wiring and consumer behavior, but must not import internal implementations, internal
fixtures, private data models, or storage details. Retain focused contract or integration tests
at the port to prove that real adapters satisfy the behavior higher layers assume.

Assess artifact independence before handoff. The result is credible when the module has an
enumerable dependency surface, no dependency cycle back to higher layers, a bounded public API,
and a repository-native way to build or load it and run its internal tests without assembling the
rest of the application. Document infrastructure that would be needed for physical extraction,
but do not require a separate repository, publication, or SemVer.

## Done gate

Do not call the work modularized until all of these are evidenced:

- a named port or interface defines the consumer-facing capability;
- at least one concrete implementation sits behind that port;
- the allowed dependency direction is explicit and enforced by code structure or tooling;
- module-internal tests and fixtures run without higher layers;
- higher-layer boundary tests substitute the port without importing module internals;
- contract or integration evidence covers the real implementation at the boundary; and
- the module presents a credible standalone build/test artifact boundary, even if it remains an
  internal, unversioned part of the repository.

Failure of this gate means the result remains an incremental refactor, not a completed
modularization. Record the gap and route additional work through planning rather than overstating
isolation.
