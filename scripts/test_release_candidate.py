#!/usr/bin/env python3
"""Exercise candidate acceptance success and drift/unsafe-input failures."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import check_release_candidate as check


def seal(document: dict) -> dict:
    document["digest"] = check.digest(document)
    return document


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def fixture(root: Path) -> tuple[dict, dict, Path]:
    artifact = root / "artifact"
    files = {
        ".claude-plugin/marketplace.json": '{"name":"beadhive","plugins":[{"name":"bh","source":"./beadhive","version":"0.5.0"}]}\n',
        "LICENSE": "fixture license\n",
        "beadhive/.claude-plugin/plugin.json": '{"name":"bh","version":"0.5.0"}\n',
        "beadhive/hooks/hooks.json": '{"hooks":{"SessionStart":[{"hooks":[{"type":"command","command":"${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh"}]}]}}\n',
        "beadhive/scripts/hook.sh": "#!/bin/sh\nexit 0\n",
        "beadhive/.mcp.json": '{"mcpServers":{"bh":{"command":"bh-mcp","args":[]}}}\n',
        "beadhive/OPERATOR-COMMUNICATION.md": "# Operator-facing communication contract\n\n## Always-on rules\n\n<!-- shared-rules:start -->\nRules\n<!-- shared-rules:end -->\n\nLoad `bh:operator-communication`\n",
        "beadhive/output-styles/beadhive-operator-brief.md": "Use bh:operator-communication\n",
        "beadhive/output-styles/beadhive-operator-brief-verbose.md": "Use bh:operator-communication\n",
        "beadhive/skills/fixture/SKILL.md": "---\nname: fixture\ndescription: fixture skill\n---\n\n[Readme](README.md)\n",
        "beadhive/skills/fixture/README.md": "Fixture reference.\n",
    }
    inventory = {}
    for name, content in files.items():
        path = artifact / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755 if name.endswith("hook.sh") else 0o644)
        inventory[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "mode": "100755" if name.endswith("hook.sh") else "100644"}
    candidate = seal({
        "schemaVersion": 1, "pack": "beadhive", "authoredVersion": "0.5.0", "releaseVersion": "0.5.0",
        "target": "claude-code", "sourceCommit": "a" * 40, "hitchRevision": "b" * 40,
        "files": inventory, "payloadDigest": check.digest(inventory),
    })
    receipt = seal({
        "schemaVersion": 1, "candidateDigest": candidate["digest"], "planDigest": "c" * 64,
        "payloadDigest": candidate["payloadDigest"],
        "destination": {"identity": "https://github.com/beadhive/claude-plugin", "expectedBase": "d" * 40,
                        "branch": "release/test", "layout": "root", "path": "", "baseBranch": "main",
                        "remote": "origin", "immutable": False},
        "destinationCommit": "e" * 40, "branch": "release/test", "sourceCommit": candidate["sourceCommit"],
        "hitchRevision": candidate["hitchRevision"], "authoredVersion": candidate["authoredVersion"],
        "releaseVersion": candidate["releaseVersion"], "pushed": True, "remoteVerified": True,
        "prUrl": "https://github.com/beadhive/claude-plugin/pull/1", "filesVerified": len(inventory),
    })
    return candidate, receipt, artifact


def rejected(label: str, operation) -> None:
    try:
        operation()
    except check.Invalid:
        return
    raise AssertionError(f"expected rejection: {label}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="release-candidate-test-") as tmp:
        root = Path(tmp)
        candidate, receipt, artifact = fixture(root)
        check.validate_candidate(candidate, candidate["digest"])
        check.public_contract(candidate, artifact)
        check.validate_receipt(receipt, candidate, receipt["digest"])
        destination_repo = root / "destination"
        shutil.copytree(artifact, destination_repo)
        subprocess.run(["git", "-C", str(destination_repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(destination_repo), "config", "user.name", "QA fixture"], check=True)
        subprocess.run(["git", "-C", str(destination_repo), "config", "user.email", "qa@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(destination_repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(destination_repo), "commit", "-qm", "fixture"], check=True)
        receipt["destinationCommit"] = subprocess.run(["git", "-C", str(destination_repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        receipt = seal({key: value for key, value in receipt.items() if key != "digest"})
        candidate_path, receipt_path = root / "candidate.json", root / "receipt.json"
        write_json(candidate_path, candidate)
        write_json(receipt_path, receipt)
        command = [sys.executable, str(Path(check.__file__).resolve()), "--candidate", str(candidate_path), "--receipt", str(receipt_path), "--artifact", str(artifact), "--expected-candidate-digest", candidate["digest"], "--expected-receipt-digest", receipt["digest"], "--destination-repo", str(destination_repo)]
        success = subprocess.run(command, capture_output=True, text=True)
        assert success.returncode == 0, success.stderr
        (destination_repo / "beadhive/OPERATOR-COMMUNICATION.md").write_text("post promotion edit\n", encoding="utf-8")
        drift = subprocess.run(command, capture_output=True, text=True)
        assert drift.returncode != 0 and "post-promotion worktree edits" in drift.stderr
        rejected("independent candidate pin mismatch", lambda: check.validate_candidate(candidate, "f" * 64))
        rejected("candidate bytes altered", lambda: check.validate_candidate({**candidate, "digest": "0" * 64}, candidate["digest"]))
        extra = artifact / "unexpected.txt"
        extra.write_text("unreviewed", encoding="utf-8")
        rejected("extra artifact file", lambda: check.public_contract(candidate, artifact))
        extra.unlink()
        hook = artifact / "beadhive/scripts/hook.sh"
        hook.chmod(0o644)
        rejected("hook executable mode drift", lambda: check.public_contract(candidate, artifact))
        hook.chmod(0o755)
        rejected("unsafe private path", lambda: check.safe_relative(".git/config"))
        rejected("unsafe traversal", lambda: check.safe_relative("beadhive/../secret"))
        rejected("receipt candidate mismatch", lambda: check.validate_receipt({**receipt, "candidateDigest": "f" * 64}, candidate, receipt["digest"]))
        rejected("receipt schema rejects wrong nested field types", lambda: check.validate_schema({**receipt, "destination": {**receipt["destination"], "immutable": "false"}}, "receipt"))
        (root / "duplicate.json").write_text('{"schemaVersion":1,"schemaVersion":2}', encoding="utf-8")
        rejected("duplicate JSON keys", lambda: check.read_json(root / "duplicate.json"))
        bad_frontmatter = root / "bad-frontmatter"
        (bad_frontmatter / "beadhive/skills/fixture").mkdir(parents=True)
        (bad_frontmatter / "beadhive/skills/fixture/SKILL.md").write_text("---\nname: fixture\nname: duplicate\ndescription: test\n---\n", encoding="utf-8")
        rejected("duplicate YAML frontmatter", lambda: check.validate_frontmatter(bad_frontmatter, {"beadhive/skills/fixture/SKILL.md": {}}))
        (bad_frontmatter / "beadhive/skills/fixture/SKILL.md").write_text("---\nname: fixture\ndescription: test\n---\n\n[Broken](missing.md)\n", encoding="utf-8")
        rejected("broken skill link", lambda: check.validate_frontmatter(bad_frontmatter, {"beadhive/skills/fixture/SKILL.md": {}}))
    print("release candidate QA: CLI metadata binding and twelve drift/unsafe-input negatives passed")


if __name__ == "__main__":
    main()
