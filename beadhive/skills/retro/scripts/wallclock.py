#!/usr/bin/env python3
"""Phase 4: reconstruct a per-session wall-clock timeline and split it into waste families.

`analyze.py` measures tokens and cost; nothing else in the pipeline measures *time*, so a
session that burned four hours waiting on a human and a session that burned four hours
re-running the same test suite look identical in `analysis.json`. This walks the raw
transcripts named by `identify.json` and reconstructs a per-session timeline, then splits it
into four buckets and hunts specific kinds of waste inside them.

TIMING MODEL (read this before trusting a number — and see meta.timingModel in the output)
  Transcripts carry no durations — only a `timestamp` per record, written when that record was
  appended. Every duration here is therefore a gap between consecutive records, never a
  measured span:

    inference  = ts(last assistant record of a requestId) - ts(record before the first)
                 -> includes model latency, thinking, streaming, and any retry/queue time.
    tool       = ts(tool_result record) - ts(assistant record carrying the tool_use)
                 -> includes anything the harness did before/after the command, notably time
                    the call sat in a permission prompt waiting on a human.
    human idle = ts(human prompt) - ts(previous record), only when the previous assistant turn
                 ended WITHOUT a tool_use (i.e. the agent had genuinely stopped).

  Parallel tool calls in one assistant message overlap, so per-tool durations sum to more than
  the wall-clock they occupied. `totals.toolSec` and `bySession[*].toolSec` use the batch span
  (max result ts minus the assistant ts) to stay honest; `toolTime.byClass`/`byTool` sum
  per-call and are labelled inflated. Every family below carries this "derived from record
  gaps, not measured" caveat directly in its own `note`, not only here in the docstring.

  `<task-notification>` user records are harness-injected (a background sub-agent finishing)
  and carry `promptSource` even though no human typed them — they are excluded from human-idle
  detection (see `is_human_prompt`); getting this wrong misattributes background-agent runtime
  to "parked" human idle.

FOUR WASTE QUESTIONS THIS SPLITS SESSION SPAN INTO
  1. idle on a human   -> humanIdle, split into approval-shaped (a supervisor loop could have
                          answered), direction (substantive typed guidance), and parked (>6h —
                          the session was left overnight, not a decision stall).
  2. slow inference    -> per-turn output tokens/sec; excessSecondsVsP75 is the time that would
                          have been saved had every turn generated at the p75 rate.
  3. long test passes  -> tool calls classified test/build/lint, ranked by duration.
  4. test churn        -> the same test command re-run N times in a session, and test runs that
                          follow a merge/submit call inside a short window.

By default, resolves identify.json/writes wallclock.json in the same run-dir as the other three
phases: explicit `--run-dir` wins, else the `latest` pointer, else legacy cwd-relative
defaults. `--in`/`--out` always override individually.

Stdlib only, offline (no live bd/bh xref).

Usage:
    wallclock.py [--in identify.json] [--out wallclock.json] [--run-dir DIR] [--top N]
    wallclock.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
from collections import defaultdict
from datetime import datetime

import _rundir

PARKED_SEC = 6 * 3600          # a gap past this is "session parked", not a decision stall
SLOW_TURN_SEC = 180            # an inference turn longer than this is worth naming
MIN_TOKENS_FOR_RATE = 200      # short turns are latency-dominated; excluded from rate stats
APPROVAL_GATE_SEC = 45         # a "should be instant" tool call slower than this looks gated
MERGE_WINDOW_SEC = 20 * 60     # a test run this soon after a merge/submit counts as merge-adjacent
CHURN_MIN_RUNS = 3             # same command this many times in a session = churn

TIMING_CAVEAT = "derived from record gaps, not measured"

# --- command classification -----------------------------------------------------------------
TEST_RE = re.compile(
    r"\b(pytest|py\.test|unittest|nose2|tox|vitest|jest|mocha|ava\b|cargo\s+test|go\s+test|"
    r"gotestsum|npm\s+(run\s+)?test|yarn\s+test|pnpm\s+(run\s+)?test|make\s+(test|check)|"
    r"just\s+(test|check)|check-all|bats\b|rspec|phpunit|dotnet\s+test|ctest|"
    r"bh\s+work\s+check|selftest)\b"
)  # note: `selftest` (no leading dash in the alternation) so `--selftest` still matches — a
#    \b cannot sit between a space and a '-', both non-word characters.
LINT_RE = re.compile(r"\b(ruff|mypy|pyright|eslint|tsc\b|clippy|golangci-lint|shellcheck|black|"
                     r"prettier|pre-commit|gofmt|rustfmt|flake8|pylint)\b")
BUILD_RE = re.compile(r"\b(docker\s+(build|buildx)|cargo\s+build|go\s+build|npm\s+run\s+build|"
                      r"yarn\s+build|pnpm\s+build|make\s+(all|build)|uv\s+build|maturin|"
                      r"pyinstaller|tsc\s+-b|webpack|vite\s+build)\b")
MERGE_RE = re.compile(r"\b(bh\s+work\s+(merge|submit|finish)|git\s+merge|gh\s+pr\s+merge)\b")
FAST_RE = re.compile(  # commands that should return in well under a second
    r"^(git\s+(status|log|diff|branch|remote|rev-parse|show)|ls\b|cat\b|pwd|echo|wc\b|"
    r"head\b|tail\b|grep\b|find\b|which\b|command\s+-v|bh\s+work\s+(show|issue|ready|list)|"
    r"bd\s+(show|list|ready)|bh\s+bd\s+(show|list|ready)|bh\s+config\s+get|bh\s+hive\s+(list|status))"
)
# Approval-shaped human replies: a supervisor-agent loop could plausibly have said this.
APPROVAL_RE = re.compile(
    r"^\W*(y|ye|yes|yep|yeah|yup|ok|okay|k|sure|go|go\s+ahead|proceed|continue|approved?|"
    r"lgtm|do\s+it|ship\s+it|sounds\s+good|please\s+do|makes\s+sense|agreed?|correct|right|"
    r"perfect|great|nice|thanks?|ty|\U0001f44d|\+1)\W*$",
    re.I,
)
# Tools that themselves block on a human answer. Referenced here only to sharpen human-idle
# classification (an idle wait right after one of these is "answering a question", distinct
# from unprompted "direction"); a dedicated humanGate time-family is a later phase's job.
GATE_TOOLS = {"AskUserQuestion", "ExitPlanMode", "EnterPlanMode"}


def classify_command(cmd: str) -> str:
    c = (cmd or "").strip()
    if not c:
        return "other"
    if TEST_RE.search(c):
        return "test"
    if BUILD_RE.search(c):
        return "build"
    if LINT_RE.search(c):
        return "lint"
    if re.match(r"^(bh|bd)\s", c):
        return "beadhive"
    if re.match(r"^(git|gh)\s", c):
        return "vcs"
    return "other"


def normalize_command(cmd: str, width: int = 120) -> str:
    """Collapse a command to a churn key: no cd prefix, no env prefix, one line, no bead ids."""
    c = re.sub(r"\s+", " ", (cmd or "").strip())
    c = re.sub(r"^cd\s+\S+\s*&&\s*", "", c)
    c = re.sub(r"^(\w+=\S+\s+)+", "", c)
    c = re.sub(r"\b(bh|bhui|ah)-[a-z0-9]+(?:-[a-z0-9]+)*(?:\.\d+)?\b", "<bead>", c)
    return c[:width]


def ts_of(rec: dict):
    t = rec.get("timestamp")
    if not t:
        return None
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None


def text_of(message: dict) -> str:
    content = (message or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def is_human_prompt(rec: dict) -> bool:
    """A typed human turn — not a tool_result, not a harness-injected meta record.

    `<task-notification>` records are the critical negative case: the harness stamps them with
    `promptSource` (they look exactly like a human turn on that field alone) when a background
    sub-agent finishes, but no human typed them. Counting one as human idle misattributes
    background-agent runtime to "parked" — see the module docstring.
    """
    if rec.get("type") != "user" or rec.get("toolUseResult") is not None or rec.get("isMeta"):
        return False
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    ):
        return False
    if isinstance(content, str) and content.lstrip().startswith("<task-notification>"):
        return False
    return bool(rec.get("promptSource") or (rec.get("origin") or {}).get("kind") == "human")


def classify_idle(prompt_text: str, gap_sec: float, preceding_tools: set) -> str:
    body = re.sub(r"<[^>]+>", " ", prompt_text or "").strip()
    if gap_sec >= PARKED_SEC:
        return "parked"
    if preceding_tools & GATE_TOOLS:
        return "answering-a-question"
    if APPROVAL_RE.match(body) or (len(body) <= 24 and not body.endswith("?")):
        return "approval-shaped"
    return "direction"


# --- per-session walk -------------------------------------------------------------------------
def walk_session(path: str, sid: str) -> dict:
    recs = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") in ("assistant", "user") and rec.get("timestamp"):
                recs.append(rec)
    recs.sort(key=lambda r: r["timestamp"])

    pending = {}        # tool_use_id -> (tool, cmd, assistant_ts, assistant_uuid)
    tool_calls = []
    batch_span = {}     # assistant_uuid -> [start_ts, last_result_ts] (overlap-safe wall clock)
    turns = defaultdict(list)   # requestId -> [(ts, rec)]
    turn_order = []
    idle_events = []
    prev_ts = None
    prev_rec = None

    for rec in recs:
        t = ts_of(rec)
        if t is None:
            continue
        if rec.get("type") == "assistant":
            rid = rec.get("requestId") or rec.get("uuid")
            if rid not in turns:
                turn_order.append((rid, prev_ts))
            turns[rid].append((t, rec))
            for block in ((rec.get("message") or {}).get("content")) or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    inp = block.get("input") or {}
                    cmd = inp.get("command") or inp.get("skill") or inp.get("file_path") or ""
                    pending[block.get("id")] = (block.get("name") or "?", str(cmd), t, rec.get("uuid"))
                    batch_span.setdefault(rec.get("uuid"), [t, t])
        elif is_human_prompt(rec):
            # Only an idle wait if the agent had actually stopped: the record before is an
            # assistant message with no tool_use pending from it.
            waiting = prev_rec is not None and prev_rec.get("type") == "assistant" and not any(
                isinstance(b, dict) and b.get("type") == "tool_use"
                for b in ((prev_rec.get("message") or {}).get("content")) or []
            )
            if waiting and prev_ts is not None:
                gap = (t - prev_ts).total_seconds()
                if gap > 0:
                    prev_tools = set()
                    for r in reversed(recs[: recs.index(rec)]):
                        if r.get("type") != "assistant":
                            continue
                        blocks = ((r.get("message") or {}).get("content")) or []
                        prev_tools |= {
                            b.get("name") for b in blocks
                            if isinstance(b, dict) and b.get("type") == "tool_use"
                        }
                        if prev_tools or (r.get("message") or {}).get("stop_reason") == "end_turn":
                            break
                    text = text_of(rec.get("message") or {})
                    idle_events.append(
                        {
                            "sessionId": sid,
                            "ts": rec["timestamp"],
                            "gapSec": gap,
                            "class": classify_idle(text, gap, prev_tools),
                            "replyChars": len(text),
                            "replyHead": re.sub(r"\s+", " ", text)[:140],
                            "precededBy": sorted(x for x in prev_tools if x),
                        }
                    )
        else:  # tool_result
            for block in ((rec.get("message") or {}).get("content")) or []:
                if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                    continue
                tool, cmd, a_ts, a_uuid = pending.pop(block.get("tool_use_id"), (None, "", None, None))
                if a_ts is None:
                    continue
                dur = (t - a_ts).total_seconds()
                if a_uuid in batch_span:
                    batch_span[a_uuid][1] = max(batch_span[a_uuid][1], t)
                out = block.get("content")
                out_chars = len(out) if isinstance(out, str) else len(str(out))
                tool_calls.append(
                    {
                        "sessionId": sid,
                        "ts": a_ts.isoformat(),
                        "tool": tool,
                        "cmd": cmd[:400],
                        "class": classify_command(cmd) if tool == "Bash" else "other",
                        "durationSec": dur,
                        "outChars": out_chars,
                        "isError": bool(block.get("is_error")),
                    }
                )
        prev_ts, prev_rec = t, rec

    # inference turns
    inference = []
    for rid, start in turn_order:
        entries = turns[rid]
        end = max(e[0] for e in entries)
        begin = start or min(e[0] for e in entries)
        dur = (end - begin).total_seconds()
        usage = {}
        for _, r in entries:
            u = (r.get("message") or {}).get("usage") or {}
            if u.get("output_tokens"):
                usage = u
        out_tok = int(usage.get("output_tokens") or 0)
        model = ((entries[-1][1].get("message") or {}).get("model")) or "?"
        if dur >= 0:
            inference.append(
                {
                    "sessionId": sid,
                    "ts": begin.isoformat(),
                    "durationSec": dur,
                    "outputTokens": out_tok,
                    "model": model,
                    "tokPerSec": (out_tok / dur) if dur > 0 and out_tok else None,
                }
            )

    span = 0.0
    if len(recs) >= 2:
        first_ts, last_ts = ts_of(recs[0]), ts_of(recs[-1])
        if first_ts is not None and last_ts is not None:
            span = (last_ts - first_ts).total_seconds()
    # toolSec: the overlap-safe wall clock a session's tool calls actually occupied — parallel
    # calls in one assistant message collapse to their batch span (max result ts − assistant
    # ts), not a per-call sum. See TIMING_CAVEAT / toolTime.byClass for the (labelled-inflated)
    # per-call sum instead.
    tool_sec = sum((b[1] - b[0]).total_seconds() for b in batch_span.values())
    inference_sec = sum(i["durationSec"] for i in inference)
    human_idle_sec = sum(e["gapSec"] for e in idle_events)
    return {
        "sessionId": sid,
        "spanSec": span,
        "inferenceSec": inference_sec,
        "toolSec": tool_sec,
        "humanIdleSec": human_idle_sec,
        "unattributedSec": max(0.0, span - inference_sec - tool_sec - human_idle_sec),
        "inference": inference,
        "toolCalls": tool_calls,
        "idleEvents": idle_events,
    }


# --- aggregation ------------------------------------------------------------------------------
def aggregate(sessions: list, top: int) -> dict:
    all_tools = [c for s in sessions for c in s["toolCalls"]]
    all_inf = [i for s in sessions for i in s["inference"]]
    all_idle = [e for s in sessions for e in s["idleEvents"]]

    # 1. human idle
    idle_by_class = defaultdict(lambda: {"count": 0, "sec": 0.0})
    for e in all_idle:
        b = idle_by_class[e["class"]]
        b["count"] += 1
        b["sec"] += e["gapSec"]
    recoverable = idle_by_class.get("approval-shaped", {"sec": 0.0})["sec"]

    # 2. inference rate
    rated = [i for i in all_inf if i["tokPerSec"] and i["outputTokens"] >= MIN_TOKENS_FOR_RATE]
    rates = sorted(i["tokPerSec"] for i in rated)
    p50 = statistics.median(rates) if rates else 0.0
    p75 = rates[int(len(rates) * 0.75)] if rates else 0.0
    p25 = rates[int(len(rates) * 0.25)] if rates else 0.0
    excess = sum(max(0.0, i["durationSec"] - i["outputTokens"] / p75) for i in rated) if p75 else 0.0

    # 3/4. tools by class, test churn, merge-adjacent re-tests
    by_class = defaultdict(lambda: {"count": 0, "sec": 0.0, "failed": 0})
    for c in all_tools:
        b = by_class[c["class"]]
        b["count"] += 1
        b["sec"] += c["durationSec"]
        b["failed"] += int(c["isError"])

    churn = defaultdict(lambda: {"runs": 0, "sec": 0.0, "sessions": set(), "example": ""})
    for c in all_tools:
        if c["class"] not in ("test", "build", "lint"):
            continue
        k = (c["class"], normalize_command(c["cmd"]))
        e = churn[k]
        e["runs"] += 1
        e["sec"] += c["durationSec"]
        e["sessions"].add(c["sessionId"])
        e["example"] = e["example"] or c["cmd"][:200]
    churn_rows = [
        {
            "class": k[0], "command": k[1], "runs": v["runs"], "sec": v["sec"],
            "sessions": len(v["sessions"]), "example": v["example"],
            "avgSec": v["sec"] / v["runs"] if v["runs"] else 0.0,
        }
        for k, v in churn.items()
    ]
    churn_rows.sort(key=lambda r: -r["sec"])
    repeat_rows = [r for r in churn_rows if r["runs"] >= CHURN_MIN_RUNS]
    # seconds spent on runs 2..N of a repeated command — the re-test tax
    retest_tax = sum(r["sec"] - r["avgSec"] for r in repeat_rows)

    merge_adjacent = []
    merge_unique = {}  # (session, ts, cmd) -> seconds, deduped across overlapping windows
    for s in sessions:
        calls = sorted(s["toolCalls"], key=lambda c: c["ts"])
        merges = [c for c in calls if c["tool"] == "Bash" and MERGE_RE.search(c["cmd"] or "")]
        for m in merges:
            m_ts = datetime.fromisoformat(m["ts"])
            following = [
                c for c in calls
                if c["class"] in ("test", "build", "lint")
                and 0 <= (datetime.fromisoformat(c["ts"]) - m_ts).total_seconds() <= MERGE_WINDOW_SEC
            ]
            for c in following:
                merge_unique[(s["sessionId"], c["ts"], c["cmd"])] = c["durationSec"]
            if following:
                merge_adjacent.append(
                    {
                        "sessionId": s["sessionId"],
                        "ts": m["ts"],
                        "mergeCmd": m["cmd"][:160],
                        "runs": len(following),
                        "sec": sum(c["durationSec"] for c in following),
                    }
                )
    merge_adjacent.sort(key=lambda r: -r["sec"])

    # heuristic: a "should be instant" call that took a long time was probably sitting in a
    # permission prompt. The transcript records no permission event, so this is inference, not
    # an observation — labelled explicitly below.
    gated = [
        c for c in all_tools
        if c["tool"] == "Bash"
        and c["durationSec"] >= APPROVAL_GATE_SEC
        and FAST_RE.match(normalize_command(c["cmd"], 200))
    ]
    gated.sort(key=lambda c: -c["durationSec"])

    other_by_tool = defaultdict(lambda: {"count": 0, "sec": 0.0})
    for c in all_tools:
        b = other_by_tool[c["tool"] or "?"]
        b["count"] += 1
        b["sec"] += c["durationSec"]

    slow_turns = sorted(
        (i for i in all_inf if i["durationSec"] >= SLOW_TURN_SEC), key=lambda i: -i["durationSec"]
    )
    slow_tools = sorted(all_tools, key=lambda c: -c["durationSec"])

    total_span = sum(s["spanSec"] for s in sessions)
    total_inf = sum(s["inferenceSec"] for s in sessions)
    total_tool = sum(s["toolSec"] for s in sessions)
    total_idle = sum(s["humanIdleSec"] for s in sessions)
    total_unattributed = sum(s["unattributedSec"] for s in sessions)

    return {
        "totals": {
            "sessions": len(sessions),
            "sessionSpanSec": total_span,
            "inferenceSec": total_inf,
            "toolSec": total_tool,
            "humanIdleSec": total_idle,
            "unattributedSec": total_unattributed,
            "note": f"session-span split into inference/tool/humanIdle/unattributed; all four "
            f"are {TIMING_CAVEAT} (a gap between consecutive transcript records), and "
            "sessionSpanSec is summed across concurrently-open sessions, not wall-clock elapsed. "
            "unattributedSec is span minus the other three — mainly background sub-agent "
            "(sidechain) activity and a session left open with no following turn to close the "
            "gap, neither of which produces a human-idle or tool-call record to attribute to.",
        },
        "humanIdle": {
            "byClass": {k: v for k, v in sorted(idle_by_class.items(), key=lambda kv: -kv[1]["sec"])},
            "recoverableSec": recoverable,
            "recoverableNote": "approval-shaped: a supervisor-agent loop could plausibly have "
                               "answered these without a human.",
            "top": sorted(all_idle, key=lambda e: -e["gapSec"])[:top],
            "note": f"gapSec is {TIMING_CAVEAT} (human-prompt ts minus the preceding record's "
            "ts, only counted when the prior assistant turn ended without a tool_use).",
        },
        "inferenceRate": {
            "turns": len(all_inf),
            "ratedTurns": len(rated),
            "p25TokPerSec": p25,
            "medianTokPerSec": p50,
            "p75TokPerSec": p75,
            "excessSecondsVsP75": excess,
            "slowTurnCount": len(slow_turns),
            "slowTurnSec": sum(i["durationSec"] for i in slow_turns),
            "top": slow_turns[:top],
            "note": f"turn durationSec is {TIMING_CAVEAT} (last assistant-record ts of a "
            "requestId minus the record before the first), so it includes thinking + streaming "
            "+ any retry/queue time — not pure provider latency.",
        },
        "toolTime": {
            "byTool": {
                k: v for k, v in sorted(other_by_tool.items(), key=lambda kv: -kv[1]["sec"])[:20]
            },
            "byClass": {k: v for k, v in sorted(by_class.items(), key=lambda kv: -kv[1]["sec"])},
            "note": f"durationSec per call is {TIMING_CAVEAT} (tool_result ts minus the "
            "assistant record carrying the tool_use).",
            "byClassNote": "byClass/byTool sum every call's durationSec individually; parallel "
            "calls in one assistant message overlap in real time, so these totals are inflated "
            "vs totals.toolSec, which uses the batch span instead. Do not present byClass/byTool "
            "sums as the wall-clock time tools occupied.",
            "slowest": slow_tools[:top],
            "slowestByClass": {
                cls: sorted(
                    (c for c in all_tools if c["class"] == cls), key=lambda c: -c["durationSec"]
                )[:top]
                for cls in ("test", "build", "lint")
            },
        },
        "testChurn": {
            "commands": churn_rows[:top],
            "repeated": repeat_rows[:top],
            "repeatedCount": len(repeat_rows),
            "retestTaxSec": retest_tax,
            "retestTaxNote": f"seconds in runs 2..N of every command run >={CHURN_MIN_RUNS} times.",
            "mergeAdjacent": merge_adjacent[:top],
            "mergeAdjacentSec": sum(r["sec"] for r in merge_adjacent),
            "mergeAdjacentRuns": sum(r["runs"] for r in merge_adjacent),
            "mergeAdjacentUniqueRuns": len(merge_unique),
            "mergeAdjacentUniqueSec": sum(merge_unique.values()),
            "mergeAdjacentNote": "windows overlap, so a run following two merges counts twice in "
                                 "runs/sec; the unique* figures count each run once.",
            "note": f"every sec figure here is {TIMING_CAVEAT} (per-call tool_result ts minus "
            "assistant ts, summed).",
        },
        "suspectedApprovalGate": {
            "count": len(gated),
            "sec": sum(c["durationSec"] for c in gated),
            "top": gated[:top],
            "note": "heuristic, not observed: a normally-instant command that took >= "
                    f"{APPROVAL_GATE_SEC}s was probably parked in a permission prompt. "
                    f"Transcripts record no permission event, so this is inferred. Durations are "
                    f"otherwise {TIMING_CAVEAT}, same as toolTime.",
        },
        "bySession": {
            s["sessionId"]: {
                "spanSec": s["spanSec"],
                "inferenceSec": s["inferenceSec"],
                "toolSec": s["toolSec"],
                "humanIdleSec": s["humanIdleSec"],
                "unattributedSec": s["unattributedSec"],
                "testSec": sum(c["durationSec"] for c in s["toolCalls"] if c["class"] == "test"),
            }
            for s in sessions
        },
    }


# --- cli --------------------------------------------------------------------------------------
def resolve_paths(infile, out, run_dir_arg) -> tuple:
    """(infile, out) with explicit flags winning, else the resolved run-dir, else legacy
    cwd-relative filenames — same precedence as analyze.py/render.py."""
    run_dir = _rundir.resolve_run_dir(run_dir_arg)
    infile = infile or (os.path.join(run_dir, "identify.json") if run_dir else "identify.json")
    out = out or (os.path.join(run_dir, "wallclock.json") if run_dir else "wallclock.json")
    return infile, out


def selftest() -> None:
    assert classify_command("uv run pytest -q tests/") == "test"
    assert classify_command("python3 scripts/analyze.py --selftest") == "test"
    assert classify_command("docker build -t x .") == "build"
    assert classify_command("ruff check .") == "lint"
    assert classify_command("bh work merge bh-1") == "beadhive"
    assert classify_command("git status") == "vcs"
    assert normalize_command("cd /a/b && pytest tests/test_x.py") == "pytest tests/test_x.py"
    assert normalize_command("bh work merge bh-cp-6je") == "bh work merge <bead>"
    assert classify_idle("yes", 60, set()) == "approval-shaped"
    assert classify_idle("go ahead", 60, set()) == "approval-shaped"
    assert classify_idle("rewrite the parser to stream", 60, set()) == "direction"
    assert classify_idle("option B", 60, {"AskUserQuestion"}) == "answering-a-question"
    assert classify_idle("yes", PARKED_SEC + 1, set()) == "parked"
    assert MERGE_RE.search("bh work merge bh-1") and not MERGE_RE.search("bh work show bh-1")
    assert FAST_RE.match("git status") and not FAST_RE.match("pytest -q")

    # is_human_prompt: the task-notification negative case is the acceptance-critical one — a
    # background sub-agent's completion notification carries promptSource but was never typed
    # by a human, and getting this wrong misattributed 41h of background-agent runtime to
    # "parked" human idle in the prototype this script replaces.
    assert is_human_prompt({"type": "user", "promptSource": "typed", "message": {"content": "hi"}})
    assert not is_human_prompt({"type": "user", "toolUseResult": {}, "message": {"content": []}})
    assert not is_human_prompt(
        {"type": "user", "promptSource": "typed",
         "message": {"content": [{"type": "tool_result", "content": "x"}]}}
    )
    assert not is_human_prompt(
        {"type": "user", "promptSource": "typed",
         "message": {"content": "<task-notification>\n<task-id>x</task-id>"}}
    )

    _walk_session_selftest()
    _aggregate_selftest()
    _resolve_paths_selftest()
    print("wallclock.py: selftest OK")


def _walk_session_selftest() -> None:
    """Exercises walk_session() end to end against real record shapes (not pre-built dicts):
    parallel tool-call batch-span overlap, and the task-notification human-idle exclusion."""
    import tempfile

    t0 = "2026-01-01T00:00:00.000Z"
    t_a_result = "2026-01-01T00:00:10.000Z"   # tool "a" resolves after 10s
    t_b_result = "2026-01-01T00:00:30.000Z"   # tool "b" (parallel, same message) after 30s
    t_notification = "2026-01-01T03:00:30.000Z"  # 2h30m after the batch — a background notif

    recs = [
        # one assistant message issuing two PARALLEL Bash tool calls
        {
            "type": "assistant", "uuid": "asst-1", "requestId": "req-1", "timestamp": t0,
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "a", "name": "Bash", "input": {"command": "sleep 10"}},
                    {"type": "tool_use", "id": "b", "name": "Bash", "input": {"command": "sleep 30"}},
                ],
            },
        },
        {
            "type": "user", "timestamp": t_a_result,
            "message": {"content": [{"type": "tool_result", "tool_use_id": "a", "content": "ok"}]},
        },
        {
            "type": "user", "timestamp": t_b_result,
            "message": {"content": [{"type": "tool_result", "tool_use_id": "b", "content": "ok"}]},
        },
        # assistant turn ends with no tool_use, so the harness-injected notification below
        # would (if wrongly classified) attribute a 2.5h gap to human idle.
        {
            "type": "assistant", "uuid": "asst-2", "requestId": "req-2", "timestamp": t_b_result,
            "message": {"role": "assistant", "content": [{"type": "text", "text": "done for now"}]},
        },
        {
            "type": "user", "timestamp": t_notification, "promptSource": "notification",
            "message": {"content": "<task-notification>\n<task-id>bg-1</task-id>\ndone\n"},
        },
    ]

    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "sess.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for rec in recs:
            fh.write(json.dumps(rec) + "\n")

    result = walk_session(path, "s-parallel")

    # per-call durations are each measured from the SAME assistant ts (both "a" and "b" were
    # issued in the one batch): 10s and 30s, summing to 40s ...
    durs = sorted(c["durationSec"] for c in result["toolCalls"])
    assert durs == [10.0, 30.0], durs
    assert sum(durs) == 40.0
    # ... but toolSec (batch span) is the overlap-safe wall clock the batch actually occupied:
    # max(10, 30) - start(0) = 30s, strictly less than the 40s per-call sum — the concrete
    # demonstration of the "parallel calls overlap" acceptance requirement.
    assert result["toolSec"] == 30.0, result["toolSec"]
    assert result["toolSec"] < sum(durs)

    # the task-notification 2.5h after an assistant turn that ended without a tool_use must NOT
    # be counted as human idle — the acceptance-critical case for this script.
    assert result["idleEvents"] == [], result["idleEvents"]
    assert result["humanIdleSec"] == 0.0


def _aggregate_selftest() -> None:
    agg = aggregate(
        [{
            "sessionId": "s", "spanSec": 100.0, "inferenceSec": 0.0, "toolSec": 0.0,
            "humanIdleSec": 0.0, "unattributedSec": 100.0, "inference": [], "idleEvents": [],
            "toolCalls": [
                {"sessionId": "s", "ts": "2026-01-01T00:00:00+00:00", "tool": "Bash",
                 "cmd": "bh work merge bh-1", "class": "beadhive", "durationSec": 5.0,
                 "outChars": 10, "isError": False},
                {"sessionId": "s", "ts": "2026-01-01T00:02:00+00:00", "tool": "Bash",
                 "cmd": "pytest -q", "class": "test", "durationSec": 30.0,
                 "outChars": 10, "isError": False},
            ],
        }], top=5)
    # the test run 1 minute after a merge is attributed to that merge point
    assert agg["testChurn"]["mergeAdjacentRuns"] == 1
    assert agg["testChurn"]["mergeAdjacentUniqueRuns"] == 1

    # every duration family carries the "derived from record gaps, not measured" caveat
    # verbatim, in the output itself (not only in prose) — this is an acceptance requirement.
    for family in ("totals", "humanIdle", "inferenceRate", "toolTime", "testChurn", "suspectedApprovalGate"):
        notes = " ".join(str(v) for k, v in agg[family].items() if "note" in k.lower())
        assert TIMING_CAVEAT in notes, f"{family} is missing the '{TIMING_CAVEAT}' caveat: {notes!r}"

    # toolTime.byClass/byTool sum per-call and are labelled inflated relative to totals.toolSec
    # (which uses the batch span) — assert the label exists and the two views can diverge.
    assert "inflated" in agg["toolTime"]["byClassNote"]
    per_call_sum = sum(v["sec"] for v in agg["toolTime"]["byClass"].values())
    assert per_call_sum == 35.0  # 5 + 30, an independent per-call sum from this fixture's
    # single-session toolSec=0.0 above — demonstrating byClass is not derived from toolSec.


def _resolve_paths_selftest() -> None:
    """run-dir resolution: explicit flags win; else resolved run-dir; else legacy cwd
    filenames — same contract as analyze.py's."""
    import tempfile

    orig_root, orig_latest = _rundir.RETROS_ROOT, _rundir.LATEST_POINTER
    tmpdir = tempfile.mkdtemp()
    _rundir.RETROS_ROOT = os.path.join(tmpdir, "retros")
    _rundir.LATEST_POINTER = os.path.join(_rundir.RETROS_ROOT, "latest")
    try:
        assert resolve_paths(None, None, None) == ("identify.json", "wallclock.json")

        run_dir, _ = _rundir.new_run_dir("20260101-000000-deadbeef")
        _rundir.write_latest_pointer(run_dir)
        assert resolve_paths(None, None, None) == (
            os.path.join(run_dir, "identify.json"),
            os.path.join(run_dir, "wallclock.json"),
        )
        assert resolve_paths(None, "custom.json", None) == (
            os.path.join(run_dir, "identify.json"),
            "custom.json",
        )
        assert resolve_paths(None, None, "/explicit/dir") == (
            "/explicit/dir/identify.json",
            "/explicit/dir/wallclock.json",
        )
    finally:
        _rundir.RETROS_ROOT, _rundir.LATEST_POINTER = orig_root, orig_latest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="infile", default=None, help="identify.json path (default: <run-dir>/identify.json)")
    parser.add_argument("--out", default=None, help="default: <run-dir>/wallclock.json")
    parser.add_argument("--run-dir", dest="run_dir", default=None, help="run-dir to resolve identify.json/wallclock.json in (default: latest pointer, else cwd)")
    parser.add_argument("--top", type=int, default=20, help="how many examples to keep per top-N list")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    infile, out = resolve_paths(args.infile, args.out, args.run_dir)
    with open(infile, encoding="utf-8") as fh:
        ident = json.load(fh)
    sessions = [
        walk_session(s["path"], s["sessionId"])
        for s in ident["sessions"]
        if os.path.exists(s["path"])
    ]
    result = aggregate(sessions, args.top)
    result["meta"] = {
        "sourceIdentify": infile,
        "window": ident.get("window"),
        "sessionCount": len(sessions),
        "timingModel": {
            "inference": "ts(last assistant record of a requestId) - ts(record before the "
            "first); includes thinking, streaming, retries — not pure provider latency.",
            "tool": "ts(tool_result record) - ts(assistant record carrying the tool_use); "
            "parallel calls in one message use the batch span (max result ts - assistant ts), "
            "not a per-call sum.",
            "humanIdle": "ts(human prompt) - ts(previous record), only when the previous "
            "assistant turn ended without a tool_use.",
            "caveat": TIMING_CAVEAT,
        },
        "thresholds": {
            "parkedSec": PARKED_SEC,
            "slowTurnSec": SLOW_TURN_SEC,
            "approvalGateSec": APPROVAL_GATE_SEC,
            "mergeWindowSec": MERGE_WINDOW_SEC,
            "churnMinRuns": CHURN_MIN_RUNS,
        },
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    print(f"wallclock.py: {len(sessions)} sessions -> {out}")


if __name__ == "__main__":
    main()
