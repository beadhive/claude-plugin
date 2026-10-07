#!/usr/bin/env python3
"""Validate Beadhive payload and publisher candidates, then optional Hitch promotion evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_HASHES = {
    "candidate": "6ece5355c007b5be2a1d7533ba7a70737d71e427626cdd0cec67bf925d794385",
    "plan": "0668a79c5bc047bab648c464cd9bc1ed1a85c59a5567710654973201fac11815",
    "receipt": "3a6d81aa3bd124b30abb6a570f9df4b418aa641a9f5dafd6fbd84f873ee1442c",
}
SEMVER = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?")
EXPECTED_SKILLS = {"backfill", "control", "developer", "dispatcher", "groom", "merger", "modularize", "operator-communication", "overview", "plan", "planner", "plugins", "refactor", "replan", "retro", "reviewer", "setup", "setup-git-workspace", "triage", "work"}
EXPECTED_AGENTS = {"analyst", "controller", "custodian", "developer", "director", "dispatcher", "merger", "planner", "reviewer", "supervisor", "warden"}
QA_ROOTS = {".github", "docs", "qa", "schemas", "scripts", "tests"}
QA_FILES = {".gitignore", ".markdownlint-cli2.jsonc", "justfile", "pyproject.toml", "uv.lock"}


class Invalid(ValueError):
    """A candidate or promotion contract violation."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise Invalid(message)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Invalid(f"cannot read JSON document: {path}") from exc
    require(isinstance(value, dict), f"JSON document must be an object: {path}")
    return value


def safe_path(value: str) -> PurePosixPath:
    require(isinstance(value, str) and value and "\\" not in value and "\x00" not in value, "unsafe candidate path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.as_posix() == value, "unsafe candidate path")
    require(all(part.lower() not in {"", ".", "..", ".git", ".hitch", ".beads", ".venv", "__pycache__"} for part in value.split("/")), "unsafe/private candidate path")
    require(not any(ord(char) < 32 or char == ":" for char in value), "unsafe candidate path")
    return path


def schema_document(document: dict[str, Any], kind: str, qa_root: Path) -> None:
    path = qa_root / "schemas" / f"hitch.release-{kind}.v1.schema.json"
    require(path.is_file() and not path.is_symlink(), f"public Hitch schema is missing: {kind}")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SCHEMA_HASHES[kind], f"public Hitch {kind} schema differs from pinned Hitch revision")
    schema = read_json(path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(document), key=lambda error: list(map(str, error.path)))
    if errors:
        first = errors[0]
        where = "/".join(map(str, first.path)) or "document"
        raise Invalid(f"Hitch {kind} schema violation at {where}: {first.message}")


def validate_candidate(doc: dict[str, Any], pin: str, qa_root: Path) -> None:
    schema_document(doc, "candidate", qa_root)
    unsigned = {key: value for key, value in doc.items() if key != "digest"}
    require(digest(unsigned) == doc["digest"], "candidate document digest mismatch")
    require(re.fullmatch(r"[0-9a-f]{64}", pin) is not None and doc["digest"] == pin, "candidate differs from independently approved digest")
    require(doc["pack"] == "beadhive" and doc["target"] == "claude-code", "candidate pack/target identity mismatch")
    require(all(SEMVER.fullmatch(doc[key]) for key in ("authoredVersion", "releaseVersion")), "candidate versions must be SemVer 2")
    require(re.fullmatch(r"[0-9a-f]{40}", doc["sourceCommit"]) is not None, "candidate sourceCommit must be a full Git SHA")
    require(re.fullmatch(r"[0-9a-f]{40}", doc["hitchRevision"]) is not None, "candidate hitchRevision must be a full Git SHA")
    files = doc["files"]
    require(isinstance(files, dict) and bool(files), "candidate file inventory must be nonempty")
    for name, entry in files.items():
        safe_path(name)
        require(isinstance(entry, dict) and set(entry) == {"sha256", "mode"}, f"invalid candidate file entry: {name}")
        require(isinstance(entry["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is not None, f"invalid file SHA-256: {name}")
        require(entry["mode"] in {"100644", "100755"}, f"unsupported file mode: {name}")
    require(digest(files) == doc["payloadDigest"], "candidate payloadDigest mismatch")


def inventory(root: Path, *, exclude: set[str] | None = None) -> dict[str, dict[str, str]]:
    require(root.is_dir() and not root.is_symlink() and root.absolute() == root.resolve(), "artifact root must be a real, non-traversing directory")
    excluded = exclude or set()
    result: dict[str, dict[str, str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] == ".git":
            require((root / ".git").is_dir() and not (root / ".git").is_symlink(), "unexpected Git metadata entry")
            continue
        require(not path.is_symlink(), "artifact contains a symlink")
        if path.is_dir():
            continue
        require(path.is_file(), "artifact contains a non-regular entry")
        name = path.relative_to(root).as_posix()
        if name in excluded:
            continue
        safe_path(name)
        executable = bool(path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        mode = "100755" if executable else "100644"
        permissions = stat.S_IMODE(path.stat().st_mode) & 0o777
        require(permissions & 0o444 == 0o444 and permissions & 0o111 in ({0o111} if executable else {0}), f"unsupported filesystem mode: {name}")
        result[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "mode": mode}
    return result


def generated_inventory(root: Path) -> dict[str, dict[str, str]]:
    require(root.absolute() == root.resolve(), "generated payload root has a symlinked parent")
    result: dict[str, dict[str, str]] = {}
    paths = [root / ".claude-plugin", root / "beadhive", root / "LICENSE"]
    for scope in paths:
        if scope.name == "LICENSE":
            if not scope.exists():
                continue
            candidates = [scope]
        else:
            require(scope.is_dir() and not scope.is_symlink(), f"generated payload scope is missing/unsafe: {scope.name}")
            candidates = sorted(scope.rglob("*"))
        for path in candidates:
            require(not path.is_symlink(), "generated payload contains a symlink")
            if path.is_dir():
                continue
            require(path.is_file(), "generated payload contains a non-regular entry")
            name = path.relative_to(root).as_posix()
            safe_path(name)
            permissions = stat.S_IMODE(path.stat().st_mode) & 0o777
            executable = bool(permissions & 0o111)
            require(permissions & 0o444 == 0o444 and permissions & 0o111 in ({0o111} if executable else {0}), f"unsupported generated file mode: {name}")
            result[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "mode": "100755" if executable else "100644"}
    require("LICENSE" in result, "generated payload root LICENSE is missing")
    return result


def validate_committed_payload(root: Path, qa_root: Path) -> bool:
    sidecar = root / "release-receipt.json"
    if not sidecar.exists():
        return False
    require(sidecar.is_file() and not sidecar.is_symlink(), "generated payload sidecar is unsafe")
    candidate_doc = read_json(sidecar)
    validate_candidate(candidate_doc, candidate_doc.get("digest", ""), qa_root)
    actual = generated_inventory(root)
    require(actual == candidate_doc["files"], "generated payload differs from its committed payload-only sidecar")
    return True


class UniqueYamlLoader(yaml.SafeLoader):
    pass


def _unique_yaml(loader: UniqueYamlLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        require(key not in result, f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueYamlLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_yaml)


def frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    require(text.startswith("---\n") and "\n---\n" in text[4:], f"missing frontmatter: {path.name}")
    try:
        value = yaml.load(text.split("---", 2)[1], Loader=UniqueYamlLoader)
    except (yaml.YAMLError, ValueError, TypeError) as exc:
        raise Invalid(f"invalid/duplicate YAML frontmatter: {path.name}") from exc
    require(isinstance(value, dict), f"frontmatter must be a mapping: {path.name}")
    return value


def validate_markdown_links(root: Path, files: dict[str, Any]) -> None:
    pattern = re.compile(r"\[[^\]]*\]\(([^\s)]+)(?:\s+\"[^\"\n]*\")?\)")
    for name in files:
        if not name.lower().endswith(".md"):
            continue
        for target in pattern.findall((root / name).read_text(encoding="utf-8")):
            if target.startswith(("https://", "http://", "mailto:")) or target.startswith("#"):
                continue
            require(not target.startswith("/"), f"absolute Markdown reference is forbidden: {name}")
            local = unquote(target.split("#", 1)[0].split("?", 1)[0]).strip("<>")
            if not local:
                continue
            resolved = (root / name).parent.joinpath(local).resolve()
            require(resolved.is_relative_to(root.resolve()) and resolved.is_file(), f"missing or escaping Markdown reference: {name}")


def _marker(text: str, name: str) -> str:
    start, end = f"<!-- {name}:start -->", f"<!-- {name}:end -->"
    require(text.count(start) == 1 and text.count(end) == 1, f"operator marker missing or repeated: {name}")
    return text.split(start, 1)[1].split(end, 1)[0].strip()


def validate_frontmatter_and_operator(artifact: Path, payload_files: dict[str, Any]) -> None:
    skills_root = artifact / "beadhive/skills"
    agents_root = artifact / "beadhive/agents"
    skills = {path.parent.name for path in skills_root.glob("*/SKILL.md")}
    agents = {path.stem for path in agents_root.glob("*.md")}
    require(skills == EXPECTED_SKILLS, "canonical generated skill roster drift")
    require(agents == EXPECTED_AGENTS, "canonical generated agent roster drift")
    for path in skills_root.glob("*/SKILL.md"):
        data = frontmatter(path)
        require(data.get("name") == path.parent.name, f"skill frontmatter name mismatch: {path.name}")
        require(isinstance(data.get("description"), str) and 0 < len(data["description"]) <= 1024, f"invalid skill description: {path.name}")
        require(set(data) <= {"name", "description", "license", "compatibility", "allowed-tools", "metadata"}, f"unsupported skill frontmatter field: {path.name}")
        for key in ("license", "compatibility", "allowed-tools"):
            require(key not in data or isinstance(data[key], str), f"invalid skill {key}: {path.name}")
        if "metadata" in data:
            def metadata_value(value: Any) -> bool:
                if isinstance(value, (str, int, float, bool)):
                    return True
                if isinstance(value, list):
                    return all(metadata_value(item) for item in value)
                if isinstance(value, dict):
                    return all(isinstance(key, str) and metadata_value(item) for key, item in value.items())
                return False
            require(isinstance(data["metadata"], dict) and metadata_value(data["metadata"]), f"invalid skill metadata: {path.name}")
    for path in agents_root.glob("*.md"):
        data = frontmatter(path)
        require(isinstance(data.get("description"), str) and bool(data["description"].strip()), f"agent description missing: {path.name}")
        require(data.get("name") == path.stem, f"agent frontmatter name mismatch: {path.name}")
        require(set(data) <= {"name", "description", "mode", "model", "permission_json", "tools", "skills"}, f"unsupported agent frontmatter field: {path.name}")
        require(data.get("mode") in {"all", "primary", "subagent"}, f"agent mode mismatch: {path.name}")
        require(isinstance(data.get("model"), str) and bool(data["model"].strip()), f"agent model missing: {path.name}")
        require(isinstance(data.get("permission_json"), dict) and all(isinstance(key, str) and isinstance(value, str) for key, value in data["permission_json"].items()), f"agent permissions malformed: {path.name}")
        require(isinstance(data.get("tools"), str) and bool(data["tools"].strip()), f"agent tools missing: {path.name}")
        require("skills" not in data or (isinstance(data["skills"], str) and bool(data["skills"].strip())), f"agent skills malformed: {path.name}")
    instructions = artifact / "beadhive/instructions/OPERATOR-COMMUNICATION.md"
    reference = artifact / "beadhive/skills/operator-communication/references/OPERATOR-COMMUNICATION.md"
    require(instructions.is_file() and reference.is_file() and instructions.read_bytes() == reference.read_bytes(), "operator contract differs from its exact skill reference")
    contract = instructions.read_text(encoding="utf-8")
    skill_contract = (skills_root / "operator-communication/SKILL.md").read_text(encoding="utf-8")
    require("Always-on rules" in contract and "Load `bh:operator-communication`" in contract, "operator contract content is incomplete")
    require("## Decision ask" in skill_contract and "## Status summary" in skill_contract and "AskUserQuestion" in skill_contract and "Worked lifecycle example" in skill_contract, "operator skill contract content is incomplete")
    brief = artifact / "beadhive/output-styles/beadhive-operator-brief.md"
    verbose = artifact / "beadhive/output-styles/beadhive-operator-brief-verbose.md"
    for style, expected_name, motivation in ((brief, "Beadhive Operator Brief (Concise, Recommended)", "concise-motivation"), (verbose, "Beadhive Operator Brief (Verbose Motivation)", "verbose-motivation")):
        data = frontmatter(style)
        require(data.get("name") == expected_name and isinstance(data.get("description"), str) and data["description"].strip(), f"operator style frontmatter invalid: {style.name}")
        require(data.get("keep-coding-instructions") is True and data.get("force-for-plugin") is False, f"operator style opt-in contract invalid: {style.name}")
        body = style.read_text(encoding="utf-8")
        require("../skills/operator-communication/references/OPERATOR-COMMUNICATION.md" in body, f"operator style link drift: {style.name}")
        require(_marker(contract, "shared-rules") == _marker(body, "shared-rules"), f"shared operator rules differ: {style.name}")
        require(_marker(contract, motivation) == _marker(body, motivation), f"operator motivation differs: {style.name}")
        require("## Decision ask" not in body and "## Status summary" not in body, f"operator template duplication: {style.name}")
    concise = brief.read_text(encoding="utf-8")
    require(_marker(contract, "concise-motivation") == _marker(concise, "concise-motivation"), "concise motivation differs from canonical contract")
    for role in ("control", "dispatcher", "planner", "reviewer"):
        require("bh:operator-communication" in (skills_root / role / "SKILL.md").read_text(encoding="utf-8"), f"operator skill wiring missing: {role}")
    for role in ("supervisor", "dispatcher", "planner", "reviewer"):
        text = (agents_root / f"{role}.md").read_text(encoding="utf-8")
        require("bh:operator-communication" in text and "AskUserQuestion" in text, f"operator agent wiring missing: {role}")


def validate_public_contract(artifact: Path, payload: dict[str, Any], qa_root: Path) -> None:
    files = payload["files"]
    for required in (".claude-plugin/marketplace.json", "beadhive/.claude-plugin/plugin.json", "beadhive/hooks/hooks.json", "beadhive/.mcp.json", "beadhive/instructions/OPERATOR-COMMUNICATION.md", "beadhive/skills/operator-communication/references/OPERATOR-COMMUNICATION.md"):
        require(required in files, f"payload missing public contract file: {required}")
    marketplace = read_json(artifact / ".claude-plugin/marketplace.json")
    baseline = read_json(qa_root / "qa/marketplace-baseline.json")
    require(marketplace.get("name") == "beadhive", "marketplace identity must remain beadhive")
    normalized = json.loads(json.dumps(marketplace))
    entries = [row for row in normalized.get("plugins", []) if row.get("name") == "bh"]
    require(len(entries) == 1 and entries[0].get("source") == "./beadhive", "marketplace plugin identity/source mismatch")
    marketplace_version = entries[0].get("version")
    entries[0]["version"] = baseline["plugins"][0]["version"]
    require(normalized == baseline, "marketplace metadata changed outside approved bh version")
    version = payload["releaseVersion"]
    require(marketplace_version == version, "marketplace plugin version does not match payload candidate")
    plugin = read_json(artifact / "beadhive/.claude-plugin/plugin.json")
    require(plugin.get("name") == "bh" and plugin.get("version") == version, "plugin manifest identity/version mismatch")
    hooks = read_json(artifact / "beadhive/hooks/hooks.json")
    require(isinstance(hooks.get("hooks"), dict) and hooks["hooks"], "hooks manifest is empty or malformed")
    commands = []
    for groups in hooks["hooks"].values():
        require(isinstance(groups, list), "hook groups must be arrays")
        for group in groups:
            require(isinstance(group, dict) and isinstance(group.get("hooks"), list), "hook group is malformed")
            for hook in group["hooks"]:
                require(isinstance(hook, dict) and hook.get("type") == "command", "unsupported hook entry")
                require(type(hook.get("timeout")) is int and hook["timeout"] > 0, "hook timeout must be a positive integer")
                command = hook.get("command")
                require(isinstance(command, str) and command.startswith("${CLAUDE_PLUGIN_ROOT}/"), "hook command escapes plugin root")
                rel = safe_path(command.removeprefix("${CLAUDE_PLUGIN_ROOT}/"))
                target = artifact / "beadhive" / rel
                require(target.is_file() and not target.is_symlink() and bool(target.stat().st_mode & 0o111), f"hook target missing/non-executable: {rel}")
                commands.append(command)
    require(bool(commands), "no command hooks are defined")
    mcp = read_json(artifact / "beadhive/.mcp.json")
    servers = mcp.get("mcpServers")
    require(set(mcp) == {"mcpServers"} and isinstance(servers, dict) and set(servers) == {"bh"} and isinstance(servers.get("bh"), dict), "native bh MCP descriptor is malformed")
    server = servers["bh"]
    require(set(server) <= {"command", "args"} and server.get("command") == "bh-mcp" and isinstance(server.get("args", []), list) and server.get("args", []) == [], "native bh MCP descriptor mismatch")
    validate_frontmatter_and_operator(artifact, files)
    validate_markdown_links(artifact, files)
    private = re.compile(r"(?:/data/bees/|/tmp/bh-|/home/bees/|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----)")
    for name in files:
        if Path(name).suffix.lower() in {".md", ".json", ".yaml", ".yml", ".sh", ".py", ".txt"}:
            require(not private.search((artifact / name).read_text(encoding="utf-8")), "private operational material in payload")


def read_owned_paths(qa_root: Path) -> list[str]:
    manifest = read_json(qa_root / "qa/destination-owned.json")
    require(set(manifest) == {"purpose", "files"} and isinstance(manifest["purpose"], str), "QA ownership manifest shape is invalid")
    paths = manifest.get("files")
    require(isinstance(paths, list) and len(paths) == len(set(paths)), "QA ownership file list must be unique")
    require("qa/destination-owned.json" in paths, "QA ownership list must include itself")
    for name in paths:
        path = safe_path(name)
        require(path.parts[0] in QA_ROOTS or name in QA_FILES, f"QA ownership path outside approved QA roots: {name}")
        require(not name.startswith(("beadhive/", ".claude-plugin/")) and name != "release-receipt.json", "QA ownership collides with canonical payload")
    return paths


def validate_owned_manifest(artifact: Path, qa_root: Path) -> list[str]:
    trusted = read_owned_paths(qa_root)
    actual = read_owned_paths(artifact)
    require(actual == trusted, "transport QA ownership manifest differs from repository-approved list")
    return trusted


def _validate_candidate_anchors(payload: dict[str, Any], promotion: dict[str, Any]) -> None:
    for key in ("schemaVersion", "pack", "authoredVersion", "releaseVersion", "target", "sourceCommit", "hitchRevision"):
        require(promotion[key] == payload[key], f"publisher candidate {key} differs from payload candidate")


def validate_producer_closure(artifact: Path, payload: dict[str, Any], promotion: dict[str, Any]) -> None:
    _validate_candidate_anchors(payload, promotion)
    actual = inventory(artifact)
    require("release-receipt.json" in actual and read_json(artifact / "release-receipt.json") == payload, "payload sidecar does not equal payload candidate")
    payload_actual = {name: value for name, value in actual.items() if name != "release-receipt.json"}
    require(payload_actual == payload["files"], "producer payload inventory/bytes/modes differ from payload-only candidate")
    expected = dict(payload["files"])
    expected["release-receipt.json"] = actual["release-receipt.json"]
    require(expected == promotion["files"], "producer publisher candidate is not exactly payload plus the payload sidecar")


def validate_transport_closure(artifact: Path, payload: dict[str, Any], promotion: dict[str, Any], qa_root: Path) -> None:
    _validate_candidate_anchors(payload, promotion)
    actual = inventory(artifact)
    qa_paths = validate_owned_manifest(artifact, qa_root)
    require(not (set(payload["files"]) & (set(qa_paths) | {"release-receipt.json"})), "QA/sidecar path collides with payload candidate")
    require("release-receipt.json" in actual and read_json(artifact / "release-receipt.json") == payload, "payload sidecar does not equal payload candidate")
    payload_actual = {name: value for name, value in actual.items() if name not in set(qa_paths) | {"release-receipt.json"}}
    require(payload_actual == payload["files"], "payload inventory/bytes/modes differ from payload-only candidate")
    expected_promotion = dict(payload["files"])
    expected_promotion["release-receipt.json"] = actual["release-receipt.json"]
    expected_promotion.update({name: actual[name] for name in qa_paths if name in actual})
    require(set(qa_paths) <= set(actual), "destination-owned QA file missing from transport")
    require(expected_promotion == promotion["files"], "publisher candidate is not the exact payload + sidecar + approved QA closure")
    require(actual == promotion["files"], "transport artifact differs from complete publisher candidate inventory")


def validate_transport(artifact: Path, payload_path: Path, promotion_path: Path, payload_pin: str, promotion_pin: str, qa_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = read_json(payload_path)
    promotion = read_json(promotion_path)
    validate_candidate(payload, payload_pin, qa_root)
    validate_candidate(promotion, promotion_pin, qa_root)
    validate_transport_closure(artifact, payload, promotion, qa_root)
    validate_public_contract(artifact, payload, qa_root)
    return payload, promotion


def validate_producer(artifact: Path, payload_path: Path, promotion_path: Path, payload_pin: str, promotion_pin: str, qa_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate the producer's payload-only and pre-QA publisher candidates."""
    payload = read_json(payload_path)
    promotion = read_json(promotion_path)
    validate_candidate(payload, payload_pin, qa_root)
    validate_candidate(promotion, promotion_pin, qa_root)
    validate_producer_closure(artifact, payload, promotion)
    validate_public_contract(artifact, payload, qa_root)
    return payload, promotion


def validate_receipt(receipt: dict[str, Any], promotion: dict[str, Any], expected_receipt_digest: str, mode: str, qa_root: Path) -> None:
    schema_document(receipt, "receipt", qa_root)
    require(digest({key: value for key, value in receipt.items() if key != "digest"}) == receipt["digest"], "Hitch promotion receipt digest mismatch")
    require(re.fullmatch(r"[0-9a-f]{64}", expected_receipt_digest) is not None and receipt["digest"] == expected_receipt_digest, "promotion receipt differs from independent pin")
    for key, source in (("candidateDigest", "digest"), ("payloadDigest", "payloadDigest"), ("sourceCommit", "sourceCommit"), ("hitchRevision", "hitchRevision"), ("authoredVersion", "authoredVersion"), ("releaseVersion", "releaseVersion")):
        require(receipt[key] == promotion[source], f"promotion receipt {key} does not bind complete publisher candidate")
    require(receipt["filesVerified"] == len(promotion["files"]), "promotion receipt file count mismatch")
    dest = receipt["destination"]
    require(dest["identity"] in {"https://github.com/beadhive/claude-plugin", "https://github.com/beadhive/claude-plugin.git", "git@github.com:beadhive/claude-plugin.git"}, "promotion receipt destination identity mismatch")
    require(dest["layout"] == "root" and dest["path"] == "" and dest["baseBranch"] == "main", "promotion receipt destination layout mismatch")
    require(receipt["branch"] == dest["branch"], "promotion receipt branch mismatch")
    if mode == "local":
        require(receipt["pushed"] is False and receipt["remoteVerified"] is False and receipt["prUrl"] is None, "local promotion receipt incorrectly claims remote publication")
    elif mode == "remote":
        require(receipt["pushed"] is True and receipt["remoteVerified"] is True, "remote promotion receipt lacks verified push")
        if receipt["prUrl"] is not None:
            require(receipt["prUrl"].startswith("https://github.com/beadhive/claude-plugin/pull/"), "remote receipt PR URL destination mismatch")


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    require(result.returncode == 0, "Git destination verification failed")
    return result.stdout


def validate_promotion(receipt: dict[str, Any], promotion: dict[str, Any], plan: dict[str, Any], repo: Path) -> None:
    root = Path(git(repo, "rev-parse", "--show-toplevel").strip())
    require(root.resolve() == repo.resolve(), "destination must be the repository root")
    head = git(repo, "rev-parse", "HEAD").strip()
    require(head == receipt["destinationCommit"], "destination HEAD differs from promotion receipt")
    status = git(repo, "status", "--porcelain=v1", "--untracked-files=all").strip()
    require(not status, "destination has post-promotion worktree edits")
    require(digest({key: value for key, value in plan.items() if key != "digest"}) == plan["digest"], "Hitch promotion plan digest mismatch")
    require(plan["candidateDigest"] == promotion["digest"] and plan["payloadDigest"] == promotion["payloadDigest"] and receipt["planDigest"] == plan["digest"], "promotion plan/receipt candidate linkage mismatch")
    dest = plan["destination"]
    require(dest == receipt["destination"], "promotion receipt destination differs from reviewed plan")
    require(dest["layout"] == "root" and dest["path"] == "" and dest["identity"] in {"https://github.com/beadhive/claude-plugin", "https://github.com/beadhive/claude-plugin.git", "git@github.com:beadhive/claude-plugin.git"}, "promotion plan destination mismatch")
    for name in plan["ownedPaths"] + plan["copies"] + plan["deletions"]:
        safe_path(name[:-1] if name.endswith("/") else name)
    parent = git(repo, "rev-list", "--parents", "-n", "1", head).split()
    require(parent == [head, dest["expectedBase"]], "promotion commit must have exactly the reviewed base as its parent")
    expected_copies = sorted(promotion["files"])
    require(sorted(plan["copies"]) == expected_copies, "promotion plan copies differ from complete publisher inventory")
    entries: dict[str, tuple[str, str]] = {}
    raw = subprocess.run(["git", "-C", str(repo), "ls-tree", "-rz", "--full-tree", "-r", head], capture_output=True)
    require(raw.returncode == 0, "cannot read destination Git tree")
    for row in raw.stdout.decode().split("\0"):
        if row:
            metadata, name = row.split("\t", 1)
            mode, kind, oid = metadata.split()
            entries[name] = (mode, kind, oid)
    scopes = plan["ownedPaths"]
    owned = {name: entry for name, entry in entries.items()
             if any(name.startswith(scope) if scope.endswith("/") else name == scope for scope in scopes)}
    require(all(entry[1] == "blob" and entry[0] in {"100644", "100755"} for entry in owned.values()), "destination owned paths contain non-regular Git entries")
    owned_files = {}
    prefix = dest["path"] + "/" if dest["path"] else ""
    for name, (mode, _kind, oid) in owned.items():
        require(name.startswith(prefix), "owned destination path escapes configured layout")
        result = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", oid], capture_output=True)
        require(result.returncode == 0, f"cannot read destination Git blob: {name}")
        owned_files[name[len(prefix):]] = {"sha256": hashlib.sha256(result.stdout).hexdigest(), "mode": mode}
    require(owned_files == promotion["files"], "destination owned Git tree differs from complete publisher inventory")
    base_raw = subprocess.run(["git", "-C", str(repo), "ls-tree", "-rz", "--full-tree", "-r", dest["expectedBase"]], capture_output=True)
    require(base_raw.returncode == 0, "cannot read reviewed base Git tree")
    base_paths = set()
    for row in base_raw.stdout.decode().split("\0"):
        if row:
            _metadata, name = row.split("\t", 1)
            if any(name.startswith(scope) if scope.endswith("/") else name == scope for scope in scopes):
                require(name.startswith(prefix), "owned base path escapes configured layout")
                base_paths.add(name[len(prefix):])
    expected_deletions = base_paths - set(plan["copies"])
    require(set(plan["deletions"]) == expected_deletions, "promotion plan deletions do not exactly remove stale owned files")
    changed = set(git(repo, "diff", "--name-only", "-z", dest["expectedBase"], head).split("\0")) - {""}
    require(changed <= set(plan["copies"]) | set(plan["deletions"]), "promotion commit changed paths outside reviewed copies/deletions")
    for name, item in promotion["files"].items():
        require(name in entries and entries[name][0] == item["mode"] and entries[name][1] == "blob", f"destination file/mode mismatch: {name}")


def extract_payload_archive(archive: Path, dest: Path) -> None:
    total = 0
    seen: set[str] = set()
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            name = member.name.rstrip("/")
            if not name:
                continue
            safe_path(name)
            require(name not in seen, "candidate archive has duplicate paths")
            seen.add(name)
            path = dest / name
            require(path.resolve().is_relative_to(dest.resolve()), "candidate archive escapes extraction root")
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            require(member.isfile(), "candidate archive contains a link or special file")
            require(member.mode & 0o777 in {0o644, 0o755}, "candidate archive file mode is unsupported")
            total += member.size
            require(total <= 128 * 1024 * 1024 and member.size <= 16 * 1024 * 1024, "candidate archive exceeds size limit")
            path.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            require(source is not None, "candidate archive file cannot be read")
            with path.open("xb") as output:
                shutil.copyfileobj(source, output)
            path.chmod(member.mode & 0o777)


def build_artifact_from_archive(archive: Path, qa_root: Path, work: Path, *, overlay_qa: bool = True) -> Path:
    artifact = work / "artifact"
    artifact.mkdir()
    extract_payload_archive(archive, artifact)
    for name in read_owned_paths(qa_root) if overlay_qa else []:
        src = qa_root / name
        require(src.is_file() and not src.is_symlink(), f"destination-owned QA source missing/unsafe: {name}")
        dst = artifact / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        dst.chmod(0o755 if src.stat().st_mode & 0o111 else 0o644)
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, help="assembled candidate artifact used by the paired promotion caller")
    parser.add_argument("--producer-stage", action="store_true", help="validate the producer's pre-QA payload and publisher base closure")
    parser.add_argument("--payload-archive", type=Path, help="public unauthenticated Hitch payload tar.gz; QA overlay is copied from --qa-root")
    parser.add_argument("--qa-root", type=Path, default=ROOT)
    parser.add_argument("--check-committed-payload", action="store_true", help="compare committed generated scopes to their root release-receipt.json sidecar")
    parser.add_argument("--payload-candidate", type=Path)
    parser.add_argument("--expected-payload-candidate-digest")
    parser.add_argument("--promotion-candidate", type=Path)
    parser.add_argument("--expected-promotion-candidate-digest")
    parser.add_argument("--receipt", type=Path, help="optional Hitch promotion receipt; paired precommit QA supplies a not-yet-created path")
    parser.add_argument("--expected-receipt-digest")
    parser.add_argument("--receipt-mode", choices=("local", "remote"))
    parser.add_argument("--promotion-plan", type=Path)
    parser.add_argument("--expected-plan-digest")
    parser.add_argument("--destination-repo", type=Path)
    args = parser.parse_args()
    try:
        qa_root = args.qa_root.absolute()
        require(qa_root == qa_root.resolve(), "QA root has a symlinked parent")
        if args.check_committed_payload:
            root = args.artifact or Path.cwd()
            root = root.absolute()
            present = validate_committed_payload(root, qa_root)
            print(json.dumps({"status": "committed-payload-consistent" if present else "no-committed-generated-payload", "independentPin": False}, sort_keys=True))
            return 0
        require(all((args.payload_candidate, args.expected_payload_candidate_digest, args.promotion_candidate, args.expected_promotion_candidate_digest)), "payload and publisher candidate documents plus independent pins are required")
        require(not args.producer_stage or (args.receipt_mode is None and args.expected_receipt_digest is None and args.promotion_plan is None and args.destination_repo is None), "producer-stage validation cannot verify promotion receipts")
        with tempfile.TemporaryDirectory(prefix="claude-candidate-") as temp:
            work = Path(temp)
            if args.payload_archive:
                require(args.artifact is None, "choose artifact directory or public payload archive")
                artifact = build_artifact_from_archive(args.payload_archive, qa_root, work, overlay_qa=not args.producer_stage)
            else:
                require(args.artifact is not None, "candidate artifact directory is required")
                artifact = args.artifact.absolute()
                require(artifact == artifact.resolve(), "artifact root has a symlinked parent")
            if args.producer_stage:
                payload, promotion = validate_producer(artifact, args.payload_candidate, args.promotion_candidate, args.expected_payload_candidate_digest, args.expected_promotion_candidate_digest, qa_root)
            else:
                payload, promotion = validate_transport(artifact, args.payload_candidate, args.promotion_candidate, args.expected_payload_candidate_digest, args.expected_promotion_candidate_digest, qa_root)
            result = {"status": "producer-candidate-verified" if args.producer_stage else "transport-verified", "payloadCandidateDigest": payload["digest"], "promotionCandidateDigest": promotion["digest"], "payloadFiles": len(payload["files"]), "qaFiles": 0 if args.producer_stage else len(read_owned_paths(artifact)), "sourceCommit": payload["sourceCommit"], "hitchRevision": payload["hitchRevision"], "releaseVersion": payload["releaseVersion"]}
            if args.receipt is not None and args.receipt.exists():
                require(args.receipt_mode is not None and args.expected_receipt_digest is not None, "promotion receipt requires independent digest and local/remote mode")
                require(args.promotion_plan is not None and args.expected_plan_digest is not None and args.destination_repo is not None, "promotion receipt requires independently pinned plan and destination checkout")
                receipt, plan = read_json(args.receipt), read_json(args.promotion_plan)
                schema_document(plan, "plan", qa_root)
                require(plan["digest"] == args.expected_plan_digest, "promotion plan differs from independent pin")
                validate_receipt(receipt, promotion, args.expected_receipt_digest, args.receipt_mode, qa_root)
                destination_repo = args.destination_repo.absolute()
                require(destination_repo == destination_repo.resolve(), "destination repository path has a symlinked parent")
                validate_promotion(receipt, promotion, plan, destination_repo)
                result.update(status=f"{args.receipt_mode}-promotion-verified", receiptDigest=receipt["digest"], destinationCommit=receipt["destinationCommit"])
            elif args.receipt_mode is not None:
                raise Invalid("receipt mode supplied without an allocated Hitch promotion receipt")
            print(json.dumps(result, sort_keys=True))
    except (Invalid, OSError, tarfile.TarError, yaml.YAMLError) as exc:
        print(f"Claude release QA failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
