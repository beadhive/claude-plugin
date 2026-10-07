#!/usr/bin/env python3
"""Fail-closed validation of a Hitch v1 candidate against this public checkout.

The expected candidate digest is an independent release gate input. A candidate's
self-reported digest alone does not authorize its payload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote

from jsonschema import Draft202012Validator
import yaml


class Invalid(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Invalid(message)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Invalid(f"cannot read JSON document: {path}") from exc
    require(isinstance(value, dict), f"document must be an object: {path}")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise Invalid(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def validate_schema(document: dict[str, Any], kind: str) -> None:
    schema_path = Path(__file__).resolve().parent.parent / "schemas" / f"hitch.release-{kind}.v1.schema.json"
    schema = read_json(schema_path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(document), key=lambda error: list(map(str, error.path)))
    if errors:
        first = errors[0]
        location = "/".join(map(str, first.path)) or "document"
        raise Invalid(f"Hitch {kind} v1 schema violation at {location}: {first.message}")


def safe_relative(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    private = {".git", ".hitch", ".beads", ".venv", "__pycache__"}
    require(bool(name) and not path.is_absolute() and "\\" not in name, "unsafe candidate path")
    require(all(part not in {"", ".", ".."} and part.lower() not in private for part in name.split("/")), "unsafe/private candidate path")
    require(not any(ord(char) < 32 or char == ":" for char in name), "unsafe candidate path")
    return path


def validate_seal(document: dict[str, Any], kind: str) -> None:
    require(document.get("schemaVersion") == 1, f"unsupported Hitch {kind} schemaVersion")
    seal = document.get("digest")
    unsigned = {key: value for key, value in document.items() if key != "digest"}
    require(isinstance(seal, str) and re.fullmatch(r"[0-9a-f]{64}", seal), f"invalid {kind} digest")
    require(digest(unsigned) == seal, f"{kind} document digest mismatch")


def validate_candidate(candidate: dict[str, Any], expected_digest: str) -> None:
    validate_schema(candidate, "candidate")
    validate_seal(candidate, "candidate")
    require(candidate["pack"] == "beadhive" and candidate["target"] == "claude-code", "candidate pack/target identity mismatch")
    require(re.fullmatch(r"[0-9a-f]{40}", candidate["sourceCommit"] or "") is not None, "candidate sourceCommit must be a full Git SHA")
    require(re.fullmatch(r"[0-9a-f]{40}", candidate["hitchRevision"] or "") is not None, "candidate hitchRevision must be a full Git SHA")
    require(isinstance(candidate["releaseVersion"], str) and candidate["releaseVersion"], "candidate releaseVersion is required")
    require(isinstance(candidate["authoredVersion"], str) and candidate["authoredVersion"], "candidate authoredVersion is required")
    semver = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?")
    require(semver.fullmatch(candidate["authoredVersion"]) is not None and semver.fullmatch(candidate["releaseVersion"]) is not None, "candidate versions must be SemVer 2.0.0")
    files = candidate["files"]
    require(isinstance(files, dict) and bool(files), "candidate files inventory must be nonempty")
    for name, entry in files.items():
        safe_relative(name)
        require(isinstance(entry, dict) and set(entry) == {"sha256", "mode"}, f"invalid inventory entry: {name}")
        require(re.fullmatch(r"[0-9a-f]{64}", str(entry["sha256"])) is not None, f"invalid SHA-256: {name}")
        require(entry["mode"] in {"100644", "100755"}, f"invalid file mode: {name}")
    require(digest(files) == candidate["payloadDigest"], "candidate payloadDigest mismatch")
    require(re.fullmatch(r"[0-9a-f]{64}", expected_digest) is not None, "an independently approved candidate digest is required")
    require(candidate["digest"] == expected_digest, "candidate differs from independently approved digest")


def inventory(root: Path) -> dict[str, dict[str, str]]:
    require(root.is_dir() and not root.is_symlink() and root.resolve() == root.absolute(), "artifact root must be a real, non-traversing directory")
    actual: dict[str, dict[str, str]] = {}
    for path in root.rglob("*"):
        require(not path.is_symlink(), "artifact contains a symlink")
        if path.is_dir():
            continue
        require(path.is_file(), "artifact contains a non-regular entry")
        name = path.relative_to(root).as_posix()
        safe_relative(name)
        mode = "100755" if path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH) else "100644"
        actual[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "mode": mode}
    return actual


class UniqueYamlLoader(yaml.SafeLoader):
    pass


def unique_yaml_mapping(loader: UniqueYamlLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        require(key not in result, f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueYamlLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_yaml_mapping)


def validate_frontmatter(artifact: Path, files: dict[str, Any]) -> None:
    for name in files:
        path = PurePosixPath(name)
        if path.suffix.lower() == ".md":
            text = (artifact / name).read_text(encoding="utf-8")
            for target in re.findall(r"\]\(([^)]+)\)", text):
                target = target.strip().split()[0].strip("<>") if target.strip() else ""
                if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                    continue
                require(not target.startswith("/"), f"absolute local Markdown reference is forbidden: {name}: {target}")
                local = unquote(target.split("#", 1)[0].split("?", 1)[0])
                if not local:
                    continue
                resolved = (artifact / name).parent.joinpath(local).resolve()
                require(resolved.is_relative_to(artifact.resolve()), f"Markdown reference escapes candidate root: {name}")
                require(resolved.is_file(), f"unresolved shipped Markdown reference in {name}: {target}")
        is_skill = len(path.parts) == 4 and path.parts[:2] == ("beadhive", "skills") and path.name == "SKILL.md"
        is_agent = len(path.parts) == 3 and path.parts[:2] == ("beadhive", "agents") and path.suffix == ".md"
        if not (is_skill or is_agent):
            continue
        text = (artifact / name).read_text(encoding="utf-8")
        require(text.startswith("---\n") and "\n---" in text[4:], f"missing Claude frontmatter: {name}")
        try:
            header = yaml.load(text.split("---", 2)[1], Loader=UniqueYamlLoader)
        except (yaml.YAMLError, ValueError, TypeError) as exc:
            raise Invalid(f"invalid or duplicate Claude frontmatter: {name}") from exc
        require(isinstance(header, dict), f"Claude frontmatter must be a mapping: {name}")
        description = header.get("description")
        require(isinstance(description, str) and bool(description.strip()), f"frontmatter description required: {name}")
        if is_skill:
            skill_name = path.parts[2]
            require(header.get("name") == skill_name and len(skill_name) <= 64, f"skill frontmatter name mismatch: {name}")
            require(len(description) <= 1024, f"skill description too long: {name}")


def public_contract(candidate: dict[str, Any], artifact: Path) -> None:
    files = candidate["files"]
    require(inventory(artifact) == files, "artifact file set, bytes, or executable modes differ from candidate")
    marketplace_path = ".claude-plugin/marketplace.json"
    plugin_path = "beadhive/.claude-plugin/plugin.json"
    hooks_path = "beadhive/hooks/hooks.json"
    mcp_path = "beadhive/.mcp.json"
    operator_path = "beadhive/OPERATOR-COMMUNICATION.md"
    for name in (marketplace_path, plugin_path, hooks_path, mcp_path, operator_path):
        require(name in files, f"candidate is missing required public contract file: {name}")
    marketplace = read_json(artifact / marketplace_path)
    plugin = read_json(artifact / plugin_path)
    require(marketplace.get("name") == "beadhive", "marketplace identity must remain beadhive")
    entries = [entry for entry in marketplace.get("plugins", []) if entry.get("name") == "bh"]
    require(len(entries) == 1 and entries[0].get("source") == "./beadhive", "marketplace must expose bh from ./beadhive")
    version = candidate["releaseVersion"]
    require(plugin.get("name") == "bh" and plugin.get("version") == version, "plugin identity/version differs from release candidate")
    require(entries[0].get("version") == version, "marketplace plugin version differs from release candidate")
    hooks = read_json(artifact / hooks_path).get("hooks", {})
    commands: list[str] = []
    for groups in hooks.values():
        require(isinstance(groups, list), "hook event entries must be arrays")
        for group in groups:
            for hook in group.get("hooks", []):
                command = hook.get("command", "")
                require(isinstance(command, str) and command.startswith("${CLAUDE_PLUGIN_ROOT}/"), "hook command must use the plugin root")
                rel = command.removeprefix("${CLAUDE_PLUGIN_ROOT}/")
                safe_relative(rel)
                target = artifact / "beadhive" / rel
                require(target.is_file() and not target.is_symlink(), f"hook target missing or unsafe: {rel}")
                require(bool(target.stat().st_mode & 0o111), f"hook target is not executable: {rel}")
                commands.append(command)
    require(bool(commands), "candidate must declare executable hooks")
    mcp = read_json(artifact / mcp_path).get("mcpServers", {})
    require("bh" in mcp and mcp["bh"].get("command") == "bh-mcp", "bh MCP server contract is missing")
    operator = (artifact / operator_path).read_text(encoding="utf-8")
    for marker in ("# Operator-facing communication contract", "## Always-on rules", "<!-- shared-rules:start -->", "<!-- shared-rules:end -->", "Load `bh:operator-communication`"):
        require(marker in operator, f"operator communication contract is incomplete: {marker}")
    for style in ("beadhive/output-styles/beadhive-operator-brief.md", "beadhive/output-styles/beadhive-operator-brief-verbose.md"):
        require(style in files, f"candidate is missing operator output style: {style}")
        require("bh:operator-communication" in (artifact / style).read_text(encoding="utf-8"), f"operator style does not point to its skill: {style}")
    validate_frontmatter(artifact, files)


def validate_receipt(receipt: dict[str, Any], candidate: dict[str, Any], expected_receipt_digest: str) -> None:
    validate_schema(receipt, "receipt")
    validate_seal(receipt, "receipt")
    require(receipt["digest"] == expected_receipt_digest, "receipt differs from independently approved receipt digest")
    for key in ("candidateDigest", "payloadDigest", "sourceCommit", "hitchRevision", "authoredVersion", "releaseVersion"):
        source_key = "digest" if key == "candidateDigest" else key
        require(receipt[key] == candidate[source_key], f"receipt {key} does not match candidate")
    require(receipt["filesVerified"] == len(candidate["files"]), "receipt file count does not match candidate inventory")
    destination = receipt["destination"]
    identities = {"https://github.com/beadhive/claude-plugin", "https://github.com/beadhive/claude-plugin.git", "git@github.com:beadhive/claude-plugin.git"}
    require(isinstance(destination, dict) and destination.get("identity") in identities, "receipt destination identity is not the public repository")
    require(receipt["branch"] == destination.get("branch"), "receipt branch differs from destination branch")
    require(receipt["pushed"] == receipt["remoteVerified"], "receipt remote verification flags are inconsistent")
    require(receipt["pushed"], "receipt does not prove a pushed promotion")
    if receipt["prUrl"] is not None:
        require(receipt["prUrl"].startswith("https://github.com/beadhive/claude-plugin/pull/"), "receipt PR URL is not for the public destination")


def validate_destination_head(receipt: dict[str, Any], candidate: dict[str, Any], destination_repo: Path) -> None:
    require(destination_repo.is_dir() and not destination_repo.is_symlink(), "destination checkout must be a real directory")
    result = subprocess.run(["git", "-C", str(destination_repo), "rev-parse", "HEAD"], capture_output=True, text=True)
    require(result.returncode == 0 and result.stdout.strip() == receipt["destinationCommit"], "destination checkout HEAD differs from receipt destinationCommit")
    status = subprocess.run(["git", "-C", str(destination_repo), "status", "--porcelain=v1", "--untracked-files=all"], capture_output=True, text=True)
    require(status.returncode == 0 and not status.stdout.strip(), "destination checkout has post-promotion worktree edits")
    destination = receipt["destination"]
    require(destination["layout"] == "root" and destination["path"] == "", "public Claude release must target the repository root")
    prefix = destination["path"] + "/" if destination["path"] else ""
    tree = subprocess.run(["git", "-C", str(destination_repo), "ls-tree", "-rz", "--full-tree", "-r", receipt["destinationCommit"]], capture_output=True)
    require(tree.returncode == 0, "cannot inspect destination Git tree")
    entries: dict[str, dict[str, str]] = {}
    for item in tree.stdout.decode().split("\0"):
        if not item:
            continue
        metadata, name = item.split("\t", 1)
        mode, kind, oid = metadata.split(" ")
        entries[name] = {"mode": mode, "kind": kind, "oid": oid}
    expected = {prefix + name: data for name, data in candidate["files"].items()}
    roots = (prefix + ".claude-plugin/", prefix + "beadhive/")
    actual_owned = {name for name in entries if name.startswith(roots)}
    expected_owned = {name for name in expected if name.startswith(roots)}
    require(actual_owned == expected_owned, "destination payload file set differs from exact candidate inventory")
    for name in sorted(expected):
        require(name in entries, f"destination candidate file is missing: {name}")
        entry = entries[name]
        require(entry["kind"] == "blob" and entry["mode"] == expected[name]["mode"], f"destination payload mode/type drift: {name}")
        blob = subprocess.run(["git", "-C", str(destination_repo), "cat-file", "blob", entry["oid"]], capture_output=True)
        require(blob.returncode == 0 and hashlib.sha256(blob.stdout).hexdigest() == expected[name]["sha256"], f"destination payload bytes drift: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--expected-candidate-digest", required=True)
    parser.add_argument("--expected-receipt-digest", required=True)
    parser.add_argument("--destination-repo", type=Path, required=True)
    args = parser.parse_args()
    try:
        candidate = read_json(args.candidate)
        receipt = read_json(args.receipt)
        validate_candidate(candidate, args.expected_candidate_digest)
        public_contract(candidate, args.artifact)
        validate_receipt(receipt, candidate, args.expected_receipt_digest)
        validate_destination_head(receipt, candidate, args.destination_repo)
    except Invalid as exc:
        print(f"release acceptance failed: {exc}", file=sys.stderr)
        return 1
    print(f"release promotion metadata verified: {candidate['releaseVersion']} {candidate['digest']} ({len(candidate['files'])} files); this does not prove native client installation or loading")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
