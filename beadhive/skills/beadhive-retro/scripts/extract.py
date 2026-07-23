#!/usr/bin/env python3
"""Phase 2: normalize identified session transcripts into events + usage series. No judgment —
pure extraction. See ../references/metrics.md for the fields this feeds.

By default, resolves identify.json/writes extract.jsonl+events.jsonl in the same run-dir as
identify.py: explicit `--run-dir` wins, else the `latest` pointer, else legacy cwd-relative
defaults. `--in`/`--out`/`--events` always override individually.

Usage:
    extract.py [--in identify.json] [--session <path>] [--out extract.jsonl]
                [--events events.jsonl] [--run-dir DIR]
    extract.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import re

import _rundir

# Capture the FULL bd/bh invocation up to the next shell terminator, not just 2 words — a short
# capture silently drops the bead id on commands like `bh work merge bh-cp-1` (3 words after
# bd/bh: work, merge, <id>). Cap the length so a long --description doesn't bloat output.
BD_BH_TOKEN_RE = re.compile(
    r"(?:^|&&|;|\n)\s*((?:bd|bh)\s+(?:(?!&&|;|\||\n).)*)", re.DOTALL
)
# ^ stops at &&, ;, |, or newline (shell chaining) but NOT a lone '&' — a redirect like
# '2>&1' must not truncate the command before a trailing bead id.
BD_BH_DETAIL_MAXLEN = 200
# `bd create` / `bh plan` never carry the new bead's id in the command (it's assigned and
# printed in the tool_result, e.g. "Created issue: bh-cp-1 ..."), so extract.py also scans
# tool_result text for ids and attaches them to the originating Bash event as `resultIds`.
BEAD_ID_RE = re.compile(r"\bbh-[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[0-9]+)?\b")


def bd_bh_detail(command: str):
    m = BD_BH_TOKEN_RE.search(command)
    if not m:
        return None
    return m.group(1).strip()[:BD_BH_DETAIL_MAXLEN]


def tool_detail(name: str, inp: dict):
    if name == "Skill":
        return inp.get("skill")
    if name == "Bash":
        return bd_bh_detail(str(inp.get("command", "")))
    if name in ("Read", "Write", "Edit", "NotebookEdit"):
        return inp.get("file_path")
    return None


def content_chars(content) -> int:
    """Char count of a tool_result content field, which may be a string or a content-block list."""
    if content is None:
        return 0
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict):
                total += len(str(block.get("text", "")))
            else:
                total += len(str(block))
        return total
    return len(str(content))


def content_text(content) -> str:
    """Flatten a tool_result content field to plain text for bead-id scanning."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def extract_session(path: str) -> dict:
    usage_series = []
    tool_events = []  # each: {ts, tool, isSidechain, detail, tool_use_id}
    error_by_id = {}  # tool_use_id -> is_error
    result_ids_by_id = {}  # tool_use_id -> [bead ids found in that tool_result's text]
    read_chars = 0
    write_chars = 0
    session_id = None
    cc_versions = set()

    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            session_id = rec.get("sessionId", session_id)
            ts = rec.get("timestamp")
            is_sidechain = bool(rec.get("isSidechain", False))
            version = rec.get("version")
            if version:
                cc_versions.add(str(version))
            message = rec.get("message")
            if not isinstance(message, dict):
                continue

            usage = message.get("usage")
            if isinstance(usage, dict) and message.get("role") == "assistant":
                cache_creation = usage.get("cache_creation") or {}
                usage_series.append(
                    {
                        "ts": ts,
                        "input": usage.get("input_tokens", 0),
                        "output": usage.get("output_tokens", 0),
                        "cache_read": usage.get("cache_read_input_tokens", 0),
                        "cache_creation": usage.get("cache_creation_input_tokens", 0),
                        "eph5m": cache_creation.get("ephemeral_5m_input_tokens", 0),
                        "eph1h": cache_creation.get("ephemeral_1h_input_tokens", 0),
                        "isSidechain": is_sidechain,
                        "model": message.get("model"),
                    }
                )

            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue

                if block.get("type") == "tool_use":
                    name = block.get("name", "")
                    inp = block.get("input") or {}
                    tool_events.append(
                        {
                            "ts": ts,
                            "tool": name,
                            "isSidechain": is_sidechain,
                            "detail": tool_detail(name, inp),
                            "tool_use_id": block.get("id"),
                        }
                    )
                    if name in ("Write", "Edit"):
                        blob = inp.get("content") or inp.get("new_string") or ""
                        write_chars += len(str(blob))

                elif block.get("type") == "tool_result":
                    tool_use_id = block.get("tool_use_id")
                    is_error = bool(block.get("is_error", False))
                    result_content = block.get("content")
                    if tool_use_id:
                        error_by_id[tool_use_id] = is_error
                        ids = BEAD_ID_RE.findall(content_text(result_content))
                        if ids:
                            result_ids_by_id[tool_use_id] = sorted(set(ids))
                    read_chars += content_chars(result_content)

    for event in tool_events:
        tool_use_id = event["tool_use_id"]
        event["error"] = error_by_id.get(tool_use_id, False)
        event["resultIds"] = result_ids_by_id.get(tool_use_id, [])

    return {
        "sessionId": session_id,
        "path": path,
        "usageSeries": usage_series,
        "toolEvents": tool_events,
        "contentSizes": {"readChars": read_chars, "writeChars": write_chars},
        "ccVersions": sorted(cc_versions),
    }


def run(session_paths: list) -> list:
    return [extract_session(p) for p in session_paths]


def selftest() -> None:
    import os
    import tempfile

    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "sess.jsonl")

    lines = [
        {
            "sessionId": "sess-x",
            "isSidechain": False,
            "timestamp": "2026-07-20T10:00:00Z",
            "version": "2.1.207",
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-5",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 100,
                    "cache_creation_input_tokens": 5,
                    "cache_creation": {"ephemeral_5m_input_tokens": 5, "ephemeral_1h_input_tokens": 0},
                },
                "content": [
                    {"type": "tool_use", "id": "tu1", "name": "Bash", "input": {"command": "bd show bh-cp-1"}},
                    {"type": "tool_use", "id": "tu2", "name": "Write", "input": {"file_path": "/tmp/f.py", "content": "hello world"}},
                    {"type": "tool_use", "id": "tu3", "name": "Bash", "input": {"command": "bh work merge bh-cp-9 2>&1 | tail -5"}},
                    {"type": "tool_use", "id": "tu4", "name": "Bash", "input": {"command": "bd create --title x"}},
                ],
            },
        },
        {
            "sessionId": "sess-x",
            "isSidechain": False,
            "timestamp": "2026-07-20T10:01:00Z",
            "version": "2.1.208",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu1", "is_error": True, "content": "error: not found"},
                    {"type": "tool_result", "tool_use_id": "tu4", "is_error": False, "content": "Created issue: bh-cp-42 — x"},
                ],
            },
        },
    ]
    with open(path, "w") as f:
        for rec in lines:
            f.write(json.dumps(rec) + "\n")

    result = extract_session(path)

    assert result["sessionId"] == "sess-x"
    assert len(result["usageSeries"]) == 1
    u = result["usageSeries"][0]
    assert u["input"] == 10 and u["output"] == 20 and u["cache_read"] == 100 and u["cache_creation"] == 5
    assert u["eph5m"] == 5 and u["eph1h"] == 0
    assert u["model"] == "claude-sonnet-5"

    assert len(result["toolEvents"]) == 4
    bash_event = next(e for e in result["toolEvents"] if e["tool_use_id"] == "tu1")
    assert bash_event["detail"] == "bd show bh-cp-1", bash_event["detail"]
    assert bash_event["error"] is True

    write_event = next(e for e in result["toolEvents"] if e["tool_use_id"] == "tu2")
    assert write_event["detail"] == "/tmp/f.py"
    assert write_event["error"] is False

    # regression: the id must survive on a 3-word-after-bd/bh command (work merge <id>),
    # even with a trailing `2>&1 | tail` redirect/pipe.
    merge_event = next(e for e in result["toolEvents"] if e["tool_use_id"] == "tu3")
    assert "bh-cp-9" in merge_event["detail"], merge_event["detail"]
    assert merge_event["detail"].startswith("bh work merge bh-cp-9"), merge_event["detail"]

    # bd create's id only appears in the tool_result, not the command -> resultIds
    create_event = next(e for e in result["toolEvents"] if e["tool_use_id"] == "tu4")
    assert create_event["detail"] == "bd create --title x", create_event["detail"]
    assert create_event["resultIds"] == ["bh-cp-42"], create_event["resultIds"]
    assert bash_event["resultIds"] == []

    assert result["contentSizes"]["writeChars"] == len("hello world")
    assert result["contentSizes"]["readChars"] == len("error: not found") + len("Created issue: bh-cp-42 — x")

    assert result["ccVersions"] == ["2.1.207", "2.1.208"], result["ccVersions"]

    # run-dir resolution: explicit flags win; else resolved run-dir; else legacy cwd filenames.
    orig_root, orig_latest = _rundir.RETROS_ROOT, _rundir.LATEST_POINTER
    tmpdir = tempfile.mkdtemp()
    _rundir.RETROS_ROOT = os.path.join(tmpdir, "retros")
    _rundir.LATEST_POINTER = os.path.join(_rundir.RETROS_ROOT, "latest")
    try:
        assert resolve_paths(None, None, None, None) == ("identify.json", "extract.jsonl", "events.jsonl")

        run_dir, _ = _rundir.new_run_dir("20260101-000000-deadbeef")
        _rundir.write_latest_pointer(run_dir)
        assert resolve_paths(None, None, None, None) == (
            os.path.join(run_dir, "identify.json"),
            os.path.join(run_dir, "extract.jsonl"),
            os.path.join(run_dir, "events.jsonl"),
        )
        assert resolve_paths("custom.json", None, None, None) == (
            "custom.json",
            os.path.join(run_dir, "extract.jsonl"),
            os.path.join(run_dir, "events.jsonl"),
        )
        assert resolve_paths(None, None, None, "/explicit/dir") == (
            "/explicit/dir/identify.json",
            "/explicit/dir/extract.jsonl",
            "/explicit/dir/events.jsonl",
        )
    finally:
        _rundir.RETROS_ROOT, _rundir.LATEST_POINTER = orig_root, orig_latest

    print("extract.py --selftest: OK")


def resolve_paths(infile, out, events, run_dir_arg) -> tuple[str, str, str]:
    """(infile, out, events) with explicit flags winning, else the resolved run-dir, else
    legacy cwd-relative filenames."""
    run_dir = _rundir.resolve_run_dir(run_dir_arg)
    infile = infile or (os.path.join(run_dir, "identify.json") if run_dir else "identify.json")
    out = out or (os.path.join(run_dir, "extract.jsonl") if run_dir else "extract.jsonl")
    events = events or (os.path.join(run_dir, "events.jsonl") if run_dir else "events.jsonl")
    return infile, out, events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="infile", default=None, help="identify.json path (default: <run-dir>/identify.json)")
    parser.add_argument("--session", help="extract a single session file instead of an identify.json")
    parser.add_argument("--out", default=None, help="default: <run-dir>/extract.jsonl")
    parser.add_argument("--events", default=None, help="default: <run-dir>/events.jsonl")
    parser.add_argument("--run-dir", dest="run_dir", default=None, help="run-dir to resolve identify.json/extract.jsonl/events.jsonl in (default: latest pointer, else cwd)")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    infile, out, events_out = resolve_paths(args.infile, args.out, args.events, args.run_dir)

    if args.session:
        paths = [args.session]
    else:
        with open(infile) as f:
            identify = json.load(f)
        paths = [s["path"] for s in identify["sessions"]]

    sessions = run(paths)

    with open(out, "w") as f:
        for session in sessions:
            f.write(json.dumps(session) + "\n")

    with open(events_out, "w") as f:
        for session in sessions:
            for event in session["toolEvents"]:
                rolled = dict(event)
                rolled["sessionId"] = session["sessionId"]
                f.write(json.dumps(rolled) + "\n")

    print(f"extract.py: {len(sessions)} sessions -> {out}, events -> {events_out}")


if __name__ == "__main__":
    main()
