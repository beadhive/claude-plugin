# Refactor request schema

Use this schema in proposal mode to turn a raw refactoring statement into planning input. Mark
unknowns explicitly; do not invent evidence or architecture decisions. The planner may split the
request into a gated molecule or propose a spike when feasibility is unsettled.

## Required fields

1. **Problem statement and evidence** — what structural problem exists, where it appears, and the
   observations, measurements, incidents, or static-analysis findings that support the claim.
2. **North-star intent** — the desired responsibilities, dependency direction, contracts, and
   end-state qualities without prematurely prescribing every file move.
3. **Affected boundary** — the packages, modules, interfaces, data flows, public APIs, or runtime
   paths in scope, plus explicit non-goals.
4. **Expected test closure** — the functional observations and tests expected to prove preserved
   behavior, including relevant consumers and known gaps.
5. **Risk and criticality** — likely failure impact and risk factors such as security, data
   integrity, concurrency, migrations, public contracts, or broad dependency fan-out.
6. **Validation profile** — economical, balanced, or strict; state whether it is risk-derived or
   an operator override and preserve all mandatory repository gates.
7. **Observable acceptance criteria** — externally checkable evidence that the boundary improved
   while intended behavior remained stable.

## Planning handoff template

```text
Refactoring statement:
Problem/evidence:
North-star intent:
Affected boundary and non-goals:
Expected test closure and known gaps:
Risk/criticality:
Validation profile and override rationale:
Observable acceptance criteria:
Open feasibility or product decisions:
```

Present the completed proposal to the human as part of `bh:plan`'s staged checkpoints. Planning
owns architecture decisions, decomposition, filing, verification, and kickoff approval. Do not
use this template as a shortcut around those gates or as authorization to begin implementation.
