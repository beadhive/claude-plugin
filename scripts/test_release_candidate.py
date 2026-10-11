#!/usr/bin/env python3
"""Exercise strict candidate schemas, payload/publisher closure, and receipt linkage."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import check_release_candidate as check

ROOT = Path(check.__file__).resolve().parents[1]


def seal(document: dict) -> dict:
    return {**document, "digest": check.digest(document)}


def entry(path: Path) -> dict[str, str]:
    executable = bool(path.stat().st_mode & 0o111)
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "mode": "100755" if executable else "100644"}


def candidate(files: dict[str, dict[str, str]]) -> dict:
    return seal({
        "schemaVersion": 1,
        "pack": "beadhive",
        "authoredVersion": "0.6.0",
        "releaseVersion": "0.6.0",
        "target": "claude-code",
        "sourceCommit": "a" * 40,
        "hitchRevision": "b" * 40,
        "files": files,
        "payloadDigest": check.digest(files),
    })


def write(path: Path, content: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(mode)


def rejected(label: str, operation) -> None:
    try:
        operation()
    except check.Invalid:
        return
    raise AssertionError(f"expected rejection: {label}")


def git(repo: Path, *args: str) -> str:
    import subprocess
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def promotion_fixture(root: Path) -> tuple[dict, dict, dict, Path]:
    import subprocess
    repo = root / "destination"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    git(repo, "config", "user.name", "QA fixture")
    git(repo, "config", "user.email", "qa@example.invalid")
    write(repo / "owned/stale.md", b"stale\n")
    write(repo / "outside.txt", b"kept\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    base = git(repo, "rev-parse", "HEAD")
    content = b"approved bytes\n"
    write(repo / "owned/file.md", content)
    (repo / "owned/stale.md").unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "promotion")
    commit = git(repo, "rev-parse", "HEAD")
    files = {"owned/file.md": entry(repo / "owned/file.md")}
    promotion = candidate(files)
    dest = {"identity": "https://github.com/beadhive/claude-plugin", "expectedBase": base,
            "branch": "release/test", "layout": "root", "path": "", "baseBranch": "main",
            "remote": "origin", "immutable": False}
    plan = seal({"schemaVersion": 1, "candidateDigest": promotion["digest"],
                 "payloadDigest": promotion["payloadDigest"], "destination": dest,
                 "ownedPaths": ["owned/"], "copies": ["owned/file.md"],
                 "deletions": ["owned/stale.md"],
                 "actions": ["create-review-branch", "copy-approved-files", "remove-owned-stale-files", "commit", "verify-local"]})
    receipt = seal({"schemaVersion": 1, "candidateDigest": promotion["digest"],
                    "planDigest": plan["digest"], "payloadDigest": promotion["payloadDigest"],
                    "destination": dest, "destinationCommit": commit, "branch": dest["branch"],
                    "sourceCommit": promotion["sourceCommit"], "hitchRevision": promotion["hitchRevision"],
                    "authoredVersion": promotion["authoredVersion"], "releaseVersion": promotion["releaseVersion"],
                    "pushed": False, "remoteVerified": False, "prUrl": None,
                    "filesVerified": len(promotion["files"])})
    return promotion, plan, receipt, repo


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="claude-release-qa-test-") as temporary:
        root = Path(temporary)
        artifact, qa = root / "artifact", root / "qa-root"
        artifact.mkdir()
        qa.mkdir()
        subprocess.run(["git", "init", "-q", str(artifact)], check=True)  # paired caller has Git metadata, no commit yet

        payload_name = "beadhive/skills/example/SKILL.md"
        payload_bytes = b"---\nname: example\ndescription: test\n---\n"
        write(artifact / payload_name, payload_bytes)
        payload_files = {payload_name: entry(artifact / payload_name)}
        payload = candidate(payload_files)
        write(artifact / "release-receipt.json", json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode() + b"\n")
        # Candidate JSON bytes are the producer's canonical serialization.
        write(artifact / "release-receipt.json", (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode())
        sidecar = entry(artifact / "release-receipt.json")
        promotion_files = {**payload_files, "release-receipt.json": sidecar}
        promotion = candidate(promotion_files)
        check.validate_candidate(payload, payload["digest"], ROOT)
        check.validate_candidate(promotion, promotion["digest"], ROOT)
        check.validate_producer_closure(artifact, payload, promotion)

        owned = ["qa/destination-owned.json", "qa/check.md"]
        write(qa / owned[0], (json.dumps({"purpose": "fixture overlay", "files": owned}, indent=2) + "\n").encode())
        write(qa / owned[1], b"QA fixture.\n")
        for name in owned:
            write(artifact / name, (qa / name).read_bytes())
        qa_inventory = {name: entry(artifact / name) for name in owned}
        transport = candidate({**payload_files, "release-receipt.json": sidecar, **qa_inventory})
        check.validate_candidate(transport, transport["digest"], ROOT)
        check.validate_transport_closure(artifact, payload, transport, qa)

        rejected("un-pinned candidate", lambda: check.validate_candidate(payload, "f" * 64, ROOT))
        rejected("payload-only candidate cannot stand in for publisher candidate", lambda: check.validate_transport_closure(artifact, payload, payload, qa))
        rejected("payload sidecar altered", lambda: (write(artifact / "release-receipt.json", b"{}\n"), check.validate_producer_closure(artifact, payload, promotion)))
        write(artifact / "release-receipt.json", (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode())
        write(artifact / "qa/unapproved.md", b"extra\n")
        rejected("unapproved transport extra", lambda: check.validate_transport_closure(artifact, payload, transport, qa))
        (artifact / "qa/unapproved.md").unlink()
        (artifact / "qa/check.md").chmod(0o755)
        rejected("QA mode drift", lambda: check.validate_transport_closure(artifact, payload, transport, qa))
        (artifact / "qa/check.md").chmod(0o644)
        rejected("unsafe path", lambda: check.safe_path("beadhive/../private"))
        duplicate = root / "duplicate.json"
        duplicate.write_text('{"schemaVersion":1,"schemaVersion":2}', encoding="utf-8")
        rejected("duplicate JSON key", lambda: check.read_json(duplicate))

        receipt = seal({
            "schemaVersion": 1,
            "candidateDigest": promotion["digest"],
            "planDigest": "c" * 64,
            "payloadDigest": promotion["payloadDigest"],
            "destination": {"identity": "https://github.com/beadhive/claude-plugin", "expectedBase": "d" * 40,
                            "branch": "release/test", "layout": "root", "path": "", "baseBranch": "main",
                            "remote": "origin", "immutable": False},
            "destinationCommit": "e" * 40,
            "branch": "release/test",
            "sourceCommit": promotion["sourceCommit"],
            "hitchRevision": promotion["hitchRevision"],
            "authoredVersion": promotion["authoredVersion"],
            "releaseVersion": promotion["releaseVersion"],
            "pushed": False,
            "remoteVerified": False,
            "prUrl": None,
            "filesVerified": len(promotion["files"]),
        })
        check.validate_receipt(receipt, promotion, receipt["digest"], "local", ROOT)
        substituted_receipt = seal({**{key: value for key, value in receipt.items() if key != "digest"}, "candidateDigest": payload["digest"]})
        rejected("payload-only digest cannot be substituted for full publisher receipt binding",
                 lambda: check.validate_receipt(substituted_receipt, promotion, substituted_receipt["digest"], "local", ROOT))
        rejected("receipt independent pin mismatch", lambda: check.validate_receipt(receipt, promotion, "f" * 64, "local", ROOT))

        promotion, plan, promotion_receipt, destination = promotion_fixture(root)
        check.validate_receipt(promotion_receipt, promotion, promotion_receipt["digest"], "local", ROOT)
        check.validate_promotion(promotion_receipt, promotion, plan, destination)

        def clone_repo(label: str) -> Path:
            clone = root / label
            subprocess.run(["git", "clone", "-q", str(destination), str(clone)], check=True)
            git(clone, "config", "user.name", "QA fixture")
            git(clone, "config", "user.email", "qa@example.invalid")
            return clone

        def resealed_receipt(repo: Path, selected_plan: dict = plan) -> dict:
            unsigned = {key: value for key, value in promotion_receipt.items() if key not in {"digest", "planDigest", "destinationCommit", "destination"}}
            unsigned.update(planDigest=selected_plan["digest"], destination=selected_plan["destination"], destinationCommit=git(repo, "rev-parse", "HEAD"))
            return seal(unsigned)

        extra_repo = clone_repo("extra-owned")
        write(extra_repo / "owned/unapproved.md", b"extra owned\n")
        git(extra_repo, "add", "-A")
        git(extra_repo, "commit", "--amend", "-qm", "unapproved owned extra")
        rejected("owned Git tree extra", lambda: check.validate_promotion(resealed_receipt(extra_repo), promotion, plan, extra_repo))

        mode_repo = clone_repo("mode-drift")
        (mode_repo / "owned/file.md").chmod(0o755)
        git(mode_repo, "add", "-A")
        git(mode_repo, "commit", "--amend", "-qm", "mode drift")
        rejected("owned Git mode drift", lambda: check.validate_promotion(resealed_receipt(mode_repo), promotion, plan, mode_repo))

        outside_repo = clone_repo("outside-drift")
        write(outside_repo / "outside.txt", b"changed outside owned scope\n")
        git(outside_repo, "add", "-A")
        git(outside_repo, "commit", "--amend", "-qm", "outside drift")
        rejected("unowned destination change", lambda: check.validate_promotion(resealed_receipt(outside_repo), promotion, plan, outside_repo))

        wrong_payload_plan = seal({**{key: value for key, value in plan.items() if key != "digest"}, "payloadDigest": "f" * 64})
        rejected("plan payload digest mismatch", lambda: check.validate_promotion(resealed_receipt(destination, wrong_payload_plan), promotion, wrong_payload_plan, destination))
        wrong_base_dest = {**plan["destination"], "expectedBase": "f" * 40}
        wrong_base_plan = seal({**{key: value for key, value in plan.items() if key not in {"digest", "destination"}}, "destination": wrong_base_dest})
        rejected("promotion commit parent differs from reviewed base", lambda: check.validate_promotion(resealed_receipt(destination, wrong_base_plan), promotion, wrong_base_plan, destination))
        missing_deletion_plan = seal({**{key: value for key, value in plan.items() if key not in {"digest", "deletions"}}, "deletions": []})
        rejected("stale owned deletion omitted from plan", lambda: check.validate_promotion(resealed_receipt(destination, missing_deletion_plan), promotion, missing_deletion_plan, destination))

        agf_repo = root / "agf-main"
        agf_repo.mkdir()
        git(agf_repo, "init", "-q", "-b", "main")
        git(agf_repo, "config", "user.name", "QA fixture")
        git(agf_repo, "config", "user.email", "qa@example.invalid")
        write(agf_repo / "outside.txt", b"preserved unowned\n")
        write(agf_repo / "beadhive/stale.md", b"stale\n")
        git(agf_repo, "add", "-A"); git(agf_repo, "commit", "-qm", "base")
        agf_base = git(agf_repo, "rev-parse", "HEAD")
        git(agf_repo, "checkout", "-qb", "worker")
        (agf_repo / "beadhive/stale.md").unlink()
        write(agf_repo / "beadhive/file.md", b"generated\n")
        write(agf_repo / "qa/destination-owned.json", b'{"purpose":"AGF fixture QA","files":["qa/destination-owned.json"]}\n')
        agf_payload = candidate({"beadhive/file.md": entry(agf_repo / "beadhive/file.md")})
        write(agf_repo / "release-receipt.json", check.canonical(agf_payload) + b"\n")
        agf_transport = candidate({name: entry(agf_repo / name) for name in
                                   ("beadhive/file.md", "qa/destination-owned.json", "release-receipt.json")})
        git(agf_repo, "add", "-A"); git(agf_repo, "commit", "-qm", "delivery")
        staged = git(agf_repo, "rev-parse", "HEAD")
        git(agf_repo, "checkout", "-q", "main"); git(agf_repo, "merge", "--no-ff", "-qm", "AGF bubble", "worker")
        agf_main = git(agf_repo, "rev-parse", "HEAD")
        agf_plan = seal({"schemaVersion": 1, "kind": "agf-main-delivery-plan",
                        "candidateDigest": agf_transport["digest"], "payloadDigest": agf_transport["payloadDigest"],
                        "destination": {"identity": "https://github.com/beadhive/claude-plugin.git", "expectedBase": agf_base,
                                        "ref": "refs/heads/main", "hive": "bh-cp", "molecule": "bh-cp-0mm", "bead": "bh-cp-as6"},
                        "ownedPaths": ["beadhive/", "qa/destination-owned.json", "release-receipt.json"],
                        "copies": sorted(agf_transport["files"]), "deletions": ["beadhive/stale.md"]})
        agf_record = {"target": "claude-code", "transportCandidateDigest": agf_transport["digest"],
                      "payloadCandidateDigest": agf_payload["digest"], "planDigest": agf_plan["digest"],
                      "sourceCommit": agf_payload["sourceCommit"], "hitchRevision": agf_payload["hitchRevision"],
                      "packVersion": agf_payload["authoredVersion"], "releaseVersion": agf_payload["releaseVersion"],
                      "expectedBase": agf_base, "qaCommit": staged,
                      "qaFilesDigest": check.digest({"qa/destination-owned.json": agf_transport["files"]["qa/destination-owned.json"]}),
                      "stagedCommit": staged, "destinationCommit": agf_main,
                      "agf": {"hive": "bh-cp", "molecule": "bh-cp-0mm", "bead": "bh-cp-as6", "reviewGate": "actual-gate",
                              "reviewer": "reviewer", "merger": "merger", "reviewResult": "approved", "moleculeResult": "closed"},
                      "publicMain": {"identity": "https://github.com/beadhive/claude-plugin.git", "ref": "refs/heads/main", "commit": agf_main}}
        def verify_agf(record=agf_record, selected_plan=agf_plan, pin=None):
            check.validate_agf_delivery(record, pin or check.digest(record), agf_payload, agf_transport,
                                        selected_plan, selected_plan["digest"], agf_repo, agf_repo)
        verify_agf()
        rejected("AGF independent evidence pin mismatch", lambda: verify_agf(pin="f" * 64))
        rejected("AGF QA inventory mismatch", lambda: verify_agf({**agf_record, "qaFilesDigest": "f" * 64}))
        rejected("AGF incomplete review", lambda: verify_agf({**agf_record, "agf": {**agf_record["agf"], "reviewResult": "pending"}}))
        rejected("AGF substituted payload candidate", lambda: verify_agf({**agf_record, "payloadCandidateDigest": "f" * 64}))
        rejected("legacy plan cannot masquerade as AGF", lambda: verify_agf(selected_plan=plan))
        write(agf_repo / "outside.txt", b"unowned drift\n")
        git(agf_repo, "add", "-A"); git(agf_repo, "commit", "-qm", "unowned drift")
        changed_main = git(agf_repo, "rev-parse", "HEAD")
        changed_record = {**agf_record, "destinationCommit": changed_main,
                          "publicMain": {**agf_record["publicMain"], "commit": changed_main}}
        rejected("AGF unowned drift", lambda: verify_agf(changed_record))

        committed = root / "committed-payload"
        write(committed / ".claude-plugin/marketplace.json", b"{}\n")
        write(committed / "beadhive/README.md", b"generated\n")
        write(committed / "LICENSE", b"license\n")
        committed_candidate = candidate(check.generated_inventory(committed))
        write(committed / "release-receipt.json", (json.dumps(committed_candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode())
        assert check.validate_committed_payload(committed, ROOT)
        write(committed / "beadhive/README.md", b"edited generated content\n")
        rejected("committed generated payload edit", lambda: check.validate_committed_payload(committed, ROOT))
        write(committed / "beadhive/README.md", b"generated\n")
        write(committed / "beadhive/unapproved.md", b"extra\n")
        rejected("extra generated payload file", lambda: check.validate_committed_payload(committed, ROOT))

    print("release QA: staged-Git closure, pinned plan/receipt, owned-tree/mode/deletion drift, and generated payload negatives passed")


if __name__ == "__main__":
    main()
