# TypeScript and JavaScript factoring guidance

Use these as bundled defaults only. Explicit task instructions, repository architecture and
steering, and `~/.beadhive/conventions/typescript-javascript/*.md` take precedence.

## Boundaries and dependencies

- Make package entry points and `exports` describe the supported surface. Do not let higher layers
  depend on deep internal paths that bypass the boundary.
- Point dependencies toward domain policy. Put transport, persistence, platform, and framework
  code behind small injected ports when replacement or isolated testing has concrete value.
- Remember that TypeScript interfaces disappear at runtime. Pair a type-level port with an
  explicit construction boundary or runtime validation when untyped input crosses the seam.
- Keep ESM/CommonJS interop, environment reads, and singleton creation at composition roots rather
  than hiding them in otherwise reusable modules.
- Avoid barrel exports that create cycles or expose internals merely for convenience.

## State and errors

- Give mutable state, timers, subscriptions, and asynchronous cleanup an explicit owner and
  lifecycle. Do not make import order part of the contract.
- Define whether a port throws, returns a result value, or rejects a promise. Translate external
  error shapes at the adapter boundary and preserve useful causes.
- Keep command side effects separate from queries when that separation clarifies contracts; do
  not introduce duplicate models or CQRS machinery without evidence that it reduces coupling.

## Test seams

- Test consumers against typed fakes at the imported port boundary. Avoid mocks coupled to private
  call order or module-loader tricks.
- Give each adapter contract tests for its observable port behavior and focused integration tests
  for the external system it owns.
- Keep fixtures and test builders with the package that owns their vocabulary. Higher layers
  should not need an adapter's internal fixtures.
- Exercise package entry points in tests so accidental deep imports and runtime export mismatches
  are visible.
