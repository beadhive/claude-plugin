# Python factoring guidance

Use these as bundled defaults only. Explicit task instructions, repository architecture and
steering, and `~/.beadhive/conventions/python/*.md` take precedence.

## Boundaries and dependencies

- Make a package or focused module own one coherent capability; avoid catch-all utility modules.
- Point dependencies toward domain policy. Put filesystem, network, database, framework, and CLI
  behavior behind narrow ports when replacement or isolated testing has real value.
- Prefer structural `typing.Protocol` ports when consumers need a small capability. Use an ABC
  when shared runtime behavior, registration, or enforced inheritance is intentional.
- Expose the supported surface deliberately through named modules and, where useful, `__all__`.
  Keep adapter details private rather than asking callers to import through internal paths.
- Pass dependencies explicitly at construction or call boundaries. Avoid adding mutable module
  globals or import-time side effects as an extraction shortcut.

## State and errors

- Keep ownership of mutable state visible. Centralize lifecycle and cleanup with context managers
  when a boundary owns resources.
- Translate infrastructure exceptions at the owning boundary when callers should depend on a
  stable domain error. Preserve exception chaining with `raise ... from ...`.
- Keep async and sync contracts explicit; do not hide event-loop creation inside a reusable port.

## Test seams

- Test domain policy with small fakes or protocol implementations that do not import concrete
  adapters.
- Put adapter contract and integration tests with the adapter-facing package. Assert the common
  port behavior for every concrete implementation where substitution matters.
- Keep fixtures at the narrowest useful scope. Move module-owned fixtures with the module and
  avoid a root `conftest.py` becoming an implicit service locator.
- At higher layers, mock the port at the consumer boundary. Do not patch deep implementation names
  merely to avoid constructing an adapter.
