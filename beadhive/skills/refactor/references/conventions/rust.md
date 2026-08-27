# Rust factoring guidance

Use these as bundled defaults only. Explicit task instructions, repository architecture and
steering, and `~/.beadhive/conventions/rust/*.md` take precedence.

## Boundaries and dependencies

- Use modules and crates to express cohesive ownership and dependency direction. Split a crate
  when the boundary has an independently useful contract or build/test closure, not just size.
- Keep visibility narrow with private items and `pub(crate)`; deliberately re-export the stable
  public surface rather than exposing implementation modules.
- Define focused traits at the consuming boundary when multiple implementations, test doubles, or
  inversion provide value. Prefer generics for static composition and trait objects for intentional
  runtime substitution.
- Keep infrastructure adapters and feature-specific wiring outside domain policy. Avoid feature
  flags that produce many untested combinations or change core semantics invisibly.
- Use newtypes or boundary-owned data types when raw representation would leak infrastructure
  concerns into the domain.

## State and errors

- Make ownership, borrowing, thread-safety, and task lifetime part of the boundary design. Avoid
  expanding `Arc<Mutex<_>>` through layers as a substitute for choosing a state owner.
- Expose stable domain error enums where callers need to branch. Add context at adapter boundaries
  without leaking concrete dependency errors into the public contract.
- Define cancellation and cleanup for spawned async work; the module that starts a task should make
  its shutdown and join behavior testable.

## Test seams

- Test domain behavior with small trait implementations or in-memory adapters that avoid external
  infrastructure.
- Keep unit tests beside private implementation and integration or contract tests under the crate's
  public surface. Run shared contract cases for substitutable implementations.
- Keep fixtures and builders in the crate or module that owns their vocabulary. Higher layers
  should construct inputs through the public API rather than importing test-only internals.
- Validate supported feature combinations at the owning crate boundary, especially when optional
  adapters affect compilation or public exports.
