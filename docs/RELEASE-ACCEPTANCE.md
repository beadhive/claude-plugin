# Canonical Claude release acceptance

The canonical skills release builds the complete self-contained Claude candidate. The public
quality workflow runs repository checks without cloning the private skills repository,
regenerating content, or receiving private source credentials. Candidate/receipt artifact intake
in public CI is still pending a stable upstream handoff. The candidate records the
full source and Hitch Git revisions, version, complete file inventory, executable modes, and
payload digest. The receipt binds that candidate to the destination plan and promotion commit.

`just check` validates the reusable checker and its tamper cases. The checks need Python 3,
`jsonschema`, and `PyYAML`; the public quality workflow installs both Python packages. A local
promotion metadata check is a separate, fail-closed command and requires all six inputs:

```sh
RELEASE_CANDIDATE=/path/to/candidate.json \
RELEASE_RECEIPT=/path/to/receipt.json \
RELEASE_ARTIFACT=/path/to/self-contained-artifact \
RELEASE_DESTINATION_REPO=/path/to/public-checkout \
APPROVED_CANDIDATE_DIGEST=<independently-approved-64-character-sha256> \
APPROVED_RECEIPT_DIGEST=<independently-approved-64-character-sha256> \
just accept-release
```

Both digests must come from the reviewed canonical release allocation, independently of their
documents. The checker validates the public Hitch candidate and receipt v1 schemas, canonical
SHA-256 seals, candidate/receipt linkage, every artifact path/byte/mode, the marketplace identity
and source, executable hook containment, MCP declaration, operator contract, and that the public
checkout HEAD equals the receipt's destination commit. A pushed first-release receipt may have no
PR URL; the receipt schema and push flags are checked either way. Any missing input, extra file,
changed byte or mode, unsafe path, altered candidate, checkout drift, or receipt mismatch fails.
The schemas in `schemas/` were inspected at Hitch revision
`144c953e96dbfad411f562cbe432aaaec65a70a9`; the final candidate's `hitchRevision` must be checked
against the release-approved Hitch source before this check can count as acceptance.

Until the complete candidate and receipt are allocated, the promotion metadata check is
**unavailable**. Current public CI does not yet download or consume candidate/receipt artifacts.
The historical compiler `788c3821b6ca30578aa2baa6751e436f97ee9660` is not a substitute for the
candidate's compiler revision. Do not infer a release version or ownership transfer from fixture
checks. Preserve the current public `bh@beadhive` identity and version `0.5.0` until the paired
release gate approves a change.

## Public installation and handoff

Run the isolated actual public installation/update using `bh@beadhive`, then record the public
destination commit, candidate version and digest, artifact SHA-256, candidate source and Hitch
revisions, receipt digest, native Claude Code CLI version, MCP registration/startup evidence,
hook execution evidence, and selected agent/style loading evidence. Record compatibility
boundaries and rollback tags that the operator has verified. A local fixture validates the QA
checker only; it does not establish public installation or native loading. Linux native loading
was previously observed; Darwin execution remains deferred and must remain reported as such.
Passing this metadata check does not establish native installation or loading. Isolated
SessionStart execution, real MCP startup, and the supported-version matrix remain pending against
the allocated candidate and agreed client-version policy.

Send the exact evidence to `bh-skls-ta1` as the operator handoff referencing `hq-vb2y`. No
destination apply, public merge, push, tag, release, ownership notice, or source-ownership change
follows automatically from passing these checks. Those actions remain behind concrete operator
approval and the paired-release decision.
