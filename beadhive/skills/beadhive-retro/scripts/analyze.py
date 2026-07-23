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
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

BEAD_ID_RE = re.compile(r"\bbh-[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[0-9]+)?\b")

PLANNED_RE = re.compile(r"^(bd create|bh plan)\b")
IMPLEMENTED_RE = re.compile(r"^(bh work submit|bd close)\b")
MERGED_RE = re.compile(r"^bh work (merge|finish)\b")

CHARS_PER_TOKEN = 4
IDLE_GAP_SECONDS = 5 * 60
CACHE_MISS_RATIO = 0.5
RECREATION_SPIKE_TOKENS = 5000
SIGNIFICANT_WASTED_TOKENS = 10000

PRICING_PATH = Path(__file__).resolve().parent.parent / "references" / "pricing.json"


def parse_ts(ts: str):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def epic_of(bead_id: str) -> str:
    """Offline id-heuristic: strip a trailing '.N' child suffix to infer the parent epic."""
    return bead_id.split(".")[0]


def load_pricing(path=PRICING_PATH) -> dict:
    with open(path) as f:
        return json.load(f)


def model_family(model_id, pricing: dict):
    """Map a raw model id to a pricing.json family by substring match. None if no known
    family substring is found in the id (an unpriced/unknown model)."""
    if not model_id:
        return None
    for family in pricing.get("models", {}):
        if family in model_id:
            return family
    return None


def ts_model_index(session: dict) -> dict:
    """ts -> model, built from a session's usageSeries. See metrics.md (f): approximate —
    a later same-ts entry wins on collision."""
    index = {}
    for u in session.get("usageSeries", []):
        if u.get("ts"):
            index[u["ts"]] = u.get("model")
    return index


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
                    # split by actual TTL bucket so cost pricing (write5m vs write1h rate) is
                    # exact rather than assuming all waste was a 5m-TTL write.
                    "wastedEph5m": cur.get("eph5m", 0),
                    "wastedEph1h": cur.get("eph1h", 0),
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


def analyze_models(sessions: list) -> dict:
    """(f) models family: byModel usage split main/sidechain, per-session dominant model, and
    bead lifecycle events attributed to the model active at that event's ts (approximate)."""
    by_model = {}

    def bucket(model_id, is_sidechain):
        m = by_model.setdefault(
            model_id or "unknown",
            {
                "main": {"messages": 0, "sessions": set(), "input": 0, "output": 0, "cache_read": 0, "eph5m": 0, "eph1h": 0},
                "sidechain": {"messages": 0, "sessions": set(), "input": 0, "output": 0, "cache_read": 0, "eph5m": 0, "eph1h": 0},
            },
        )
        return m["sidechain"] if is_sidechain else m["main"]

    by_session = {}
    for session in sessions:
        session_totals = {}  # model_id -> token total, for dominant
        models_seen = set()
        for u in session["usageSeries"]:
            model_id = u.get("model") or "unknown"
            models_seen.add(model_id)
            b = bucket(model_id, u.get("isSidechain", False))
            b["messages"] += 1
            b["sessions"].add(session["sessionId"])
            b["input"] += u["input"]
            b["output"] += u["output"]
            b["cache_read"] += u["cache_read"]
            b["eph5m"] += u.get("eph5m", 0)
            b["eph1h"] += u.get("eph1h", 0)
            total = u["input"] + u["output"] + u["cache_read"] + u.get("cache_creation", 0)
            session_totals[model_id] = session_totals.get(model_id, 0) + total
        dominant = max(session_totals, key=session_totals.get) if session_totals else None
        by_session[session["sessionId"]] = {"models": sorted(models_seen), "dominant": dominant}

    for entry in by_model.values():
        for bucket_data in (entry["main"], entry["sidechain"]):
            bucket_data["sessions"] = len(bucket_data["sessions"])

    # beadsByModel: same lifecycle-stage detection as (a), re-bucketed by the model attributed
    # via the ts->model join instead of by epic. Shares the same (stage, bead_id) dedup as
    # analyze_lifecycle so per-stage totals reconcile across the two groupings.
    seen = set()
    beads_by_model = {}
    for session in sessions:
        ts_model = ts_model_index(session)
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
                model_id = ts_model.get(event.get("ts")) or "unknown"
                bucket = beads_by_model.setdefault(model_id, {"planned": 0, "implemented": 0, "merged": 0})
                bucket[stage] += 1

    return {
        "byModel": by_model,
        "bySession": by_session,
        "beadsByModel": beads_by_model,
        "attributionApproximate": True,
    }


def _token_cost(tokens: int, per_m: float) -> float:
    return tokens / 1_000_000 * per_m


def analyze_cost(sessions: list, pricing: dict, cache: dict) -> dict:
    """(g) cost family: per-family estimated USD from pricing.json, plus cacheWasteUSD priced
    from cache.expiryEvents at the write rate. Always an estimate — never billed precision."""
    multipliers = pricing.get("cacheMultipliers", {})
    read_mult = multipliers.get("read", 0)
    write5m_mult = multipliers.get("write5m", 0)
    write1h_mult = multipliers.get("write1h", 0)

    by_family = {}
    unpriced = {"input": 0, "output": 0, "cache_read": 0, "eph5m": 0, "eph1h": 0, "models": set()}

    for session in sessions:
        for u in session["usageSeries"]:
            model_id = u.get("model")
            family = model_family(model_id, pricing)
            if family is None:
                unpriced["input"] += u["input"]
                unpriced["output"] += u["output"]
                unpriced["cache_read"] += u["cache_read"]
                unpriced["eph5m"] += u.get("eph5m", 0)
                unpriced["eph1h"] += u.get("eph1h", 0)
                unpriced["models"].add(model_id or "unknown")
                continue

            rates = pricing["models"][family]
            in_rate = rates["inputPerM"]
            out_rate = rates["outputPerM"]

            entry = by_family.setdefault(
                family, {"inputCost": 0.0, "outputCost": 0.0, "cacheReadCost": 0.0, "cacheWriteCost": 0.0}
            )
            entry["inputCost"] += _token_cost(u["input"], in_rate)
            entry["outputCost"] += _token_cost(u["output"], out_rate)
            entry["cacheReadCost"] += _token_cost(u["cache_read"], in_rate) * read_mult
            entry["cacheWriteCost"] += (
                _token_cost(u.get("eph5m", 0), in_rate) * write5m_mult
                + _token_cost(u.get("eph1h", 0), in_rate) * write1h_mult
            )

    for entry in by_family.values():
        entry["totalCost"] = (
            entry["inputCost"] + entry["outputCost"] + entry["cacheReadCost"] + entry["cacheWriteCost"]
        )

    total = sum(entry["totalCost"] for entry in by_family.values())
    unpriced["models"] = sorted(unpriced["models"])

    # cacheWasteUSD: price every cache.expiryEvents entry's wasted tokens at that event's
    # attributed model family's cache-write rate, split by the actual eph5m/eph1h TTL bucket
    # (not a flat 5m assumption — a wasted 1h-TTL write costs more per token than a 5m one).
    # Skip events whose attributed model is unpriced.
    session_ts_model = {s["sessionId"]: ts_model_index(s) for s in sessions}
    cache_waste_usd = 0.0
    for event in cache.get("expiryEvents", []):
        ts_model = session_ts_model.get(event["sessionId"], {})
        model_id = ts_model.get(event["ts"])
        family = model_family(model_id, pricing)
        if family is None:
            continue
        in_rate = pricing["models"][family]["inputPerM"]
        cache_waste_usd += (
            _token_cost(event.get("wastedEph5m", 0), in_rate) * write5m_mult
            + _token_cost(event.get("wastedEph1h", 0), in_rate) * write1h_mult
        )

    return {
        "byModel": by_family,
        "unpriced": unpriced,
        "total": total,
        "cacheWasteUSD": cache_waste_usd,
        "currency": "USD",
        "pricingAsOf": pricing.get("asOf"),
        "approximate": True,
        "note": "estimate; transcripts carry no raw cost (costUSD absent) — computed from "
        "references/pricing.json, not a billed figure.",
    }


def bh_version() -> str:
    """Best-effort maintainer-recommendation version stamp: `bh version`, falling back to
    `bd version`, else 'unknown'. Never raises."""
    for cmd in (["bh", "version"], ["bd", "version"]):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            continue
        output = (result.stdout or result.stderr or "").strip()
        if result.returncode == 0 and output:
            return output
    return "unknown"


def analyze_meta(sessions: list, pricing: dict) -> dict:
    cc_versions = sorted({v for s in sessions for v in s.get("ccVersions", [])})
    return {
        "bhVersion": bh_version(),
        "ccVersions": cc_versions,
        "pricingAsOf": pricing.get("asOf"),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def analyze(sessions: list, pricing: dict = None) -> dict:
    if pricing is None:
        pricing = load_pricing()
    cache = analyze_cache(sessions)
    return {
        "lifecycle": analyze_lifecycle(sessions),
        "failures": analyze_failures(sessions),
        "skillReads": analyze_skill_reads(sessions),
        "tokens": analyze_tokens(sessions),
        "cache": cache,
        "activity": analyze_activity(sessions),
        "models": analyze_models(sessions),
        "cost": analyze_cost(sessions, pricing, cache),
        "meta": analyze_meta(sessions, pricing),
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
                    # idle gap > 5m, cache_read collapses, cache_creation spikes >= 5000: expiry
                    # event. Split across both TTL buckets to exercise wastedEph5m/wastedEph1h.
                    "ts": "2026-07-20T10:20:00Z",
                    "input": 5,
                    "output": 15,
                    "cache_read": 10,
                    "cache_creation": 12000,
                    "eph5m": 4000,
                    "eph1h": 8000,
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
    assert ev["wastedEph5m"] == 4000
    assert ev["wastedEph1h"] == 8000
    assert ev["significant"] is True
    assert cache["significantExpiryEventCount"] == 1

    activity = result["activity"]["s1"]["counts"]
    assert activity["planning"] >= 1
    assert activity["implementing"] >= 1
    assert activity["fixing"] >= 1  # Edit at 10:30 immediately follows the error turn at 10:25
    assert activity["diagnosing"] >= 1  # Read+Skill at 10:35, no Edit on that turn

    # load_pricing() reads references/pricing.json relative to this script.
    loaded_pricing = load_pricing()
    assert "sonnet" in loaded_pricing["models"]
    assert loaded_pricing.get("asOf")

    # --- two-model synthetic: models / cost / meta / beadsByModel attribution ---
    # A fixed pricing table (independent of the user-editable pricing.json contents) so this
    # test's "known cost" stays hand-checkable even if a user re-rates pricing.json.
    test_pricing = {
        "asOf": "2026-07",
        "cacheMultipliers": {"read": 0.1, "write5m": 1.25, "write1h": 2.0},
        "models": {
            "sonnet": {"inputPerM": 3.00, "outputPerM": 15.00},
            "opus": {"inputPerM": 5.00, "outputPerM": 25.00},
            "haiku": {"inputPerM": 1.00, "outputPerM": 5.00},
        },
        "default": "sonnet",
    }
    model_sessions = [
        {
            "sessionId": "s2",
            "ccVersions": ["9.9.9"],
            "usageSeries": [
                {
                    "ts": "2026-07-21T09:00:00Z",
                    "input": 1_000_000,
                    "output": 1_000_000,
                    "cache_read": 0,
                    "cache_creation": 0,
                    "eph5m": 0,
                    "eph1h": 0,
                    "isSidechain": False,
                    "model": "claude-sonnet-5",
                },
                {
                    # idle gap == 5m, cache collapses from 0, cache_creation spikes: an
                    # attributable (opus) cache-expiry event -> hand-checks cacheWasteUSD.
                    # Split across both TTL buckets to exercise the write5m/write1h split.
                    "ts": "2026-07-21T09:05:00Z",
                    "input": 1_000_000,
                    "output": 0,
                    "cache_read": 1_000_000,
                    "cache_creation": 1_000_000,
                    "eph5m": 600_000,
                    "eph1h": 400_000,
                    "isSidechain": False,
                    "model": "claude-opus-4-20250514",
                },
                {
                    # unknown/unpriced family -> must land in cost.unpriced, not be dropped.
                    "ts": "2026-07-21T09:10:00Z",
                    "input": 2_000_000,
                    "output": 0,
                    "cache_read": 0,
                    "cache_creation": 0,
                    "eph5m": 0,
                    "eph1h": 0,
                    "isSidechain": False,
                    "model": "claude-mystery-1",
                },
            ],
            "toolEvents": [
                {"ts": "2026-07-21T09:00:00Z", "tool": "Bash", "detail": "bd create bh-cp-2", "error": False},
                {"ts": "2026-07-21T09:05:00Z", "tool": "Bash", "detail": "bh work submit bh-cp-2", "error": False},
            ],
            "contentSizes": {"readChars": 0, "writeChars": 0},
        }
    ]

    result2 = analyze(model_sessions, pricing=test_pricing)

    models = result2["models"]
    sonnet_main = models["byModel"]["claude-sonnet-5"]["main"]
    assert sonnet_main == {
        "messages": 1, "sessions": 1, "input": 1_000_000, "output": 1_000_000,
        "cache_read": 0, "eph5m": 0, "eph1h": 0,
    }
    opus_main = models["byModel"]["claude-opus-4-20250514"]["main"]
    assert opus_main["input"] == 1_000_000 and opus_main["cache_read"] == 1_000_000
    assert models["bySession"]["s2"]["dominant"] == "claude-opus-4-20250514"
    assert sorted(models["bySession"]["s2"]["models"]) == [
        "claude-mystery-1", "claude-opus-4-20250514", "claude-sonnet-5",
    ]

    # beadsByModel: bh-cp-2 planned under sonnet's ts, implemented under opus's ts.
    assert models["beadsByModel"]["claude-sonnet-5"] == {"planned": 1, "implemented": 0, "merged": 0}
    assert models["beadsByModel"]["claude-opus-4-20250514"] == {"planned": 0, "implemented": 1, "merged": 0}
    # reconciles with lifecycle.byEpic — same underlying events, grouped differently.
    lc2 = result2["lifecycle"]["byEpic"]["bh-cp-2"]
    assert lc2["planned"] == 1 and lc2["implemented"] == 1

    # known cost: sonnet 1M in @ $3/M + 1M out @ $15/M = $18.00; opus 1M in @ $5/M
    # + 1M cache_read @ $5/M*0.1 + (600k eph5m @ $5/M*1.25 + 400k eph1h @ $5/M*2.0)
    # = $5 + $0.50 + ($3.75 + $4.00) = $13.25.
    cost = result2["cost"]
    assert round(cost["byModel"]["sonnet"]["totalCost"], 2) == 18.00
    assert round(cost["byModel"]["opus"]["totalCost"], 2) == 13.25
    assert round(cost["total"], 2) == 31.25
    assert cost["unpriced"]["input"] == 2_000_000
    assert cost["unpriced"]["models"] == ["claude-mystery-1"]
    assert cost["currency"] == "USD"
    assert cost["approximate"] is True
    assert cost["pricingAsOf"] == "2026-07"

    # cacheWasteUSD: the one expiry event's wasted tokens, split 600k eph5m / 400k eph1h,
    # attributed to opus (the ts of the spike), priced at opus's respective write rates:
    # 600k/1M*$5/M*1.25 + 400k/1M*$5/M*2.0 = $3.75 + $4.00 = $7.75 (matches opus's
    # cacheWriteCost exactly, since it's the same tokens at the same rates).
    cache2 = result2["cache"]
    assert len(cache2["expiryEvents"]) == 1
    ev2 = cache2["expiryEvents"][0]
    assert ev2["wastedTokens"] == 1_000_000
    assert ev2["wastedEph5m"] == 600_000
    assert ev2["wastedEph1h"] == 400_000
    assert round(cost["cacheWasteUSD"], 2) == 7.75

    meta = result2["meta"]
    assert meta["ccVersions"] == ["9.9.9"]
    assert meta["pricingAsOf"] == "2026-07"
    assert isinstance(meta["bhVersion"], str) and meta["bhVersion"]
    assert "generatedAt" in meta

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
