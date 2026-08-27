# Repowise and static-analysis integration reference

Use this reference for Beadhive's Repowise integration and the boundary between its local-index
lifecycle and native static analysis. It follows the shared contract in the
[bh plugins router](../SKILL.md). For candidate selection and bead-filing heuristics, read the
[refactor static-analysis guide](../../refactor/references/static-analysis.md).

## Purpose and prerequisites

Repowise can index repository structure and expose dependency, history, health, risk, coverage,
and test-impact evidence. Beadhive supplies an optional, small lifecycle surface for the current
hive's local index. Native Repowise owns the richer analysis surface.

Start with installed help because both surfaces can change:

```bash
bh plugin --help
bh plugin repowise --help
bh plugin repowise status
command -v repowise
repowise --help
```

Proceed only when the integration is enabled for the intended hive, the native executable is
available, and status reports an index suitable for the question. Record stale or missing index
state as a limitation. Coverage and impacted-test evidence additionally require current coverage
data; an indexed repository alone does not make that evidence current.

## Ownership boundary

| Layer | Owns | Does not own |
| --- | --- | --- |
| `bh plugin repowise` | Provisioning and status of the hive's local Repowise index, as exposed by installed help. | Native analysis, architecture decisions, source edits, or bead lifecycle. |
| Native `repowise` | Analysis commands, index contents, coverage ingestion, health/risk calculations, and native diagnostics. | Permission to edit/delete code or authority to choose a north-star architecture. |
| Refactor/planner workflow | Corroborating findings, defining boundaries and outcomes, filing gated beads, and human decisions. | Treating a score as truth or bypassing review and validation. |

The installed Beadhive wrapper currently separates index/status operations from analysis. Never
translate a native analysis command into `bh plugin repowise <analysis>` unless the installed
wrapper help explicitly exposes it.

## Probe-first workflow

1. Run `bh plugin repowise status` from the repository or managed worktree being analyzed. Keep
   its freshness result with the evidence.
2. If an index must be provisioned or refreshed, inspect `bh plugin repowise index --help` first.
   Indexing mutates local tool state and may consume meaningful time and storage, so perform it
   only within the operator's stated intent.
3. Run `repowise --help`, choose only an available analysis family, then run
   `repowise <selected-command> --help` immediately before using it. Relevant installed versions
   may expose context/why, health, risk, dead-code, coverage, and impacted-test families; their
   arguments and output schemas remain version-sensitive.
4. Prefer deterministic local evidence. Check help and disclose cost/network behavior before a
   model-backed query or generated-code action.
5. Capture the revision, working directory, exact invocation, freshness, and relevant output.
   Correlate independent signals and inspect the named code, tests, history, and architecture
   records before recommending a bead.

The [refactor static-analysis guide](../../refactor/references/static-analysis.md) maps these
signals to candidate questions and supplies the proposed-bead evidence template. A finding is a
lead, not an automatic refactor request.

## Diagnostics

Use the smallest read-only probe that distinguishes the failure:

```bash
bh plugin repowise status
bh plugin repowise --help
repowise status --help
repowise doctor --help
```

- **Wrapper command absent:** the installed `bh` version does not provide this integration; use
  native tools or repository evidence without blocking the refactor workflow.
- **Disabled or unavailable:** inspect the hive's normal configuration/readiness surfaces and the
  native executable; do not guess a configuration key from this reference.
- **Missing or stale index:** inspect the installed index help and decide explicitly whether its
  time/storage cost is warranted before provisioning.
- **Missing/stale coverage:** use native coverage help to inspect or ingest the repository's
  actual report; never present impacted tests as complete when coverage provenance is unknown.
- **Unsupported language or incomplete graph:** record the blind spot and corroborate with
  repository-native search, build, test, and dependency tools.
- **Analysis-command failure:** retain the command/output, re-check its native help and repository
  target, then use native diagnostics. Do not repair native state by deleting caches blindly.

## Cleanup and safety

Status and ordinary analysis are evidence gathering, not authorization for a refactor, deletion,
or generated-code application. In particular, a dead-code result does not prove runtime or public
unreachability, and an impacted-test list does not waive the repository's full configured gate.

Do not run native delete/uninstall operations, remove `.repowise` state, ingest coverage, refresh
an index, invoke a paid/networked model, or apply generated code without the corresponding user or
workflow authority. Use installed native help for intentional cleanup and confirm the exact
repository/index target first.

## Current limitations and deeper guidance

- Indexes and coverage are snapshots and may lag the source revision under review.
- Dynamic loading, reflection, generated code, cross-repository consumers, and unsupported
  languages can make dependency, reachability, and impacted-test results incomplete.
- Command families and output schemas vary by installed version; this reference intentionally
  does not copy their full flag inventory.
- Static analysis can identify promising seams and blast-radius evidence, but humans still own
  responsibility boundaries, compatibility decisions, and whether expected test-closure savings
  justify the migration.

Use `repowise --help` and the selected command's help for exhaustive syntax. Return to the
[plugin router](../SKILL.md) for other integrations and to the
[refactor guide](../../refactor/SKILL.md) for proposal or execution lifecycle.
