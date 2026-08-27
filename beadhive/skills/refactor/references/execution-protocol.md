# Evidence-led refactor execution

Use this protocol only inside a claimed implementation bead. The bead remains the authority for
scope and acceptance; `bh:developer` and `bh:work` remain the authority for worktrees, history,
validation, review, and merge.

## 1. Establish the baseline

Before editing, capture enough evidence to distinguish pre-existing behavior from regressions:

- the starting revision, relevant environment/configuration, and any dirty files already present;
- one or more functional observations or demos covering the behavior being preserved;
- the exact test, build, lint, type-check, or policy commands used, with exit status and summary;
- each expected failure by stable identity (for example test node, check name, or build target)
  plus its useful error fingerprint; and
- known flakes, quarantines, skipped coverage, or environmental limits.

Do not summarize a non-green baseline merely as “tests fail.” Preserve the failure identities and
symptoms needed for later comparison. If the baseline cannot be reproduced, resolve the
environmental uncertainty or record and escalate the limitation before moving code.

## 2. Write the north-star

Describe the intended architecture before choosing file moves. Record:

- responsibilities and the boundary that should own each one;
- allowed dependency direction and public contracts;
- observable behavior and compatibility invariants that must remain unchanged;
- the target end state and how it improves the stated problem; and
- non-goals, deferred cleanup, and any deliberately retained compatibility layer.

Keep the north-star proportional to the bead. It is a decision aid, not permission to expand the
refactor into unrelated redesign or product behavior.

## 3. Design incremental movement commits

Break the path into small, reviewable transitions. Prefer separating mechanical movement from
semantic cleanup, preserving contracts with temporary adapters when useful, and changing one
dependency direction or responsibility at a time. For every transition, state:

1. what moves or changes;
2. which invariant or behavior proves it is safe;
3. which targeted or impacted checks cover it; and
4. which known-good checkpoint follows it.

Make local conventional commits as the work becomes coherent. Use `fixup!` checkpoints for
temporary corrections and `bh work refine <id> --autosquash` before handoff when appropriate.
Checkpoint commits are squashable recovery points: they make a known-good tree and its evidence
easy to identify, but do not authorize destructive reset, loss of unrelated work, or rewriting
history anyone else may consume.

## 4. Select the validation cadence

Choose the default from code-path criticality and change risk, then record any user override.
Repository-mandated checks remain mandatory. When evidence is mixed, choose the more cautious
profile.

| Profile | Default use | During movement | Completion |
| --- | --- | --- | --- |
| Economical | Low-risk, non-critical, well-isolated code | Run targeted or impacted checks after each coherent cluster of transitions | Run the full configured validation gate |
| Balanced | Ordinary application paths or moderate boundary/coupling risk | Run targeted or impacted checks at every known-good transition; run broader checks after a boundary changes | Run the full configured validation gate |
| Strict | Critical paths; security, data integrity, concurrency, migrations, or public-contract risk | Run focused checks after each commit and the relevant broader closure at every boundary transition; repeat the full gate when a high-risk transition warrants it | Run the full configured validation gate |

The user may explicitly move anywhere on this spectrum. Record the override and its rationale;
do not silently weaken repository policy or skip the final full gate. Increase cadence immediately
when observed behavior, unexpected failures, or uncertainty exceeds the selected profile.

## 5. Compare checkpoints with the baseline

For each scheduled validation, classify the result against the recorded baseline:

- **expected and unchanged:** the same failure identity and materially equivalent fingerprint;
  it may remain only when the bead does not own repairing it;
- **expected but changed:** the identity remains but its symptom, count, or affected surface
  changes; treat it as unexpected until explained;
- **new failure:** a previously passing or absent check now fails; block progress;
- **resolved expected failure:** note the improvement and ensure it was an intended consequence,
  not lost coverage or a skipped check; and
- **inconclusive/flaky:** rerun or narrow the diagnostic until it can be classified; do not label
  uncertainty as unchanged.

When an unexpected result appears, stop advancing the movement sequence. Diagnose it against the
last known-good checkpoint, fix forward or use a repository-approved non-destructive recovery,
then rerun the checks required by the selected cadence. Never delete unrelated work to recreate a
checkpoint.

At the end, run `bh work show`, self-refine if needed, run `bh work check`, and submit through
`bh work submit`. A checkpoint never substitutes for the full gate or human review.
