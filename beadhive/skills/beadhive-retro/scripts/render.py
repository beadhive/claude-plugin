#!/usr/bin/env python3
"""Opt-in artifact: render analysis.json into a single self-contained report.html.

Stdlib only, inline CSS, no JS framework. Reads analysis.json from a run-dir (see
../SKILL.md's "artifact mode") and writes report.html next to it. Every number in the output
is read straight from analysis.json — this script does no new aggregation of its own beyond
simple grounded roll-ups (sums/filters) for the recommendations section.

By default, resolves analysis.json/writes report.html in the same run-dir as identify.py:
explicit `--run-dir` wins, else the `latest` pointer, else legacy cwd-relative defaults.
`--in`/`--out` always override individually.

Usage:
    render.py [--in analysis.json] [--out report.html] [--run-dir DIR]
    render.py --selftest
"""
from __future__ import annotations

import argparse
import html
import json
import os

import _rundir

# ---------------------------------------------------------------------------
# Beadhive honeycomb brand palette — mirrors ../references/palette.md verbatim.
# Keep these two files in sync by hand (palette.md is the single source of
# truth; this is just its "Chart chrome & ink" + brand-accent rows hardcoded
# as CSS-ready constants, not parsed from markdown).
# ---------------------------------------------------------------------------
BRAND = {
    "surface": "#17140c",
    "surface_panel": "#2a2413",  # hex-grid tint
    "surface_page": "#0a0702",
    "ink_primary": "#f3e9d5",  # cream ink
    "ink_secondary": "#c8972e",  # bronze
    "ink_muted": "#a99a79",  # muted-tan
    "accent": "#f2b617",  # amber, brand primary
    "gridline": "#2a2413",
    "border": "rgba(243,233,213,0.12)",
    "good": "#409d48",
}


def esc(value) -> str:
    return html.escape(str(value))


def fmt_int(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return esc(n)


def fmt_usd(n) -> str:
    try:
        return f"${float(n):,.2f}"
    except (TypeError, ValueError):
        return esc(n)


def fmt_pct(n) -> str:
    try:
        return f"{float(n):.1f}%"
    except (TypeError, ValueError):
        return esc(n)


def table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return "<p class='empty'>No data.</p>"
    thead = "".join(f"<th>{esc(h)}</th>" for h in headers)
    trs = []
    for row in rows:
        tds = "".join(f"<td>{esc(c)}</td>" for c in row)
        trs.append(f"<tr>{tds}</tr>")
    return f"<table><thead><tr>{thead}</tr></thead><tbody>{''.join(trs)}</tbody></table>"


def section(title: str, anchor: str, body: str, note: str | None = None) -> str:
    note_html = f"<p class='note'>{esc(note)}</p>" if note else ""
    return f"<section id='{esc(anchor)}'><h2>{esc(title)}</h2>{note_html}{body}</section>"


# ---------------------------------------------------------------------------
# Section builders — each reads one analysis.json family, renders it verbatim.
# ---------------------------------------------------------------------------


def render_lifecycle(lifecycle: dict) -> str:
    by_epic = lifecycle.get("byEpic", {})
    rows = [
        [epic, counts.get("planned", 0), counts.get("implemented", 0), counts.get("merged", 0)]
        for epic, counts in sorted(by_epic.items())
    ]
    body = table(["Epic", "Planned", "Implemented", "Merged"], rows)
    return section(
        "Lifecycle",
        "lifecycle",
        body,
        note=f"source: {lifecycle.get('source', 'unknown')} (offline id-heuristic, not a verified parent link)",
    )


def render_tokens(tokens: dict) -> str:
    exact = tokens.get("exact", {})
    totals = exact.get("totals", {})
    pct = exact.get("percentOfTotal", {})
    rows = [[k, fmt_int(v), fmt_pct(pct.get(k, 0))] for k, v in totals.items()]
    body = table(["Category", "Tokens", "% of total"], rows)
    approx = tokens.get("approximateFileIo", {})
    body += (
        "<p class='note'>approximate file I/O (chars/4, not exact): "
        f"read ≈ {fmt_int(approx.get('readTokensApprox', 0))} tokens, "
        f"write ≈ {fmt_int(approx.get('writeTokensApprox', 0))} tokens</p>"
    )
    return section("Tokens", "tokens", body)


def render_cache(cache: dict, cache_waste_usd) -> str:
    body = f"<p class='stat'>cache ratio: <strong>{fmt_pct(cache.get('cacheRatio', 0))}</strong></p>"
    significant = [e for e in cache.get("expiryEvents", []) if e.get("significant")]
    rows = [
        [e.get("sessionId"), e.get("ts"), f"{e.get('idleGapSeconds', 0):.0f}s", fmt_int(e.get("wastedTokens", 0))]
        for e in significant
    ]
    body += table(["Session", "Timestamp", "Idle gap", "Wasted tokens"], rows)
    body += (
        f"<p class='note'>{len(significant)} significant cache-expiry event(s) shown "
        f"(wasted ≥ 10,000 tokens); est. cache-waste cost across all expiry events: "
        f"{fmt_usd(cache_waste_usd)} (cost.cacheWasteUSD)</p>"
    )
    return section("Cache", "cache", body)


def render_models(models: dict) -> str:
    by_session = models.get("bySession", {})
    rows = [
        [sid, ", ".join(info.get("models", [])), info.get("dominant")]
        for sid, info in sorted(by_session.items())
    ]
    body = table(["Session", "Models used", "Dominant"], rows)

    beads_by_model = models.get("beadsByModel", {})
    rows2 = [
        [model, counts.get("planned", 0), counts.get("implemented", 0), counts.get("merged", 0)]
        for model, counts in sorted(beads_by_model.items())
    ]
    body += "<h3>Bead lifecycle events by model</h3>"
    body += table(["Model", "Planned", "Implemented", "Merged"], rows2)
    return section(
        "Models",
        "models",
        body,
        note="model attribution is approximate (ts→model join) per metrics.md (f)",
    )


def render_cost(cost: dict) -> str:
    by_model = cost.get("byModel", {})
    rows = [
        [
            family,
            fmt_usd(entry.get("inputCost", 0)),
            fmt_usd(entry.get("outputCost", 0)),
            fmt_usd(entry.get("cacheReadCost", 0)),
            fmt_usd(entry.get("cacheWriteCost", 0)),
            fmt_usd(entry.get("totalCost", 0)),
        ]
        for family, entry in sorted(by_model.items())
    ]
    body = table(["Family", "Input", "Output", "Cache read", "Cache write", "Total"], rows)
    body += f"<p class='stat'>grand total (estimate): <strong>{fmt_usd(cost.get('total', 0))}</strong></p>"

    unpriced = cost.get("unpriced", {})
    unpriced_models = unpriced.get("models", [])
    if unpriced_models:
        unpriced_tokens = sum(
            unpriced.get(k, 0) for k in ("input", "output", "cache_read", "eph5m", "eph1h")
        )
        body += (
            f"<p class='note'>unpriced model families (not included above): {esc(', '.join(unpriced_models))} "
            f"— {fmt_int(unpriced_tokens)} raw tokens</p>"
        )

    return section(
        "Cost",
        "cost",
        body,
        note=f"estimate only, not a billed figure; pricing as of {cost.get('pricingAsOf', 'unknown')} "
        "(references/pricing.json)",
    )


def render_failures(failures: dict) -> str:
    rows = []
    for bucket_name, bucket in failures.items():
        for tool, count in bucket.items():
            rows.append([bucket_name, tool, count])
    body = table(["Bucket", "Tool", "Failure count"], sorted(rows, key=lambda r: (-r[2], r[0], r[1])))
    return section("Failures", "failures", body)


def render_skills(skill_reads: dict) -> str:
    invocations = skill_reads.get("invocations", {})
    rows = []
    for bucket_name, bucket in invocations.items():
        for skill, count in bucket.items():
            rows.append([bucket_name, skill, count])
    body = table(["Bucket", "Skill", "Invocations"], sorted(rows, key=lambda r: (-r[2], r[0], r[1])))
    body += f"<p class='stat'>SKILL.md reads: <strong>{fmt_int(skill_reads.get('skillMdReads', 0))}</strong></p>"
    return section("Skills", "skills", body)


def render_activity(activity: dict) -> str:
    rows = [
        [
            sid,
            info["counts"].get("planning", 0),
            info["counts"].get("implementing", 0),
            info["counts"].get("diagnosing", 0),
            info["counts"].get("fixing", 0),
            info.get("suggested"),
        ]
        for sid, info in sorted(activity.items())
    ]
    body = table(["Session", "Planning", "Implementing", "Diagnosing", "Fixing", "Suggested"], rows)
    return section(
        "Activity",
        "activity",
        body,
        note="counts are raw signal counts, not a forced label; suggested is a best-effort argmax",
    )


# ---------------------------------------------------------------------------
# Recommendations — simple, mechanical, grounded roll-ups of the same fields
# above. Never invents a number; every bullet cites one already in analysis.json.
# ---------------------------------------------------------------------------

CACHE_CALLOUT_LIMIT = 5


def generate_recommendations(analysis: dict) -> dict:
    usage = []
    product = []

    cache = analysis.get("cache", {})
    significant = [e for e in cache.get("expiryEvents", []) if e.get("significant")]
    for e in significant[:CACHE_CALLOUT_LIMIT]:
        usage.append(
            f"Handoff opportunity in session {e.get('sessionId')} at {e.get('ts')}: cache expired "
            f"after a {e.get('idleGapSeconds', 0):.0f}s idle gap, wasting "
            f"{fmt_int(e.get('wastedTokens', 0))} tokens."
        )

    cost = analysis.get("cost", {})
    unpriced = cost.get("unpriced", {})
    unpriced_models = unpriced.get("models", [])
    unpriced_tokens = sum(unpriced.get(k, 0) for k in ("input", "output", "cache_read", "eph5m", "eph1h"))
    if unpriced_models:
        usage.append(
            f"{fmt_int(unpriced_tokens)} tokens were spent on unpriced model family/families "
            f"({', '.join(unpriced_models)}) — cost estimates above exclude them."
        )

    failures = analysis.get("failures", {})
    beads_bh_failures = sum(failures.get("beadsBh", {}).values())
    if beads_bh_failures:
        breakdown = ", ".join(f"{tool}: {n}" for tool, n in failures.get("beadsBh", {}).items())
        usage.append(f"{beads_bh_failures} failed bd/bh tool call(s) ({breakdown}) — worth a look in events.jsonl.")

    skill_md_reads = analysis.get("skillReads", {}).get("skillMdReads", 0)
    if skill_md_reads > 2:
        usage.append(f"SKILL.md was read {skill_md_reads} times across sessions — a shorter refresher pointer may cut repeat reads.")

    meta = analysis.get("meta", {})
    version_stamp = f"observed on bh {meta.get('bhVersion', 'unknown')} (CC {', '.join(meta.get('ccVersions', []) or ['unknown'])})"
    if unpriced_models:
        product.append(
            f"pricing.json has no rate for model family/families {', '.join(unpriced_models)} "
            f"({fmt_int(unpriced_tokens)} raw tokens went unpriced) — {version_stamp}."
        )
    if beads_bh_failures:
        breakdown = ", ".join(f"{tool}: {n}" for tool, n in failures.get("beadsBh", {}).items())
        product.append(f"{beads_bh_failures} bd/bh tool call(s) failed ({breakdown}) — {version_stamp}.")

    return {"usagePattern": usage, "productImprovements": product[:3]}


def render_recommendations(recs: dict) -> str:
    def bullets(items):
        if not items:
            return "<p class='empty'>None grounded in this run's data.</p>"
        return "<ul>" + "".join(f"<li>{esc(item)}</li>" for item in items) + "</ul>"

    body = "<h3>Usage-pattern (for you)</h3>" + bullets(recs["usagePattern"])
    body += "<h3>Beadhive product improvements (for maintainers)</h3>" + bullets(recs["productImprovements"])
    return section("Recommendations", "recommendations", body)


# Old unstyled fallback — kept behind --plain, not the default.
PLAIN_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0;
       padding: 2rem; max-width: 960px; margin-inline: auto; color: #1a1a1a; line-height: 1.5; }
h1 { margin-bottom: 0.25rem; }
h2 { border-bottom: 2px solid #ddd; padding-bottom: 0.25rem; margin-top: 2.5rem; }
h3 { margin-top: 1.5rem; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.9rem; }
th, td { border: 1px solid #ddd; padding: 0.4rem 0.6rem; text-align: left; }
th { background: #f4f4f4; }
tr:nth-child(even) { background: #fafafa; }
.note { color: #666; font-size: 0.85rem; font-style: italic; }
.stat { font-size: 1.05rem; }
.empty { color: #888; font-style: italic; }
nav { margin: 1.5rem 0; }
nav a { margin-right: 1rem; }
footer { margin-top: 3rem; color: #888; font-size: 0.8rem; }
"""

# Branded, dark-first honeycomb theme — the default. Values sourced from
# ../references/palette.md's "Chart chrome & ink" table; keep the two in sync.
BRANDED_CSS = f"""
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0;
       padding: 2rem; max-width: 960px; margin-inline: auto; line-height: 1.5;
       background: {BRAND['surface']}; color: {BRAND['ink_primary']}; }}
h1 {{ margin-bottom: 0.25rem; color: {BRAND['accent']}; letter-spacing: 0.01em; }}
h2 {{ border-bottom: 2px solid {BRAND['gridline']}; padding-bottom: 0.25rem; margin-top: 2.5rem;
     color: {BRAND['accent']}; }}
h3 {{ margin-top: 1.5rem; color: {BRAND['ink_secondary']}; }}
a {{ color: {BRAND['ink_secondary']}; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.9rem; }}
th, td {{ border: 1px solid {BRAND['border']}; padding: 0.4rem 0.6rem; text-align: left; }}
th {{ background: {BRAND['surface_panel']}; color: {BRAND['ink_primary']}; }}
tr:nth-child(even) {{ background: {BRAND['surface_panel']}; }}
.note {{ color: {BRAND['ink_muted']}; font-size: 0.85rem; font-style: italic; }}
.stat {{ font-size: 1.05rem; color: {BRAND['ink_primary']}; }}
.stat strong {{ color: {BRAND['accent']}; }}
.empty {{ color: {BRAND['ink_muted']}; font-style: italic; }}
nav {{ margin: 1.5rem 0; }}
nav a {{ margin-right: 1rem; }}
footer {{ margin-top: 3rem; color: {BRAND['ink_muted']}; font-size: 0.8rem;
         border-top: 1px solid {BRAND['border']}; padding-top: 1rem; }}
"""

SECTION_ORDER = [
    ("lifecycle", "Lifecycle"),
    ("tokens", "Tokens"),
    ("cache", "Cache"),
    ("models", "Models"),
    ("cost", "Cost"),
    ("failures", "Failures"),
    ("skills", "Skills"),
    ("activity", "Activity"),
    ("recommendations", "Recommendations"),
]


def render_html(analysis: dict, plain: bool = False) -> str:
    meta = analysis.get("meta", {})
    cost = analysis.get("cost", {})
    recs = generate_recommendations(analysis)

    nav = " ".join(f"<a href='#{anchor}'>{label}</a>" for anchor, label in SECTION_ORDER)
    body_sections = "\n".join(
        [
            render_lifecycle(analysis.get("lifecycle", {})),
            render_tokens(analysis.get("tokens", {})),
            render_cache(analysis.get("cache", {}), cost.get("cacheWasteUSD", 0)),
            render_models(analysis.get("models", {})),
            render_cost(cost),
            render_failures(analysis.get("failures", {})),
            render_skills(analysis.get("skillReads", {})),
            render_activity(analysis.get("activity", {})),
            render_recommendations(recs),
        ]
    )

    css = PLAIN_CSS if plain else BRANDED_CSS
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Beadhive Retro Report</title>
<style>{css}</style>
</head>
<body>
<h1>Beadhive Retro Report</h1>
<p class="note">generated {esc(meta.get('generatedAt', 'unknown'))} · bh {esc(meta.get('bhVersion', 'unknown'))}
· CC {esc(', '.join(meta.get('ccVersions', []) or ['unknown']))} · pricing as of {esc(cost.get('pricingAsOf', 'unknown'))}</p>
<nav>{nav}</nav>
{body_sections}
<footer>Rendered by beadhive-retro's render.py from analysis.json. All figures are estimates
derived from Claude Code session transcripts — never billed/verified numbers.</footer>
</body>
</html>
"""


def resolve_paths(infile, out, run_dir_arg) -> tuple[str, str]:
    """(infile, out) with explicit flags winning, else the resolved run-dir, else legacy
    cwd-relative filenames."""
    run_dir = _rundir.resolve_run_dir(run_dir_arg)
    infile = infile or (os.path.join(run_dir, "analysis.json") if run_dir else "analysis.json")
    out = out or (os.path.join(run_dir, "report.html") if run_dir else "report.html")
    return infile, out


def selftest() -> None:
    import os as _os
    import tempfile

    analysis = {
        "lifecycle": {"source": "id-heuristic", "byEpic": {"bh-cp-1": {"planned": 1, "implemented": 1, "merged": 0}}},
        "failures": {"beadsBh": {"Bash": 2}, "other": {}},
        "skillReads": {"invocations": {"bhBeads": {"bh:planner": 3}, "other": {}}, "skillMdReads": 5},
        "tokens": {
            "exact": {"totals": {"input": 100, "output": 200, "cache_read": 50, "cache_creation": 10}, "percentOfTotal": {"input": 27.8, "output": 55.6, "cache_read": 13.9, "cache_creation": 2.8}},
            "approximateFileIo": {"approximate": True, "readTokensApprox": 40, "writeTokensApprox": 10},
        },
        "cache": {
            "cacheRatio": 0.42,
            "expiryEvents": [
                {"sessionId": "sess-1", "ts": "2026-07-20T10:20:00Z", "idleGapSeconds": 1200, "wastedTokens": 12000, "significant": True, "wastedEph5m": 4000, "wastedEph1h": 8000}
            ],
            "significantExpiryEventCount": 1,
        },
        "activity": {"sess-1": {"counts": {"planning": 1, "implementing": 2, "diagnosing": 0, "fixing": 1}, "suggested": "implementing"}},
        "models": {
            "byModel": {},
            "bySession": {"sess-1": {"models": ["claude-sonnet-5"], "dominant": "claude-sonnet-5"}},
            "beadsByModel": {"claude-sonnet-5": {"planned": 1, "implemented": 1, "merged": 0}},
            "attributionApproximate": True,
        },
        "cost": {
            "byModel": {"sonnet": {"inputCost": 0.3, "outputCost": 3.0, "cacheReadCost": 0.01, "cacheWriteCost": 0.05, "totalCost": 3.36}},
            "unpriced": {"input": 5, "output": 0, "cache_read": 0, "eph5m": 0, "eph1h": 0, "models": ["claude-mystery-1"]},
            "total": 3.36,
            "cacheWasteUSD": 0.07,
            "currency": "USD",
            "pricingAsOf": "2026-07",
            "approximate": True,
        },
        "meta": {"bhVersion": "bd version 1.1.0", "ccVersions": ["2.1.207"], "pricingAsOf": "2026-07", "generatedAt": "2026-07-23T19:46:26Z"},
    }

    out_html = render_html(analysis)

    assert out_html.startswith("<!DOCTYPE html>")
    assert out_html.rstrip().endswith("</html>")
    assert "bh-cp-1" in out_html
    assert "sess-1" in out_html
    assert "12,000" in out_html  # wasted tokens, comma-formatted
    assert "$3.36" in out_html  # cost.byModel.sonnet.totalCost
    assert "claude-mystery-1" in out_html  # unpriced model surfaced, not dropped
    assert "$0.07" in out_html  # cacheWasteUSD cited beside the cache-expiry callout
    assert "claude-sonnet-5" in out_html
    assert "Handoff opportunity in session sess-1" in out_html  # recommendation grounded in the expiry event
    assert "pricing.json has no rate for model family/families claude-mystery-1" in out_html
    assert "observed on bh bd version 1.1.0" in out_html

    recs = generate_recommendations(analysis)
    assert len(recs["usagePattern"]) >= 1
    assert len(recs["productImprovements"]) <= 3

    # branded-by-default: no flag needed, honeycomb palette hex values present.
    assert BRAND["surface"] in out_html
    assert BRAND["accent"] in out_html
    assert BRAND["ink_secondary"] in out_html
    assert "PLAIN_CSS" not in out_html  # sanity: didn't leak the variable name itself

    # --plain escape hatch: old unstyled gray theme, no brand hex present.
    plain_html = render_html(analysis, plain=True)
    assert BRAND["surface"] not in plain_html
    assert BRAND["accent"] not in plain_html
    assert "#1a1a1a" in plain_html  # old plain body color still there
    assert plain_html.startswith("<!DOCTYPE html>")

    # run-dir resolution: explicit flags win; else resolved run-dir; else legacy cwd filenames.
    orig_root, orig_latest = _rundir.RETROS_ROOT, _rundir.LATEST_POINTER
    tmpdir = tempfile.mkdtemp()
    _rundir.RETROS_ROOT = _os.path.join(tmpdir, "retros")
    _rundir.LATEST_POINTER = _os.path.join(_rundir.RETROS_ROOT, "latest")
    try:
        assert resolve_paths(None, None, None) == ("analysis.json", "report.html")

        run_dir, _ = _rundir.new_run_dir("20260101-000000-deadbeef")
        _rundir.write_latest_pointer(run_dir)
        assert resolve_paths(None, None, None) == (
            _os.path.join(run_dir, "analysis.json"),
            _os.path.join(run_dir, "report.html"),
        )
        assert resolve_paths(None, "custom.html", None) == (
            _os.path.join(run_dir, "analysis.json"),
            "custom.html",
        )
        assert resolve_paths(None, None, "/explicit/dir") == (
            "/explicit/dir/analysis.json",
            "/explicit/dir/report.html",
        )
    finally:
        _rundir.RETROS_ROOT, _rundir.LATEST_POINTER = orig_root, orig_latest

    print("render.py --selftest: OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="infile", default=None, help="analysis.json path (default: <run-dir>/analysis.json)")
    parser.add_argument("--out", default=None, help="default: <run-dir>/report.html")
    parser.add_argument("--run-dir", dest="run_dir", default=None, help="run-dir to resolve analysis.json/report.html in (default: latest pointer, else cwd)")
    parser.add_argument(
        "--plain", action="store_true",
        help="render the old unstyled gray theme instead of the branded honeycomb default",
    )
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    infile, out = resolve_paths(args.infile, args.out, args.run_dir)
    with open(infile) as f:
        analysis = json.load(f)

    with open(out, "w") as f:
        f.write(render_html(analysis, plain=args.plain))

    print(f"render.py: rendered {infile} -> {out}")


if __name__ == "__main__":
    main()
