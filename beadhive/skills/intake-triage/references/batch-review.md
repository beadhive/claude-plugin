# Batch mode (`--review`) — procedure, packet shape, operator summary, dry-run

The skill drives the analyst and verifier passes; `bh` is deterministic and makes no model calls.
`bh work triage` provides packets, the proposal store, checks and apply. This is the long form of
the `SKILL.md` section; check `bh work triage <verb> --help` where a flag here disagrees with the
binary — the binary wins. Needs `bh` 0.35.0 or later and the same host-owned `intake.external`
switches as single-report triage, plus `comments.enabled` and
`plugins.tracker-github.read.comments.enabled` (a packet without its thread is refused).

## Verbs

| Verb | What it does | Writes |
|---|---|---|
| `bh work triage review --pending [--batch-size N] [--out DIR] [--json]` | Builds cluster-aware packets for the pending set (untriaged or woken reports with no applied proposal): body, **full thread** (ingested first), proposal and review history, a global index of every pending report's title and disposition, and correction metrics. A duplicate cluster never splits across batches. `--pending` is required; `--out` writes one JSON file per batch plus `index.json`. | the thread ingest, and the files in `--out` |
| `bh work triage propose <report> <file\|->` | Stores a proposal (Pass A). The document is **positional** (`-` reads stdin); `--json` is only the output-format flag. Codec and leak lint run first; a refusal writes nothing. | proposal store |
| `bh work triage propose <report> --review-of <N> <file\|->` | Stores a review verdict (`confirmed`/`corrected`/`unsure`) as review pass `N`. A correcting verdict that adopts a correction moves the proposal back to `proposed` with the corrected content. | proposal store |
| `bh work triage check [--pending] [--json]` | Deterministic checks: owner target exists and is open; `share_with` resolves to one canonical in the run (no cycles); fields are consistent (`new` has no `fixed_in`, `fixed` has no type or priority); `reporter_text` passes the leak policy; **`fixed_in` is computed from the first tag containing the commit and overwrites a claimed one**; the commit is on the integration branch; staleness (the branch moved in a cited path, or the thread `seq` advanced). **Exits 1 on any finding**, so a script or a loop can gate on it. | nothing |
| `bh work triage apply --reviewed [--dry-run] [--reroute-to <report>=<hive>] [--json]` | Applies only proposals whose last verdict is `confirmed`, or `corrected` with the correction adopted. Canonicals first; drafts messages, never sends; idempotent; `decision` items are listed, never applied. A `reroute` proposal is **blocked** unless `--reroute-to <report>=<hive>` names the destination (repeat the flag per report). **Operator seats only**; a `--dry-run` works from any seat. | records and **drafts** via the existing verbs |

Who runs what. The skill and the `triager` agent may run only the **read and dry-run** forms:
`triage review`, `triage propose`, `triage check`, `triage apply --reviewed --dry-run`,
`labels review`, and `labels sync --dry-run` / `labels define --dry-run`. The **write** forms are
the operator's, run from an operator seat on their explicit go: `triage apply --reviewed` (with any
`--reroute-to`), `labels define --approve <digest>` and `labels approve --batch <digest>`. The
label verbs, for reference: `bh work labels sync [--all] [--include-closed] [--dry-run]
[--prune-unmapped]` drafts the label changes, `labels define [--dry-run] [--prune] [--approve
<digest>]` plans and (approved) applies the repository's label definitions, `labels review`
renders the drafted batch with its digest, and `labels approve --batch <digest>` approves it.

Proposal dispositions: `new`, `tracked`, `fixed`, `partially-fixed`, `duplicate-of`, `reject`,
`needs-info`, `reroute`, `decision`. Targets carry a role, `owner` or `related`. Reviews carry
`confirmed`, `corrected` or `unsure`. A proposal pins `analysed_commit` and `thread_seq`.

How each disposition applies (so the summary can say what will happen): `new` -> `accept
--new-work`; `tracked` -> `accept --work <owner>`; `fixed` -> `accept --work <closed fixing work>`
(or reject with a reason and a drafted reply when no work fixed it); `partially-fixed` -> new or
tracked work for the **residual**; `duplicate-of` -> `link` to the canonical's work, then `reject`;
`needs-info` -> the question as a draft; `reject` -> `reject` plus a drafted reply; `reroute` ->
`reroute`; `decision` -> listed only.

## Pass A proposal (shape)

```json
{
  "disposition": "partially-fixed",
  "targets": [{"id": "<open work id>", "role": "owner"}, {"id": "<loosely related>", "role": "related"}],
  "share_with": "<canonical report, for a family member>",
  "type": "bug", "priority": 2,
  "fixed_in": "<set only for fixed/partially-fixed; triage check recomputes it>",
  "fix_commit": "<sha of the fixing commit, for fixed/partially-fixed>",
  "reporter_text": "<the outbound reply or question, leak-free; omitted when nothing is sent>",
  "evidence": ["src/x.py:120 @ <sha>", "thread seq 7 (reporter re-check)", "<sha> first in <tag>"],
  "analysed_commit": "<integration branch tip you read>",
  "thread_seq": 7
}
```

Those are the only keys a proposal may carry (the analyst fields); `status`, `reviews` and the like
are refused. Every claim in `evidence` is a `file:line` at a pinned sha, a sha, or a thread `seq`.
The verifier checks it; a claim with none is `unsure` at best.

## Review passes and the verdict document

Pass A is the proposal itself (plain `triage propose <report> -`); it is not a review pass, and
`--review-of A` is refused. bh numbers **review** passes 1, 2, ... in recording order for each
report, across rounds: in the first round **B = 1 and C = 2**. After a re-proposal the count keeps
going (a second round starts at 3), so always say "the next pass number" and do not hard-code B and
C to 1 and 2 beyond the first round. Recording the same verdict twice for the same pass is refused.

The verdict document bh accepts is **exactly** this, and nothing else:

```json
{"verdict": "confirmed|corrected|unsure", "corrections": ["<string>", "..."],
 "pass": 1, "seat": "<string>", "adopt": {"<full corrected proposal, analyst fields only>": "..."}}
```

- `confirmed`: `corrections` is `[]` or omitted; no `adopt`.
- `corrected`: `corrections` has one **string** per thing that was wrong; `adopt` is the **full**
  corrected proposal using only the analyst fields (`disposition`, `targets`, `share_with`, `type`,
  `priority`, `reporter_text`, `evidence`, `analysed_commit`, `thread_seq`, `fixed_in`,
  `fix_commit`). An omitted field becomes its default, so `adopt` replaces the whole content.
  `adopt` is allowed **only** with `corrected`.
- `unsure`: what could not be settled goes in `corrections` as strings; no `adopt`.
- `pass` is an integer or omitted (then bh uses the next pass); never `"B"` or `"C"`. `seat` is
  optional (bh records the acting seat).
- **An unknown key is refused** and nothing is stored: `verified_commit`, `checks`, `evidence`,
  `thread_seq`, `unsure_because`, and `corrections` as an object are all refused.

**The evidence record stays in the skill.** What bh cannot hold (the verified commit, the highest
thread `seq` read, the checks run, the `file:line @ sha` evidence) is kept by the orchestrating
session in the working directory next to the `--out` packets, one file per report and pass:
`<out>/verdicts/<report>.pass<N>.json`. The verifier returns this record in its hand-back (it has
no write tool); only the codec subset above is sent to bh. The operator summary renders the
evidence record, so the operator sees what each verdict rested on.

```json
{"report": "<report>", "pass": 1, "verdict": "corrected",
 "verified_commit": "<sha of the integration branch read>", "thread_seq": 7,
 "checks": ["read git show <sha>: the change covers the crash, not the flag the reporter asked for",
            "git tag --contains <sha> --sort=version:refname | head -1 -> v0.34.0"],
 "evidence": ["src/x.py:120 @ <sha>", "<sha>", "thread seq 7"]}
```

## Sequence

1. `bh work triage review --pending --json --out <dir>` — note the analysed commit and the batch
   list. Keep the output; do not edit packets. Create `<dir>/verdicts/` for the evidence records.
2. **Pass A**, per batch: launch one `triager` agent with the packets. It applies the analysis
   rules, runs the cheap read-only probes, and stores a proposal per report with
   `bh work triage propose <report> -`.
3. **Pass B**, per batch: launch a **fresh** `triager` agent with
   [verifier-prompt.md](verifier-prompt.md). It stores a verdict per proposal with
   `bh work triage propose <report> --review-of <N> -` (the next pass number: 1 in the first
   round) and returns an evidence record per report, which you save as
   `<dir>/verdicts/<report>.pass<N>.json`.
4. Compute the **correction rate for B** = `corrected` / proposals reviewed (report `unsure`
   separately, and reporter-visible corrections as their own count).
5. **Pass C**: a third fresh agent re-verifies (a) every item B marked `corrected` or `unsure`,
   (b) every item whose `reporter_text` changed since its last verdict, and (c) **the whole batch
   if B's correction rate exceeded 10 %**. It records its verdict as the next pass number (2 in the
   first round). Stop when C agrees with B; if C disagrees with B the item is `unresolved` and goes
   to the operator — no further rounds. Report C's correction rate.
6. `bh work triage check --pending --json` (exit 1 means at least one finding). Anything failing
   goes back to Pass A (a re-proposal; the next verifier pass continues the numbering, so a second
   round's B is review pass 3), then through the verifier again. Re-run step 6 until nothing
   fails or the item is listed as held.
7. Write the operator summary (below), rendering each item's evidence record. **Stop.** Nothing is
   applied.
8. On the operator's explicit go, run `bh work triage apply --reviewed --dry-run` and compare it
   with the summary. **`apply` itself is operator-only**: give the operator the exact command
   (`bh work triage apply --reviewed`, plus `--reroute-to <report>=<hive>` for each `reroute`
   proposal, which is blocked without it) to run from their operator seat. The skill and the agent
   never run the real `apply`, and never approve, send, edit or discard an outbox record. The
   operator hands the drafts on.

An item missing a B verdict, failing a check, or `unresolved` is **held**: it is never applied
and is listed under "Held and unresolved".

## Operator summary (template)

```text
TRIAGE REVIEW — <n> reports, <k> batches, analysed commit <sha>
Correction rate  Pass B: <x>/<n> (<pct>%)  reporter-visible: <r>/<m>   unsure: <u>
                 Pass C: <x>/<c> (<pct>%)  scope: <corrected+unsure only | whole batch (B > 10%)>
triage check: <pass | n failures, listed in section 4>

1. INTERNAL DISPOSITIONS   (what bh records; nothing here is sent)
   Family <canonical issue>  — owner: <open work>  related: <ids>
     <issue>  <disposition>  type/priority  verdict <confirmed|corrected by B|C>  evidence <file:line @ sha, from the evidence record>
   ...

2. OUTBOUND CONTENT   (everything that would reach a reporter — review this, not section 1)
   #<issue> by <reporter>   reply | question | reject reason | label change
     verdict: <confirmed|corrected|...>   disposition: <...>
     """<the exact text, verbatim>"""
   ...

3. DECISIONS FOR THE OPERATOR   (listed, never applied)
   #<issue>  <the choice>   recommendation: <...>   because: <...>

4. HELD AND UNRESOLVED
   #<issue>  <failed check | no B verdict | C disagrees with B | stale>   what unblocks it

Evidence records: <out>/verdicts/<report>.pass<N>.json (verified commit, thread seq, checks, file:line @ sha)
To apply, run from your operator seat: bh work triage apply --reviewed --dry-run, then without --dry-run
(add --reroute-to <report>=<hive> for each reroute). I run the dry-run only; apply, label approval and
sending are yours.
```

Section 2 is separate on purpose: it mirrors the review artifact the operator used on 2026-11-04
and lets them approve exactly what would be sent. It lists **every** reply, question, reject
reason and label change, each with its reporter and the public issue, the verbatim text and the
verdict that cleared it. No outbound item may appear only in section 1. Internal material (bead
ids, branches, paths, seat names, private labels) stays out of section 2. Label changes are the
planned projection (read `bh work labels review`); the operator approves them with their own
verbs.

## Dry-run over the 2026-11-04 error classes

The recorded first-pass proposals are replayed as a fixture by the review-gated triage code
(beadhive `bh-9aqmv`); the same five reporter-visible errors must be caught by Pass B or by
`triage check` before apply. This is how this procedure catches each, by error class:

| 2026-11-04 error | Wrong outcome | Caught by |
|---|---|---|
| #3, #25 | told "fixed" while the thread showed it unresolved or the fix partial | **B** — fixed checks: read the diff, ask what is left, check the reporter re-check in the thread; and **`check`** — the computed `fixed_in` / branch ancestry disagrees with the claim. Correction: `partially-fixed` + residual work |
| #110 | "fixed" with a claimed fix version | **`check`** — `fixed_in` is recomputed from the first containing tag and the claim is overwritten or refused; and **B** — first-tag and ancestry check |
| #14 | false reject | **B** — reject checks: reason true at HEAD? thread re-check that defeats it? Correction: not a reject |
| #11 | false "works as designed" | **B** — reject checks: runs the cheap read-only probe the analyst skipped and cites the design source. (No deterministic check can settle a claim about a tool, so B is the catcher here.) |

Also caught before apply: closed or loose targets (#1, #7, #10, #15, #91) by `check` (owner must
be open) and B (same defect?); unread threads (#1, #3, #4, #14, #25) by B step 1 and the packet,
which carries the thread; cross-batch families by the cluster-aware batches and the `share_with`
check; the maintainer choice misrouted as a question (#40) by B's needs-info/decision checks.
Confirm each row against the replayed fixture when it lands, and change a row here if the fixture
shows a different catcher.

### Walkthrough: the verdict documents bh would receive

The same classes, as the documents the verifier sends (`bh work triage propose <report>
--review-of <N> -`, first round, so B = pass 1 and C = pass 2). `<sha>`, `<tag>` and `<work>` are
placeholders for the fixture's values.

**#3 / #25, told "fixed" but the fix was partial. B corrects it:**

```json
{
  "verdict": "corrected",
  "corrections": [
    "the proposal says fixed, but the commit only handles the crash; the flag the reporter asked for is still missing at HEAD",
    "the reporter's re-check at thread seq 7 says it still fails, which the proposal did not account for"
  ],
  "pass": 1,
  "adopt": {
    "disposition": "partially-fixed",
    "targets": [{"id": "<open residual work>", "role": "owner"}],
    "reporter_text": "Part of this is fixed: the crash no longer happens. The flag you asked for is still missing and is tracked as follow-up work.",
    "evidence": ["src/x.py:120 @ <sha>", "<sha> first in <tag>", "thread seq 7 (reporter re-check)"],
    "analysed_commit": "<sha of the integration tip B read>",
    "thread_seq": 7,
    "fixed_in": "<tag>",
    "fix_commit": "<sha>"
  }
}
```

The evidence record for this verdict (`<out>/verdicts/<report>.pass1.json`, never sent to bh)
carries what the codec cannot: `verified_commit`, `thread_seq` 7, the `checks` run (diff read, tag
computed, residual confirmed at HEAD) and the `file:line @ sha` list.

**#110, a claimed fix version.** No verdict is needed to stop it: `triage check` recomputes
`fixed_in` from the first tag containing the commit and overwrites or refuses the claim. If B
also notices, it corrects with `adopt` carrying the computed `fixed_in`, and a `corrections`
string saying the claimed version differed.

**#11, "works as designed" without the probe.** B runs the cheap read-only probe the analyst
skipped. If the probe settles it, B corrects (`adopt.disposition` is no longer `reject`; the
`corrections` string names the probe and its result). If the probe cannot settle it, B does not
guess:

```json
{
  "verdict": "unsure",
  "corrections": [
    "could not confirm the design intent: no design source found for the behaviour, and the tool's --help output does not say"
  ],
  "pass": 1
}
```

An `unsure` item goes to Pass C (`--review-of 2`). A proposal B cannot break is:

```json
{"verdict": "confirmed", "corrections": []}
```
