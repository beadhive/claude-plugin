# Go factoring guidance

Use these as bundled defaults only. Explicit task instructions, repository architecture and
steering, and `~/.beadhive/conventions/go/*.md` take precedence.

## Boundaries and dependencies

- Give packages cohesive responsibilities and names that describe the capability they provide,
  not generic layers such as `util`, `common`, or `helpers`.
- Define narrow interfaces at the consuming package when substitution is required. Accept
  behavior, return concrete values, and avoid provider-owned umbrella interfaces.
- Use `internal/` to enforce implementation privacy when the repository boundary warrants it.
  Avoid creating packages solely to reduce file size or mirror every type.
- Keep construction and concrete wiring at the composition boundary. Pass dependencies explicitly
  and avoid mutable package globals.
- Prevent import cycles by moving policy toward the owning domain or extracting a genuinely stable
  contract, not by duplicating types between packages.

## State and errors

- Make goroutine, channel, and resource ownership explicit. Propagate `context.Context` from the
  caller and define shutdown behavior at the boundary that starts work.
- Wrap errors with useful context while preserving identity for `errors.Is` and `errors.As`.
  Translate implementation errors only where the consumer contract needs stability.
- Keep zero-value behavior and concurrency guarantees part of the public contract when callers
  rely on them.

## Test seams

- Use small hand-written fakes for consumer-owned interfaces unless generation is repository
  policy. Assert behavior rather than incidental call sequences.
- Put adapter contract and integration tests with the package that owns the adapter. Reuse a
  contract test across implementations when interchangeability is promised.
- Choose `package x` tests for internal behavior and `package x_test` tests for the public surface
  deliberately; prefer the external form when architectural isolation is the claim.
- Keep `testdata/` and fixture builders with their owning package so higher layers can test through
  the interface without importing implementation fixtures.
