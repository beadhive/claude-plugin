# Language factoring conventions

Resolve structural conventions before proposing a north-star or moving code. This mechanism is
filesystem-based; do not add or require a core `config.yaml` field.

## Precedence and composition

Apply rules from highest to lowest precedence:

1. the explicit refactoring request and operator instructions for this task;
2. repository steering and architecture documents, including the nearest applicable instructions;
3. every matching host-wide file under `~/.beadhive/conventions/<language>/*.md`; and
4. the bundled guide for a known language key.

A higher tier wins only on a direct conflict. Compose all non-conflicting rules. Within the host
tier, load files by basename in bytewise lexical order (the equivalent of `LC_ALL=C` sorting).
Files loaded later win direct conflicts between host files. Record consequential conflicts and
the winning rule in the proposal or north-star rather than silently discarding the alternative.

The host path applies to every hive operated by that user on the current host. It is not a
repository-local setting and must not be committed into the target repository.

## Resolve the language key

`<language>` is an open-set identifier, not a closed schema enum. Use a lowercase, filesystem-safe
key matching `[a-z0-9][a-z0-9.+-]*`. Reject path separators, `.` segments, and `..` segments. For a
known language, normalize its aliases to the canonical directory below. For an unknown language,
normalize an explicit name by trimming it, lowercasing it, and replacing whitespace or `_` runs
with `-`; then accept the resulting valid key without a plugin or schema change.

| Language | Canonical directory | Recognized aliases |
|---|---|---|
| Python | `python` | `py`, `python3` |
| TypeScript and JavaScript | `typescript-javascript` | `typescript`, `ts`, `javascript`, `js`, `node`, `nodejs` |
| Go | `go` | `golang` |
| Rust | `rust` | `rs` |

Treat TypeScript and JavaScript as one known convention family because their package, runtime,
and test seams commonly cross `.ts`, `.tsx`, `.js`, and `.jsx` files. An explicit operator key
may still be open-set—for example, `deno` or `javascript-browser`—but it does not also inherit the
bundled TypeScript/JavaScript guide unless repository evidence or the operator maps it there.

Infer languages from the files and build metadata in scope, not from the repository's dominant
language alone. Resolve every applicable key for a polyglot boundary.

## Discover host files

For each resolved key, inspect only direct regular-file children whose basenames end in `.md` in:

```text
~/.beadhive/conventions/<language>/*.md
```

Do not recurse into subdirectories, follow directory contents as an implicit include tree, or
load non-Markdown files. Sort matches as defined above and load all of them cumulatively. An
absent directory, an empty directory, or a directory with no direct `*.md` files contributes no
host rules and is not an error. Continue deterministically with repository rules and any bundled
guide. A valid unknown key with no directory and no bundled guide likewise contributes no
language-specific rules.

## Example: cumulative files and a repository override

Suppose the host has these files:

```text
~/.beadhive/conventions/python/10-boundaries.md
~/.beadhive/conventions/python/20-tests.md
```

`10-boundaries.md` says that callers depend on `Protocol` ports and that adapters remain private.
`20-tests.md` says each adapter owns contract tests and also says exceptions must cross the port
unchanged. Both files apply, in that order. The bundled Python guidance composes beneath them.

The repository's `docs/architecture.md` instead requires ports to translate adapter exceptions
into domain errors. That repository rule overrides the conflicting host rule and any bundled
error-boundary advice. The host rules about private adapters and contract-test ownership still
apply because they do not conflict.

## Use the bundled guides

Bundled guides are compact defaults, not universal style guides. Load only the guides for the
languages in scope:

- [Python](conventions/python.md)
- [TypeScript and JavaScript](conventions/typescript-javascript.md)
- [Go](conventions/go.md)
- [Rust](conventions/rust.md)

Explicit, repository, and host-wide rules always take precedence over these guides.
