# Flat-repository refactor scenario

This worked example is modeled on a mature Python application whose prototype grew into many
top-level source and test files. It demonstrates the contract; it does not authorize or perform a
refactor in `beadhive/beadhive` or any other repository. Names, revisions, counts, and command
results below are illustrative evidence that a real run must replace with observed values.

## Start with the statement and conventions

The operator says: “Separate plan-file validation from CLI and MCP orchestration so validation
can evolve and be tested without booting either transport.” There is no claimed implementation
bead, so `bh:refactor` selects proposal mode and then routes the result through `bh:plan`.

Inspection identifies Python in scope. Load applicable rules in precedence order:

1. preserve the operator's stated CLI/MCP behavior;
2. apply repository steering and `docs/design/` decisions;
3. load direct Markdown children such as
   `~/.beadhive/conventions/python/10-boundaries.md` and
   `~/.beadhive/conventions/python/20-tests.md` in bytewise basename order; and
4. compose the bundled [Python conventions](conventions/python.md) beneath them.

Suppose the repository requires domain errors at transport boundaries while the host files require
`Protocol` ports and module-owned fixtures. The repository's error rule wins any direct conflict;
the non-conflicting host rules still apply.

If Repowise is enabled and ready, supported native commands may add reproducible evidence: for
example a dependency cycle between plan validation and CLI formatting, broad impacted-test output,
and high centrality for a validation helper. Record the revision, exact commands, index freshness,
and relevant outputs. Corroborate those findings with imports, callers, history, and tests. If
Repowise is absent or stale, proceed with those repository-native sources and mark the tool gap;
neither path changes the requested behavior boundary.

## Produce the proposal

Populate the shared [refactor request schema](request-schema.md) completely:

```text
Refactoring statement:
Separate plan-file validation from CLI and MCP orchestration without changing accepted input,
diagnostics, exit status, or serialized results.

Problem/evidence:
Validation rules, transport formatting, and orchestration share top-level modules and fixtures.
CLI-only setup is required by validation tests. Import inspection and two recent change sets show
the same rule edited through both transports. Optional fresh Repowise evidence reports the named
cycle and a broad impacted-test set; exact reproduction data is attached.

North-star intent:
A ValidationPort owns behavior-oriented validation operations. A PythonValidationService is the
concrete implementation. CLI and MCP adapters depend inward on the port; the composition root may
construct the implementation; validation internals never import either transport.

Affected boundary and non-goals:
In scope are plan validation, its result/error contract, CLI and MCP callers, and their tests and
fixtures. Out of scope are new validation rules, output redesign, CLI renaming, persistence changes,
plugin APIs, and repository extraction.

Expected test closure and known gaps:
Characterization covers valid/invalid plans and equivalent CLI/MCP results. Module-local tests
cover rule behavior and adapter contract tests cover the real implementation. Higher-layer tests
use a port substitute. The final repository gate remains mandatory. Dynamic plugin consumers are
not proven and require a focused search before caller migration.

Risk/criticality:
Moderate-to-high: validation gates molecule filing, diagnostics are user-visible, and two transports
consume the result. Data migration, concurrency, and security boundaries are not in scope.

Validation profile and override rationale:
Balanced by risk: targeted checks at each known-good transition and broader transport checks after
each caller migration. The operator may override toward strict; no override may remove the final
configured gate.

Observable acceptance criteria:
The same characterization inputs produce equivalent results and diagnostics; CLI and MCP depend
only on ValidationPort; dependency checks find no import back to transports; module tests run with
module-owned fixtures; higher-layer tests substitute the port; the real adapter passes its contract;
and final configured validation matches or improves the baseline with no unexpected failure.

Open feasibility or product decisions:
Confirm dynamic plugin consumers before deleting compatibility imports. A separate read model or
CQRS split is not justified by current evidence.
```

Present this proposal at the normal planner checkpoints. It is planning input, not a filed bead or
permission to edit.

## Execute only after claim

Assume a later implementation bead contains that accepted boundary and has been briefed and claimed
through `bh:work`. The developer records this non-trivial example baseline before editing:

| Evidence | Baseline result |
| --- | --- |
| Starting tree | clean at illustrative revision `abc123`; Python 3.12; test extras installed |
| CLI observation | sample valid and invalid plans retain captured diagnostics and exit statuses |
| Focused behavior | `uv run pytest tests/test_plan_validation.py -q`: 84 passed, exit 0 |
| Transport behavior | `uv run pytest tests/test_plan_cli.py tests/test_plan_mcp.py -q`: 63 passed, exit 0 |
| Optional environment suite | `uv run pytest -m postgres -q`: expected failure `test_remote_round_trip`, exit 1, fingerprint “connection refused” |
| Configured gate | `just check`: exit 0 |

The PostgreSQL failure is expected only for that non-gating environment suite. A changed identity,
count, or fingerprint is unexpected until explained; it cannot be hidden inside “baseline already
failed.” Repository submission policy still governs whether any failing configured gate is allowed.

Write the north-star before file movement: `ValidationPort` is the consumer contract,
`PythonValidationService` owns the rules, CLI and MCP are outside adapters, and only the composition
root knows the concrete implementation. Preserve accepted inputs, result ordering, diagnostics, and
exit statuses. Do not add rules, change serialization, introduce CQRS, or publish a package.

Use small transitions and squashable local checkpoints:

1. Add characterization for the preserved result/error contract; checkpoint with a conventional
   test commit after focused behavior and transport checks match baseline.
2. Introduce the port and concrete implementation behind a compatibility adapter; checkpoint after
   focused behavior and a dependency-direction check pass.
3. Migrate the CLI caller without cleanup; checkpoint after CLI and focused behavior checks pass.
4. Migrate the MCP caller, then remove the authorized compatibility adapter; checkpoint after both
   transport suites and the broader affected closure pass.
5. Run the modularization isolation transition below; use `fixup!` commits for corrections and
   `bh work refine --autosquash` before handoff.

Balanced cadence is the risk-derived default. In this example the operator overrides transitions
3–5 to strict: focused checks run after each commit, both transport suites and the dependency check
run at every boundary transition, and the configured gate runs after the high-risk compatibility
removal. Record the override; do not silently weaken repository policy.

At every checkpoint, compare named checks with the baseline. The two focused suites remain green;
the optional PostgreSQL test remains the same single failure with a materially equivalent
fingerprint; no check gains a new failure or skip. A changed expected failure or new failure stops
movement until it is explained and fixed forward or recovered through repository-approved,
non-destructive means. End with the full `just check`, compare its exit and summary with baseline,
then use `bh work show`, refine, `bh work check`, and `bh work submit`.

## Continue through modularization

The request becomes completed modularization only after `bh:modularize` phase N establishes all of
these properties:

- module-local tests construct `PythonValidationService` using module-owned plan factories and
  injected filesystem/clock substitutes; they do not import or boot CLI or MCP layers;
- higher-layer CLI and MCP tests inject a `ValidationPort` fake and assert transport mapping rather
  than importing concrete validation rules or fixtures;
- focused contract tests run the real implementation against the behaviors promised by the port;
- a repository-native dependency check rejects imports from validation internals back to CLI/MCP
  and rejects higher-layer imports of private validation modules; and
- the module's declared dependencies are enumerable, its public API is bounded, and one documented
  repository-native command can build or load it and run its internal tests without assembling the
  higher application.

If any property is missing, report an incremental refactor rather than claiming modularization.
Physical extraction may still require build, release, ownership, and infrastructure decisions.

## Keep current and future scope explicit

This skill family currently provides proposal and execution protocols, convention resolution,
optional static-analysis evidence guidance, validation cadence, checkpoint discipline, and module
isolation criteria. It can record current and expected test closures as architectural evidence.

It does **not** currently implement hierarchical or memoized test-closure selection, internally
versioned artifacts, external packaging, SemVer, publishing, or repository extraction. Those are
possible follow-on capabilities once module boundaries are evidenced; do not claim cache hits,
selectively skip the repository gate, assign an internal version, or describe an in-tree module as
independently shipped until separate tooling and policy exist.
