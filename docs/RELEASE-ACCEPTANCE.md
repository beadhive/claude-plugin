# Canonical Claude release acceptance

The canonical skills release produces two distinct Hitch candidate documents. The payload-only
candidate describes the generated `beadhive/` and `.claude-plugin/` payload and is also copied as
root `release-receipt.json` in the payload. The complete publisher candidate binds that
payload, the sidecar, and the exact destination-owned QA overlay. The sidecar is not a promotion
receipt. A later Hitch promotion receipt binds the complete publisher candidate to the reviewed
plan and destination commit. The checker independently pins each candidate, plan, and receipt;
none is trusted just because its internal digest is self-consistent.

Canonical content changes must be made and reviewed in the canonical skills source, then rebuilt
into a new candidate with fresh source/Hitch provenance and independent payload/publisher digests.
Do not hand-edit generated `beadhive/` or `.claude-plugin/` files in this destination. Until the
paired ownership switch is explicitly approved, route requested content changes through the
paired-release operator; this repository remains `bh@beadhive` at 0.5.0. Re-run candidate transport
QA, obtain the pinned promotion plan/receipt, then complete the separate native installation gate.

`just check` runs the existing public quality suite, operator contract checks, candidate checker
drift tests, and—when root `release-receipt.json` exists—compares committed generated scopes
(`.claude-plugin/`, `beadhive/`, and root `LICENSE`) against the payload-only sidecar. This catches
post-promotion generated-file edits and extras while allowing destination-owned QA/docs outside
those scopes. The sidecar consistency check is not an independent candidate approval, publisher
closure, promotion receipt, or native acceptance. Legacy source checkouts without the sidecar
report that the generated-payload check is unavailable. Checker dependencies are pinned in
`pyproject.toml`/`uv.lock` (`jsonschema`
and `PyYAML`). `just accept-release` is a local fail-closed promotion metadata check and needs
these variables:

```sh
RELEASE_PAYLOAD_CANDIDATE=/path/to/payload-candidate.json \
RELEASE_PROMOTION_CANDIDATE=/path/to/complete-publisher-candidate.json \
RELEASE_ARTIFACT=/path/to/assembled-payload-and-QA-overlay \
APPROVED_PAYLOAD_CANDIDATE_DIGEST=<independently-approved-sha256> \
APPROVED_PROMOTION_CANDIDATE_DIGEST=<independently-approved-sha256> \
just accept-release
```

This transport stage intentionally needs no promotion receipt and can run before the destination
commit. The public `Pinned Claude candidate acceptance` workflow is manually dispatched with
public HTTPS artifact URLs and independent digest inputs. It has read-only repository permission,
rejects URL credentials/query strings, uses no private-source credentials, and performs no
publication action. Its workflow must first land on the default branch before GitHub can dispatch
it; no remote run is claimed here.

A complete promotion metadata check additionally requires `RELEASE_RECEIPT`,
`RELEASE_PLAN`, `RELEASE_DESTINATION_REPO`, `APPROVED_RECEIPT_DIGEST`,
`APPROVED_PLAN_DIGEST`, and `RELEASE_RECEIPT_MODE=local|remote`. A local Hitch receipt must say
`pushed=false` and `remoteVerified=false`; a remotely verified receipt must say both true. The
checker verifies the receipt against the complete publisher candidate (never the payload-only
sidecar), the plan's digest and destination, a single-parent destination commit at the expected
base, exact owned-tree bytes and modes, absence of planned deletions, and a clean checkout.
Receipt metadata verifies promotion content and provenance only; it does not establish native
installation or loading. Current QA path ownership is declared in `qa/destination-owned.json`.
The paired release caller must bind the committed mode and SHA-256 of every path in that list.

The current producer candidate is a useful compatibility test, but it is not a public promotion
receipt or installation result. Preserve public `bh@beadhive` ownership/version `0.5.0` until the
paired release gate approves a change. The candidate reports 0.6.0 and source commit
`0f921d4b12da6fdd1106a1b2ba667cff145cfd7c`, with Hitch revision
`144c953e96dbfad411f562cbe432aaaec65a70a9`; the prior compiler revision is not a substitute.

## Public installation and handoff

The separate `bh-cp-7ts` acceptance still requires an isolated real public install/update using
`bh@beadhive`. Record the public destination commit, candidate version and digest, artifact
SHA-256, source and Hitch revisions, receipt digest, Claude Code CLI version, MCP registration and
startup, hook execution, and selected agent/style loading. Also record the agreed compatibility
matrix and rollback evidence. A local fixture, producer compatibility check, or metadata receipt
is not native acceptance. Linux native loading was previously observed; Darwin remains deferred.
SessionStart execution, a real MCP probe, and the supported-version matrix remain pending against
the allocated candidate and agreed client policy. No destination apply, public merge, push, tag,
release, ownership notice, or source-ownership change follows from these QA checks.
