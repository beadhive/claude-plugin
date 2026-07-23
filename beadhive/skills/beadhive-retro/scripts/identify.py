#!/usr/bin/env python3
"""Phase 1: identify Beadhive-using Claude Code sessions within a resolved time window.

Stdlib only. See ../references/metrics.md for the marker/window rules this implements.

Usage:
    identify.py [--since <iso|auto>] [--projects <glob>] [--out identify.json]
    identify.py --selftest
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

PROJECTS_ROOT = os.path.expanduser("~/.claude/projects")
BEAD_ID_RE = re.compile(r"\bbh-[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[0-9]+)?\b")
SKILL_MARKER_RE = re.compile(r"^(bh|beads):")
BD_BH_CMD_RE = re.compile(r"(?:^|&&|;|\n)\s*(bd|bh)\s+\S")
WT_BRANCH_RE = re.compile(r"^wt/")

SUNDAY = 6  # datetime.weekday(): Monday=0 ... Sunday=6
IDLE_GAP_WINDOW = timedelta(hours=24)


def parse_ts(ts: str):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def most_recent_sunday_00z(now: datetime) -> datetime:
    days_since_sunday = (now.weekday() - SUNDAY) % 7
    sunday = (now - timedelta(days=days_since_sunday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return sunday


def scan_session(path: str) -> dict:
    """Stream one session JSONL file, returning its summary + Beadhive markers."""
    session_id = None
    cwd = None
    git_branch = None
    start = None
    end = None
    markers = set()

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
            cwd = rec.get("cwd", cwd)
            branch = rec.get("gitBranch")
            if branch:
                git_branch = branch
                if WT_BRANCH_RE.match(branch):
                    markers.add("branch:wt/")

            ts = rec.get("timestamp")
            if ts:
                try:
                    dt = parse_ts(ts)
                except ValueError:
                    dt = None
                if dt is not None:
                    start = dt if start is None or dt < start else start
                    end = dt if end is None or dt > end else end

            message = rec.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        name = block.get("name", "")
                        inp = block.get("input") or {}
                        if name == "Skill":
                            skill = str(inp.get("skill", ""))
                            if SKILL_MARKER_RE.match(skill):
                                markers.add(f"skill:{skill}")
                        elif name == "Bash":
                            cmd = str(inp.get("command", ""))
                            if BD_BH_CMD_RE.search(cmd):
                                markers.add("bash:bd/bh")
                            for m in BEAD_ID_RE.finditer(cmd):
                                markers.add(f"id:{m.group(0)}")
                        else:
                            blob = json.dumps(inp)
                            for m in BEAD_ID_RE.finditer(blob):
                                markers.add(f"id:{m.group(0)}")

    return {
        "path": path,
        "sessionId": session_id,
        "cwd": cwd,
        "gitBranch": git_branch,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "markers": sorted(markers),
    }


def find_session_files(projects_glob: str) -> list:
    pattern = os.path.join(PROJECTS_ROOT, projects_glob, "*.jsonl")
    return sorted(glob.glob(pattern))


def resolve_since_auto(sessions: list, now: datetime) -> tuple:
    """Largest idle gap near the most recent Sunday; trailing edge is the boundary.

    Returns (boundary_iso, detected_bool).
    """
    intervals = []
    for s in sessions:
        if s["start"] and s["end"]:
            intervals.append((parse_ts(s["start"]), parse_ts(s["end"])))
    if not intervals:
        sunday = most_recent_sunday_00z(now)
        return sunday.isoformat(), False

    intervals.sort()
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    sunday = most_recent_sunday_00z(now)
    window_start = sunday - IDLE_GAP_WINDOW
    window_end = sunday + IDLE_GAP_WINDOW

    best_gap = None
    best_size = None
    for (prev_start, prev_end), (next_start, next_end) in zip(merged, merged[1:]):
        midpoint = prev_end + (next_start - prev_end) / 2
        if window_start <= midpoint <= window_end:
            size = next_start - prev_end
            if best_size is None or size > best_size:
                best_size = size
                best_gap = next_start

    if best_gap is not None:
        return best_gap.isoformat(), True
    return sunday.isoformat(), False


def qualifies(session: dict, boundary_iso: str) -> bool:
    if not session["markers"]:
        return False
    if not session["end"]:
        return False
    return parse_ts(session["end"]) >= parse_ts(boundary_iso)


def run(since: str, projects_glob: str) -> dict:
    files = find_session_files(projects_glob)
    sessions = [scan_session(p) for p in files]

    now = datetime.now(timezone.utc)
    if since == "auto":
        boundary_iso, detected = resolve_since_auto(sessions, now)
    else:
        boundary_iso, detected = parse_ts(since).isoformat(), True

    qualifying = [s for s in sessions if qualifies(s, boundary_iso)]
    project_root = PROJECTS_ROOT
    for s in qualifying:
        s["project"] = os.path.basename(os.path.dirname(s["path"]))

    return {
        "window": {"since": boundary_iso, "auto_detected": since == "auto", "detected": detected},
        "sessions": qualifying,
    }


def selftest() -> None:
    import tempfile

    tmpdir = tempfile.mkdtemp()
    proj_dir = os.path.join(tmpdir, "-Users-x-proj")
    os.makedirs(proj_dir)

    global PROJECTS_ROOT
    PROJECTS_ROOT = tmpdir

    now = datetime.now(timezone.utc)
    t0 = now - timedelta(hours=2)
    t1 = now - timedelta(hours=1)

    beadhive_lines = [
        {
            "sessionId": "sess-1",
            "cwd": "/tmp/proj",
            "gitBranch": "wt/bead/issue/bh-cp-1",
            "timestamp": t0.isoformat().replace("+00:00", "Z"),
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "Skill", "input": {"skill": "bh:planner"}}
                ],
            },
        },
        {
            "sessionId": "sess-1",
            "cwd": "/tmp/proj",
            "gitBranch": "wt/bead/issue/bh-cp-1",
            "timestamp": t1.isoformat().replace("+00:00", "Z"),
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": "bd show bh-cp-1"}}
                ],
            },
        },
    ]
    beadhive_path = os.path.join(proj_dir, "sess-1.jsonl")
    with open(beadhive_path, "w") as f:
        for rec in beadhive_lines:
            f.write(json.dumps(rec) + "\n")

    plain_lines = [
        {
            "sessionId": "sess-2",
            "cwd": "/tmp/other",
            "gitBranch": "main",
            "timestamp": t0.isoformat().replace("+00:00", "Z"),
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/tmp/x.py"}}
                ],
            },
        },
    ]
    plain_path = os.path.join(proj_dir, "sess-2.jsonl")
    with open(plain_path, "w") as f:
        for rec in plain_lines:
            f.write(json.dumps(rec) + "\n")

    # since=auto with no prior sessions to form a gap: falls back to most-recent-Sunday boundary,
    # which may exclude our synthetic (recent) sessions — so selftest pins --since explicitly.
    since_boundary = (now - timedelta(hours=3)).isoformat()
    result = run(since_boundary, "*")

    session_ids = {s["sessionId"] for s in result["sessions"]}
    assert "sess-1" in session_ids, f"expected sess-1 to qualify, got {session_ids}"
    assert "sess-2" not in session_ids, f"sess-2 should not qualify (no Beadhive markers), got {session_ids}"

    sess1 = next(s for s in result["sessions"] if s["sessionId"] == "sess-1")
    assert sess1["cwd"] == "/tmp/proj"
    assert sess1["gitBranch"] == "wt/bead/issue/bh-cp-1"
    assert "skill:bh:planner" in sess1["markers"]
    assert "bash:bd/bh" in sess1["markers"]
    assert "id:bh-cp-1" in sess1["markers"]
    assert "branch:wt/" in sess1["markers"]
    assert sess1["start"] is not None and sess1["end"] is not None
    assert sess1["start"] <= sess1["end"]

    # auto since-detection: build two clusters separated by an idle gap straddling the most
    # recent Sunday, assert the resolved boundary lands at the gap's trailing edge.
    sunday = most_recent_sunday_00z(now)
    before = sunday - timedelta(hours=6)
    after = sunday + timedelta(hours=6)
    gap_sessions = [
        {"start": (before - timedelta(hours=1)).isoformat(), "end": before.isoformat()},
        {"start": after.isoformat(), "end": (after + timedelta(hours=1)).isoformat()},
    ]
    boundary_iso, detected = resolve_since_auto(gap_sessions, now)
    assert detected is True
    assert parse_ts(boundary_iso) == after, f"expected boundary at gap trailing edge {after}, got {boundary_iso}"

    print("identify.py --selftest: OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", default="auto", help="ISO timestamp or 'auto' (default)")
    parser.add_argument("--projects", default="*", help="glob for project dir names under ~/.claude/projects")
    parser.add_argument("--out", default="identify.json", help="output path")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    result = run(args.since, args.projects)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"identify.py: {len(result['sessions'])} qualifying sessions, window since {result['window']['since']} -> {args.out}")


if __name__ == "__main__":
    main()
