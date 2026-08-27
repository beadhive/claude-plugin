# Static-analysis evidence for refactoring

Use this reference when an enabled static-analysis-category plugin can add evidence to a refactor
or modularization request. Repowise is the concrete integration described here; for its index
lifecycle, readiness, and ownership boundary, also read the
[Repowise plugin reference](../../plugins/references/repowise.md).

Static analysis is an optional evidence source. Its absence must not block proposal or execution,
and its output neither authorizes edits or deletion nor replaces human architectural judgment.
Continue with repository documentation, code and history inspection, runtime observations, and
native test tooling when no category plugin is ready.

## Probe before analysis

Do not assume that a command, flag, or output field exists in the installed version. Probe the
Beadhive wrapper and native tool separately:

```bash
bh plugin --help
bh plugin repowise --help
bh plugin repowise status
repowise --help
repowise <selected-command> --help
```

`bh plugin repowise` owns the Beadhive-side index lifecycle and status surface. Run analysis with
the native Repowise commands exposed by `repowise --help`; do not invent analysis subcommands under
`bh plugin repowise`. Record the repository revision, working directory, exact command, relevant
output or durable reference, and index/coverage freshness so another planner or developer can
reproduce each finding. Ask before an operation would refresh an index, ingest data, use a paid or
networked model, or otherwise mutate tool state.

## Turn signals into architectural questions

Select only the command families present in installed help. Use each signal to ask a question,
not to declare a solution:

| Evidence | Candidate question | Useful corroboration |
| --- | --- | --- |
| Dependency cycles | Which responsibilities or dependency directions form the cycle, and is there a stable port or seam that could break it? | Callers/callees, runtime wiring, ownership, decisions, and tests crossing the proposed seam. |
| Risk or centrality | Is the highly connected or historically risky area a sequencing hotspot, a missing contract, or merely legitimate coordination code? | Change history, incident evidence, fan-in/fan-out, public contracts, and impacted tests. |
| Dead-code findings | Is the element truly unreachable, or is it loaded dynamically, externally consumed, generated, or retained for compatibility? | Runtime/config searches, public API inventory, history, and focused characterization tests. |
| Coverage evidence | Which preserved behaviors lack characterization, and which boundary currently forces an unnecessarily broad test closure? | Test ownership, fixture coupling, runtime demos, and coverage freshness. |
| Context and `why` evidence | Which responsibility, decision, or dependency rationale must the north-star preserve or deliberately supersede? | Architecture records, code owners, git archaeology, and current consumers. |
| Health scores or trends | Is complexity concentrated at a real responsibility boundary, and is it worsening enough to justify intervention? | Symbol-level metrics, churn, defects, ownership, and an observable before/after measure. |
| Impacted-test evidence | What is the current blast radius, which tests protect the movement, and should an isolated module reduce that closure? | Coverage provenance, test selection logs, dependency edges, and a conservative full gate. |

For cycles or centrality, use the dependency/relationship evidence the installed version actually
exposes. If it has no dedicated command for a signal, use supported context, risk, health, or
question surfaces plus repository-native graph tooling; state the limitation instead of inferring
a measurement. Prefer deterministic, local commands before a model-backed query, and disclose
when a result came from synthesis rather than a direct metric.

## Decide whether a finding deserves a bead

Do not file a cleanup bead for an isolated score, ranking, or aesthetic preference. Propose work
only when all of these are available:

1. corroborating evidence: at least two independent signals, or one structural finding supported
   by runtime, history, test, incident, or ownership evidence;
2. an articulable affected boundary and north-star dependency or responsibility model;
3. a measured outcome, such as smaller expected test closure, a broken dependency cycle, reduced
   risk/complexity at a named seam, or removal proven safe by consumer evidence;
4. documented risk, criticality, uncertainty, and sequencing constraints; and
5. observable acceptance criteria that compare the result with a captured baseline.

Prefer a spike when the boundary is speculative, dynamic behavior prevents reachability proof,
coverage or index data is stale, or alternative architectures cannot yet be distinguished. Group
related findings by one architectural outcome; do not turn every reported file or symbol into a
separate bead. Route a complete proposal through `bh:refactor` proposal mode and the human-gated
planner flow. Analysis never bypasses planning or starts implementation automatically.

## Proposed refactor bead evidence

Populate every field and mark unknowns explicitly:

```text
Refactoring statement:
Problem and corroborating evidence:
Reproduction: <revision, cwd, tool/index freshness, exact commands, relevant outputs>
Affected boundary and current dependency direction:
North-star responsibilities, contracts, and dependency direction:
Expected test closure and measured benefit:
Baseline functionality, tests, metrics, and known failures:
Validation profile: <economical|balanced|strict; risk-derived or operator override>
Risk and criticality:
Sequencing and compatibility constraints:
Observable acceptance criteria:
Explicit non-goals:
Open uncertainties or spike questions:
```

During execution, re-run only the relevant supported analyses at the checkpoints justified by the
validation profile, compare results with the baseline, and still run the repository's full
configured gate. A narrower impacted-test result guides intermediate validation; it does not by
itself prove that the full suite is unnecessary or that a proposed module boundary is sound.
