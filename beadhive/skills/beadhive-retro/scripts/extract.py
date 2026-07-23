#!/usr/bin/env python3
"""Phase 2: normalize identified session transcripts into events + usage series. No judgment —
pure extraction. See ../references/metrics.md for the fields this feeds.

Usage:
    extract.py [--in identify.json] [--session <path>] [--out extract.jsonl] [--events events.jsonl]
    extract.py --selftest
"""
from __future__ import annotations

import argparse
import json
import re

BD_BH_TOKEN_RE = re.compile(r"(?:^|&&|;|\n)\s*((?:bd|bh)\s+\S+(?:\s+\S+)?)")


def bd_bh_detail(command: str):
    m = BD_BH_TOKEN_RE.search(command)
    return m.group(1).strip() if m else None


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


def extract_session(path: str) -> dict:
    usage_series = []
    tool_events = []  # each: {ts, tool, isSidechain, detail, tool_use_id}
    error_by_id = {}  # tool_use_id -> is_error
    read_chars = 0
    write_chars = 0
    session_id = None

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
                    if tool_use_id:
                        error_by_id[tool_use_id] = is_error
                    read_chars += content_chars(block.get("content"))

    for event in tool_events:
        event["error"] = error_by_id.get(event["tool_use_id"], False)

    return {
        "sessionId": session_id,
        "path": path,
        "usageSeries": usage_series,
        "toolEvents": tool_events,
        "contentSizes": {"readChars": read_chars, "writeChars": write_chars},
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
                ],
            },
        },
        {
            "sessionId": "sess-x",
            "isSidechain": False,
            "timestamp": "2026-07-20T10:01:00Z",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu1", "is_error": True, "content": "error: not found"},
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

    assert len(result["toolEvents"]) == 2
    bash_event = next(e for e in result["toolEvents"] if e["tool"] == "Bash")
    assert bash_event["detail"] == "bd show bh-cp-1", bash_event["detail"]
    assert bash_event["error"] is True

    write_event = next(e for e in result["toolEvents"] if e["tool"] == "Write")
    assert write_event["detail"] == "/tmp/f.py"
    assert write_event["error"] is False

    assert result["contentSizes"]["writeChars"] == len("hello world")
    assert result["contentSizes"]["readChars"] == len("error: not found")

    print("extract.py --selftest: OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="infile", default="identify.json", help="identify.json path")
    parser.add_argument("--session", help="extract a single session file instead of an identify.json")
    parser.add_argument("--out", default="extract.jsonl")
    parser.add_argument("--events", default="events.jsonl")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    if args.session:
        paths = [args.session]
    else:
        with open(args.infile) as f:
            identify = json.load(f)
        paths = [s["path"] for s in identify["sessions"]]

    sessions = run(paths)

    with open(args.out, "w") as f:
        for session in sessions:
            f.write(json.dumps(session) + "\n")

    with open(args.events, "w") as f:
        for session in sessions:
            for event in session["toolEvents"]:
                rolled = dict(event)
                rolled["sessionId"] = session["sessionId"]
                f.write(json.dumps(rolled) + "\n")

    print(f"extract.py: {len(sessions)} sessions -> {args.out}, events -> {args.events}")


if __name__ == "__main__":
    main()
