#!/usr/bin/env python3
"""Phase 3: aggregate extract.py output into analysis.json per ../references/metrics.md.

Stdlib only, offline (no live bd/bh xref) — runs against extract output alone. Consumes
extract.jsonl; outputs analysis.json.

Usage:
    analyze.py [--in extract.jsonl] [--out analysis.json]
    analyze.py --selftest
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta

BEAD_ID_RE = re.compile(r"\bbh-[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[0-9]+)?\b")

PLANNED_RE = re.compile(r"^(bd create|bh plan)\b")
IMPLEMENTED_RE = re.compile(r"^(bh work submit|bd close)\b")
MERGED_RE = re.compile(r"^bh work (merge|finish)\b")

CHARS_PER_TOKEN = 4
IDLE_GAP_SECONDS = 5 * 60
CACHE_MISS_RATIO = 0.5
RECREATION_SPIKE_TOKENS = 5000
SIGNIFICANT_WASTED_TOKENS = 10000


def parse_ts(ts: str):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def epic_of(bead_id: str) -> str:
    """Offline id-heuristic: strip a trailing '.N' child suffix to infer the parent epic."""
    return bead_id.split(".")[0]


def is_beads_bh(event: dict) -> bool:
    if event["tool"] == "Skill":
        skill = str(event.get("detail") or "")
        return skill.startswith("bh:") or skill.startswith("beads:")
    if event["tool"] == "Bash":
        detail = event.get("detail") or ""
        return bool(re.match(r"^(bd|bh)\s", detail))
    return False


def lifecycle_stage(detail: str):
    if PLANNED_RE.match(detail):
        return "planned"
    if IMPLEMENTED_RE.match(detail):
        return "implemented"
    if MERGED_RE.match(detail):
        return "merged"
    return None


def analyze_lifecycle(sessions: list) -> dict:
    seen = set()  # (stage, bead_id)
    by_epic = {}
    for session in sessions:
        for event in session["toolEvents"]:
            if event["tool"] != "Bash":
                continue
            detail = event.get("detail") or ""
            stage = lifecycle_stage(detail)
            if not stage:
                continue
            ids = set(BEAD_ID_RE.findall(detail)) | set(event.get("resultIds") or [])
            for bead_id in ids:
                key = (stage, bead_id)
                if key in seen:
                    continue
                seen.add(key)
                epic = epic_of(bead_id)
                bucket = by_epic.setdefault(epic, {"planned": 0, "implemented": 0, "merged": 0})
                bucket[stage] += 1
    return {"source": "id-heuristic", "byEpic": by_epic}


def analyze_failures(sessions: list) -> dict:
    by_tool = {"beadsBh": {}, "other": {}}
    for session in sessions:
        for event in session["toolEvents"]:
            if not event.get("error"):
                continue
            bucket = by_tool["beadsBh"] if is_beads_bh(event) else by_tool["other"]
            bucket[event["tool"]] = bucket.get(event["tool"], 0) + 1
    return by_tool


def analyze_skill_reads(sessions: list) -> dict:
    skills = {"bhBeads": {}, "other": {}}
    skill_md_reads = 0
    for session in sessions:
        for event in session["toolEvents"]:
            if event["tool"] == "Skill":
                name = str(event.get("detail") or "unknown")
                bucket = skills["bhBeads"] if (name.startswith("bh:") or name.startswith("beads:")) else skills["other"]
                bucket[name] = bucket.get(name, 0) + 1
            elif event["tool"] == "Read":
                path = str(event.get("detail") or "")
                if path.endswith("SKILL.md"):
                    skill_md_reads += 1
    return {"invocations": skills, "skillMdReads": skill_md_reads}


def analyze_tokens(sessions: list) -> dict:
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    read_chars = 0
    write_chars = 0
    for session in sessions:
        for u in session["usageSeries"]:
            totals["input"] += u["input"]
            totals["output"] += u["output"]
            totals["cache_read"] += u["cache_read"]
            totals["cache_creation"] += u["cache_creation"]
        sizes = session.get("contentSizes", {})
        read_chars += sizes.get("readChars", 0)
        write_chars += sizes.get("writeChars", 0)

    grand_total = sum(totals.values())
    pct = {k: (v / grand_total * 100 if grand_total else 0.0) for k, v in totals.items()}

    return {
        "exact": {"totals": totals, "percentOfTotal": pct},
        "approximateFileIo": {
            "approximate": True,
            "note": "estimated as chars/4 from tool_result and Write/Edit content sizes; "
            "not per-tool token precision",
            "readTokensApprox": read_chars // CHARS_PER_TOKEN,
            "writeTokensApprox": write_chars // CHARS_PER_TOKEN,
        },
    }


def analyze_cache(sessions: list) -> dict:
    total_cache_read = 0
    total_input = 0
    total_cache_creation = 0
    events = []

    for session in sessions:
        series = session["usageSeries"]
        for u in series:
            total_cache_read += u["cache_read"]
            total_input += u["input"]
            total_cache_creation += u["cache_creation"]

        for prev, cur in zip(series, series[1:]):
            if not prev.get("ts") or not cur.get("ts"):
                continue
            gap = (parse_ts(cur["ts"]) - parse_ts(prev["ts"])).total_seconds()
            if gap < IDLE_GAP_SECONDS:
                continue
            prev_cache_read = prev["cache_read"]
            cur_cache_read = cur["cache_read"]
            if prev_cache_read and cur_cache_read > prev_cache_read * CACHE_MISS_RATIO:
                continue  # cache stayed warm
            wasted = cur["cache_creation"]
            if wasted < RECREATION_SPIKE_TOKENS:
                continue
            events.append(
                {
                    "sessionId": session["sessionId"],
                    "ts": cur["ts"],
                    "idleGapSeconds": gap,
                    "wastedTokens": wasted,
                    "significant": wasted >= SIGNIFICANT_WASTED_TOKENS,
                }
            )

    ratio_denominator = total_input + total_cache_creation
    cache_ratio = (total_cache_read / ratio_denominator) if ratio_denominator else 0.0

    return {
        "cacheRatio": cache_ratio,
        "expiryEvents": events,
        "significantExpiryEventCount": sum(1 for e in events if e["significant"]),
    }


def turn_has_edit(event_ts_index: dict, ts: str) -> bool:
    events = event_ts_index.get(ts, [])
    return any(e["tool"] in ("Edit", "Write", "NotebookEdit") for e in events)


def analyze_activity(sessions: list) -> dict:
    per_session = {}
    for session in sessions:
        counts = {"planning": 0, "implementing": 0, "diagnosing": 0, "fixing": 0}
        events = session["toolEvents"]
        has_bh_work = any(
            e["tool"] == "Bash" and re.match(r"^bh work\b", e.get("detail") or "") for e in events
        )

        by_ts = {}
        for e in events:
            by_ts.setdefault(e.get("ts"), []).append(e)

        prev_error = False
        for ts in sorted(by_ts, key=lambda t: t or ""):
            turn_events = by_ts[ts]
            has_edit = any(e["tool"] in ("Edit", "Write", "NotebookEdit") for e in turn_events)
            has_diag = any(
                e["tool"] in ("Read", "Grep", "Glob")
                or (e["tool"] == "Bash" and re.search(r"test|pytest|check", e.get("detail") or "", re.I))
                for e in turn_events
            )
            has_plan_skill = any(
                e["tool"] == "Skill" and re.match(r"^bh:(planner|plan|replan)$", str(e.get("detail") or ""))
                for e in turn_events
            )
            has_plan_cmd = any(
                e["tool"] == "Bash" and lifecycle_stage(e.get("detail") or "") == "planned"
                for e in turn_events
            )

            if has_plan_skill or has_plan_cmd:
                counts["planning"] += 1
            if has_edit and has_bh_work:
                counts["implementing"] += 1
            if has_diag and not has_edit:
                counts["diagnosing"] += 1
            if has_edit and prev_error:
                counts["fixing"] += 1

            prev_error = any(e.get("error") for e in turn_events)

        suggested = max(counts, key=lambda k: counts[k]) if any(counts.values()) else None
        per_session[session["sessionId"]] = {"counts": counts, "suggested": suggested}

    return per_session


def analyze(sessions: list) -> dict:
    return {
        "lifecycle": analyze_lifecycle(sessions),
        "failures": analyze_failures(sessions),
        "skillReads": analyze_skill_reads(sessions),
        "tokens": analyze_tokens(sessions),
        "cache": analyze_cache(sessions),
        "activity": analyze_activity(sessions),
    }


def load_extract(path: str) -> list:
    sessions = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                sessions.append(json.loads(line))
    return sessions


def selftest() -> None:
    sessions = [
        {
            "sessionId": "s1",
            "usageSeries": [
                {
                    "ts": "2026-07-20T10:00:00Z",
                    "input": 10,
                    "output": 20,
                    "cache_read": 1000,
                    "cache_creation": 0,
                },
                {
                    # idle gap > 5m, cache_read collapses, cache_creation spikes >= 5000: expiry event
                    "ts": "2026-07-20T10:20:00Z",
                    "input": 5,
                    "output": 15,
                    "cache_read": 10,
                    "cache_creation": 12000,
                },
            ],
            "toolEvents": [
                {"ts": "2026-07-20T10:00:00Z", "tool": "Bash", "detail": "bd create issue", "error": False},
                {"ts": "2026-07-20T10:00:00Z", "tool": "Skill", "detail": "bh:planner", "error": False},
                {"ts": "2026-07-20T10:20:00Z", "tool": "Bash", "detail": "bh work submit bh-cp-1", "error": False},
                {"ts": "2026-07-20T10:20:00Z", "tool": "Edit", "detail": "/tmp/f.py", "error": False},
                {"ts": "2026-07-20T10:20:00Z", "tool": "Bash", "detail": "bh work merge bh-cp-1", "error": False},
                {"ts": "2026-07-20T10:25:00Z", "tool": "Bash", "detail": "bd show broken", "error": True},
                {"ts": "2026-07-20T10:30:00Z", "tool": "Edit", "detail": "/tmp/g.py", "error": False},
                {"ts": "2026-07-20T10:35:00Z", "tool": "Skill", "detail": "other:thing", "error": False},
                {"ts": "2026-07-20T10:35:00Z", "tool": "Read", "detail": "/x/SKILL.md", "error": False},
            ],
            "contentSizes": {"readChars": 400, "writeChars": 40},
        }
    ]

    result = analyze(sessions)

    lc = result["lifecycle"]["byEpic"]
    assert lc["bh-cp-1"]["implemented"] == 1
    assert lc["bh-cp-1"]["merged"] == 1
    assert "issue" not in lc  # 'bd create issue' has no bh-xxx id, contributes nothing

    fail = result["failures"]
    assert fail["beadsBh"]["Bash"] == 1

    reads = result["skillReads"]
    assert reads["invocations"]["bhBeads"]["bh:planner"] == 1
    assert reads["invocations"]["other"]["other:thing"] == 1
    assert reads["skillMdReads"] == 1

    tok = result["tokens"]
    assert tok["exact"]["totals"]["input"] == 15
    assert tok["exact"]["totals"]["cache_read"] == 1010
    assert tok["approximateFileIo"]["approximate"] is True
    assert tok["approximateFileIo"]["readTokensApprox"] == 400 // 4
    assert tok["approximateFileIo"]["writeTokensApprox"] == 40 // 4

    cache = result["cache"]
    assert len(cache["expiryEvents"]) == 1
    ev = cache["expiryEvents"][0]
    assert ev["wastedTokens"] == 12000
    assert ev["significant"] is True
    assert cache["significantExpiryEventCount"] == 1

    activity = result["activity"]["s1"]["counts"]
    assert activity["planning"] >= 1
    assert activity["implementing"] >= 1
    assert activity["fixing"] >= 1  # Edit at 10:30 immediately follows the error turn at 10:25
    assert activity["diagnosing"] >= 1  # Read+Skill at 10:35, no Edit on that turn

    print("analyze.py --selftest: OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="infile", default="extract.jsonl")
    parser.add_argument("--out", default="analysis.json")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    sessions = load_extract(args.infile)
    result = analyze(sessions)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"analyze.py: analyzed {len(sessions)} sessions -> {args.out}")


if __name__ == "__main__":
    main()
