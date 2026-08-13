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
from datetime import datetime

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

# Claude Code's internal marker for non-billed synthetic messages -- not a real Claude model.
# It's already excluded from cost.byModel (model_family() returns None for it, so its tokens
# land in cost.unpriced instead); this is the single skip rule for excluding it from every
# other model-attributed display too (models.bySession's "models used" list,
# models.beadsByModel, and the unpriced-models callouts below) -- never duplicate the literal
# string at each call site.
SYNTHETIC_MODEL = "<synthetic>"


def is_synthetic_model(model_id) -> bool:
    return model_id == SYNTHETIC_MODEL


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


def fmt_ratio(n) -> str:
    try:
        return f"{float(n):.1f}×"
    except (TypeError, ValueError):
        return esc(n)


def _humanize_duration(seconds) -> str:
    """Compact human duration for an idle-gap seconds count, e.g. 9951 -> '~2h46m'."""
    try:
        secs = float(seconds)
    except (TypeError, ValueError):
        return "~unknown"
    if secs < 60:
        return f"~{round(secs)}s"
    total_minutes = round(secs / 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"~{hours}h{minutes}m" if minutes else f"~{hours}h"
    return f"~{minutes}m"


def _humanize_ts(ts) -> str:
    """Render an ISO-8601 timestamp as compact, human-readable text; falls back to the raw
    string (or 'unknown time') on anything that doesn't parse -- never raises."""
    if not isinstance(ts, str) or not ts:
        return "unknown time"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return ts


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
        [group, counts.get("planned", 0), counts.get("implemented", 0), counts.get("merged", 0)]
        for group, counts in sorted(by_epic.items())
    ]
    body = table(["Group", "Planned", "Implemented", "Merged"], rows)
    return section(
        "Bead group (by id prefix)",
        "lifecycle",
        body,
        note=(
            f"source: {lifecycle.get('source', 'unknown')} — grouped by bead-id prefix, a "
            "heuristic — not verified epic/parent links; many groups are a single bead."
        ),
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
    body = f"<p class='stat'>cache ratio: <strong>{fmt_ratio(cache.get('cacheRatio', 0))}</strong></p>"
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
    # '<synthetic>' is stripped from both views below -- it's an internal non-billed-message
    # marker, not a real model a session/bead was ever "attributed to" for display purposes
    # (see SYNTHETIC_MODEL). The underlying analysis.json is untouched; this is display-only.
    by_session = models.get("bySession", {})
    rows = [
        [sid, ", ".join(m for m in info.get("models", []) if not is_synthetic_model(m)), info.get("dominant")]
        for sid, info in sorted(by_session.items())
    ]
    body = table(["Session", "Models used", "Dominant"], rows)

    beads_by_model = models.get("beadsByModel", {})
    rows2 = [
        [model, counts.get("planned", 0), counts.get("implemented", 0), counts.get("merged", 0)]
        for model, counts in sorted(beads_by_model.items())
        if not is_synthetic_model(model)
    ]
    body += "<h3>Bead lifecycle events by model</h3>"
    body += table(["Model", "Planned", "Implemented", "Merged"], rows2)
    return section(
        "Models",
        "models",
        body,
        note=(
            "Model attribution is approximate — each tool call is credited to whichever "
            "model's turn shares its timestamp."
        ),
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
    unpriced_models = [m for m in unpriced.get("models", []) if not is_synthetic_model(m)]
    unpriced_tokens = sum(unpriced.get(k, 0) for k in ("input", "output", "cache_read", "eph5m", "eph1h"))
    # Gate on actual unpriced TOKEN VOLUME, not model-list length -- the '<synthetic>' sentinel
    # is always present in unpriced.models with 0 tokens in the normal case, so a
    # models-list-length gate always fired (H1 anchor bug). When there's no real unpriced
    # volume, emit nothing at all.
    if unpriced_tokens > 0:
        body += (
            f"<p class='note'>* Excludes {fmt_int(unpriced_tokens)} tokens from model(s) "
            f"{esc(', '.join(unpriced_models))} with no configured rate — total is a slight "
            "under-count.</p>"
        )

    return section(
        "Cost",
        "cost",
        body,
        note=f"estimate only, not a billed figure; pricing as of {cost.get('pricingAsOf', 'unknown')} "
        "(references/pricing.json)",
    )


# How many clusters get the full paste-ready treatment (command + complete error text).
FAILURE_GROUP_DETAIL_LIMIT = 5


def render_failure_groups(groups: list, meta: dict) -> str:
    """Ranked failure clusters — "this failed 6 times", not five arbitrary early examples.

    The top clusters also expand to the exemplar's whole command and COMPLETE error text, so
    the report itself is the paste-ready surface for a bug report (bh-cp-t46.1).
    """
    if not groups:
        return ""
    rows = [
        [
            g.get("count"),
            g.get("commandShape"),
            (g.get("signatures") or [{}])[0].get("signature", ""),
            g.get("signatureCount", len(g.get("signatures") or [])),
            len(g.get("sessions") or []),
        ]
        for g in groups
    ]
    body = "<h3>Ranked clusters</h3>"
    body += table(["Failures", "Command shape", "Top error signature", "Distinct errors", "Sessions"], rows)
    for group in groups[:FAILURE_GROUP_DETAIL_LIMIT]:
        for sig in (group.get("signatures") or [])[:1]:
            exemplar = sig.get("exemplar", {})
            command = exemplar.get("command") or exemplar.get("detail") or ""
            body += (
                f"<details><summary>{esc(group.get('count'))}× {esc(group.get('commandShape'))} "
                f"— session {esc(str(exemplar.get('sessionId') or 'unknown')[:8])} at "
                f"{esc(_humanize_ts(exemplar.get('ts')))}</summary>"
                f"<pre>$ {esc(command)}\n\n{esc(exemplar.get('errorText') or '')}</pre></details>"
            )
    grouped = meta.get("failuresGrouped")
    shapes = meta.get("shapes")
    if grouped is not None:
        shown = meta.get("shapesShown", len(groups))
        body += (
            f"<p class='note'>{fmt_int(grouped)} bd/bh failure(s) clustered into "
            f"{fmt_int(shapes)} command shape(s), {fmt_int(shown)} shown, ranked by count; "
            "a failing bh:/beads: skill invocation has no command to shape and is counted "
            "above but not clustered</p>"
        )
    return body


def render_failures(failures: dict) -> str:
    # Only the two count buckets are tables — `examples`/`groups`/`groupsMeta` live alongside
    # them under the same key and are NOT tool->count maps (iterating every key here used to
    # crash the whole render on any real analysis.json).
    rows = []
    for bucket_name in ("beadsBh", "other"):
        for tool, count in (failures.get(bucket_name) or {}).items():
            rows.append([bucket_name, tool, count])
    body = table(["Bucket", "Tool", "Failure count"], sorted(rows, key=lambda r: (-r[2], r[0], r[1])))
    body += render_failure_groups(failures.get("groups") or [], failures.get("groupsMeta") or {})
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
# L4: raised from 2 -- a bare couple of re-reads isn't yet a signal worth flagging.
SKILL_MD_REREAD_THRESHOLD = 3


def _flatten_dashes(text) -> str:
    """recCard() splits a recommendation on its single ' — ' (what/why), so quoted run data —
    an error signature, a command shape — must never carry one of its own."""
    return str(text or "").replace(" — ", " - ")


def generate_recommendations(analysis: dict) -> dict:
    usage = []
    product = []

    cache = analysis.get("cache", {})
    significant = [e for e in cache.get("expiryEvents", []) if e.get("significant")]
    for e in significant[:CACHE_CALLOUT_LIMIT]:
        session_id = str(e.get("sessionId") or "")[:8]
        usage.append(
            f"Handoff opportunity in session {session_id} at {_humanize_ts(e.get('ts'))} — "
            f"cache expired after a {_humanize_duration(e.get('idleGapSeconds', 0))} idle gap, "
            f"wasting {fmt_int(e.get('wastedTokens', 0))} tokens."
        )

    cost = analysis.get("cost", {})
    unpriced = cost.get("unpriced", {})
    # H1: gate on actual unpriced TOKEN VOLUME, not model-list length -- the '<synthetic>'
    # sentinel is always present in unpriced.models with 0 tokens in every bucket in the
    # normal case, so a models-list-length gate always fired. Strip it before it's ever
    # joined into copy.
    unpriced_models = [m for m in unpriced.get("models", []) if not is_synthetic_model(m)]
    unpriced_tokens = sum(unpriced.get(k, 0) for k in ("input", "output", "cache_read", "eph5m", "eph1h"))
    if unpriced_tokens > 0:
        usage.append(
            f"{fmt_int(unpriced_tokens)} tokens were spent on unpriced model family/families "
            f"({', '.join(unpriced_models)}) — cost estimates above exclude them."
        )

    failures = analysis.get("failures", {})
    beads_bh_failures = sum(failures.get("beadsBh", {}).values())
    failure_groups = failures.get("groups") or []
    if beads_bh_failures:
        breakdown = ", ".join(f"{tool}: {n}" for tool, n in failures.get("beadsBh", {}).items())
        usage.append(
            f"{beads_bh_failures} failed bd/bh tool call(s) ({breakdown}) — worth a look in "
            "the raw session log."
        )
    # The largest cluster, not the earliest failure: a repeated failure is a fixable pattern,
    # while the first five chronologically are usually unrelated one-offs.
    top_group = failure_groups[0] if failure_groups else None
    if top_group and top_group.get("count", 0) > 1:
        usage.append(
            f"`{top_group.get('commandShape')}` failed {top_group.get('count')} times — the "
            "largest repeated failure in this run; see the Failures section for the full text."
        )

    skill_md_reads = analysis.get("skillReads", {}).get("skillMdReads", 0)
    if skill_md_reads > SKILL_MD_REREAD_THRESHOLD:
        usage.append(
            f"The retro guide was re-read {skill_md_reads} times — a shorter quick-reference "
            "might reduce that."
        )

    meta = analysis.get("meta", {})
    version_stamp = (
        f"observed on bh {meta.get('bhVersion', 'unknown')} / "
        f"plugin {meta.get('pluginVersion', 'unknown')} / "
        f"bd {meta.get('bdVersion', 'unknown')} "
        f"(CC {', '.join(meta.get('ccVersions', []) or ['unknown'])})"
    )
    if unpriced_tokens > 0:
        product.append(
            f"pricing.json has no rate for model family/families {', '.join(unpriced_models)} "
            f"({fmt_int(unpriced_tokens)} raw tokens went unpriced) — {version_stamp}."
        )
    if beads_bh_failures:
        breakdown = ", ".join(f"{tool}: {n}" for tool, n in failures.get("beadsBh", {}).items())
        product.append(f"{beads_bh_failures} bd/bh tool call(s) failed ({breakdown}) — {version_stamp}.")
    if top_group and top_group.get("count", 0) > 1:
        top_signature = (top_group.get("signatures") or [{}])[0].get("signature", "")
        product.append(
            f"`{_flatten_dashes(top_group.get('commandShape'))}` failed "
            f"{top_group.get('count')}× ({_flatten_dashes(top_signature)[:120]}) — {version_stamp}."
        )

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
details { margin: 0.5rem 0; }
summary { cursor: pointer; font-size: 0.9rem; }
pre { background: #f4f4f4; padding: 0.75rem; overflow-x: auto; white-space: pre-wrap;
      word-break: break-word; font-size: 0.8rem; }
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
details {{ margin: 0.5rem 0; }}
summary {{ cursor: pointer; font-size: 0.9rem; color: {BRAND['ink_secondary']}; }}
pre {{ background: {BRAND['surface_page']}; border: 1px solid {BRAND['border']};
      padding: 0.75rem; overflow-x: auto; white-space: pre-wrap; word-break: break-word;
      font-size: 0.8rem; color: {BRAND['ink_primary']}; }}
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
· plugin {esc(meta.get('pluginVersion', 'unknown'))} · bd {esc(meta.get('bdVersion', 'unknown'))}
· CC {esc(', '.join(meta.get('ccVersions', []) or ['unknown']))} · pricing as of {esc(cost.get('pricingAsOf', 'unknown'))}</p>
<nav>{nav}</nav>
{body_sections}
<footer>Rendered by retro's render.py from analysis.json. All figures are estimates
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
        "failures": {
            "beadsBh": {"Bash": 3},
            "other": {},
            # not a tool->count map: render_failures must not treat these as buckets
            "examples": [
                {"sessionId": "sess-1", "ts": "2026-07-20T10:25:00Z", "tool": "Bash",
                 "class": "beadhive", "detail": "bh work issue bh-cp-1 --json", "errorText": "jq: error"},
            ],
            "groups": [
                {
                    "commandShape": "bh work issue <id> --json",
                    "count": 2,
                    "classes": ["beadhive"],
                    "sessions": ["sess-1"],
                    "signatureCount": 1,
                    "signatures": [
                        {
                            "signature": "Exit code <n> jq: error (at <stdin>:<n>) — cannot index array",
                            "count": 2,
                            "exemplar": {
                                "sessionId": "sess-1", "ts": "2026-07-20T10:25:00Z", "tool": "Bash",
                                "class": "beadhive", "detail": "bh work issue $b --json",
                                "command": 'for b in bh-cp-1 bh-cp-2; do bh work issue $b --json; done',
                                "errorText": "Exit code 5\njq: error (at <stdin>:71) — cannot index array",
                                "errorChars": 52,
                            },
                        }
                    ],
                },
                {
                    "commandShape": "bh work show <id>",
                    "count": 1,
                    "classes": ["beadhive"],
                    "sessions": ["sess-1"],
                    "signatureCount": 1,
                    "signatures": [
                        {"signature": "Exit code <n>", "count": 1,
                         "exemplar": {"sessionId": "sess-1", "ts": "2026-07-20T10:26:00Z", "tool": "Bash",
                                      "class": "beadhive", "detail": "bh work show bh-cp-1",
                                      "command": "bh work show bh-cp-1 2>&1", "errorText": "Exit code 144",
                                      "errorChars": 13}},
                    ],
                },
            ],
            "groupsMeta": {"scope": "bd/bh invocation anywhere in the command",
                           "failuresGrouped": 3, "shapes": 2, "shapesShown": 2},
        },
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
        "meta": {
            "bhVersion": "0.5.1",
            "pluginVersion": "0.3.0",
            "bdVersion": "bd version 1.1.0",
            "ccVersions": ["2.1.207"],
            "pricingAsOf": "2026-07",
            "generatedAt": "2026-07-23T19:46:26Z",
        },
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
    assert "observed on bh 0.5.1" in out_html  # distinct bhVersion, not bd's
    assert "plugin 0.3.0" in out_html
    assert "bd bd version 1.1.0" in out_html

    # H2: cacheRatio is a ratio ('0.4×'), never a percentage (fmt_pct is no longer used for
    # this value in either renderer).
    assert "0.4×" in out_html

    # bh-cp-t46.2: ranked failure clusters, and the whole error text inline so the report
    # itself is paste-ready. Regression: failures now carries non-bucket keys
    # (examples/groups/groupsMeta) — render_failures used to iterate every key and crash.
    assert "Ranked clusters" in out_html
    assert "bh work issue &lt;id&gt; --json" in out_html  # escaped placeholder, ranked first
    assert out_html.index("bh work issue &lt;id&gt; --json") < out_html.index("bh work show &lt;id&gt;")
    assert "jq: error (at &lt;stdin&gt;:71)" in out_html  # exemplar's COMPLETE text, not the signature
    assert "for b in bh-cp-1 bh-cp-2" in out_html  # the command exactly as it ran
    assert "3 bd/bh failure(s) clustered into 2 command shape(s)" in out_html
    assert "failed 2 times" in out_html  # ranked-cluster recommendation

    recs = generate_recommendations(analysis)
    assert len(recs["usagePattern"]) >= 1
    assert len(recs["productImprovements"]) <= 3

    # M8: recommendation-card text is humanized (session id truncated, idle gaps/timestamps
    # readable, no internal filenames), and each item splits cleanly on exactly one ' — '
    # (what/why) -- the delimiter recCard()/recCards() split on in render_artifact.py.
    all_recs = recs["usagePattern"] + recs["productImprovements"]
    handoff_item = next(i for i in recs["usagePattern"] if i.startswith("Handoff opportunity"))
    assert "1200s" not in handoff_item  # raw seconds, e.g. the old f"{secs:.0f}s" format
    assert "~20m" in handoff_item  # humanized idle gap (1200s), not "1200s"
    assert "2026-07-20 10:20 UTC" in handoff_item  # humanized timestamp, not raw ISO-8601
    assert not any("events.jsonl" in i for i in all_recs)
    assert any("the raw session log" in i for i in all_recs)
    for item in all_recs:
        assert item.count(" — ") == 1, f"expected exactly one ' — ' delimiter: {item!r}"

    # H1 (anchor): with real unpriced token volume, exactly one '*' footnote in the exact
    # spec wording lands in the Cost section.
    assert "* Excludes 5 tokens from model(s) claude-mystery-1 with no configured rate — total is a slight under-count." in out_html

    # conditional unpriced caveat (bh-cp-og2.2 fix 7): the caveat text is NOT hardcoded --
    # it disappears once cost.unpriced.models is empty (e.g. once fable is priced, per
    # bh-cp-8xo). Re-render with an all-priced cost block and confirm the caveat is gone.
    priced_analysis = {**analysis, "cost": {**analysis["cost"], "unpriced": {
        "input": 0, "output": 0, "cache_read": 0, "eph5m": 0, "eph1h": 0, "models": [],
    }}}
    priced_html = render_html(priced_analysis)
    assert "unpriced model families" not in priced_html
    assert "pricing.json has no rate for model family/families" not in priced_html
    assert "claude-mystery-1" not in priced_html

    # H1 (anchor): zero unpriced tokens -> emit NOTHING unpriced-related at all -- no note,
    # no cost-table row, no usage/maintainer recommendation about it.
    assert "under-count" not in priced_html
    assert "Excludes" not in priced_html
    assert "unpriced" not in priced_html.lower()
    priced_recs = generate_recommendations(priced_analysis)
    assert not any("unpriced" in item.lower() for item in priced_recs["usagePattern"])
    assert not any("pricing.json has no rate" in item for item in priced_recs["productImprovements"])

    # H1 (anchor): the '<synthetic>' sentinel -- always present in cost.unpriced.models with 0
    # tokens in every bucket in the normal case -- must never leak into rendered copy, even
    # when explicitly present in the input analysis.json.
    synthetic_analysis = {**analysis, "cost": {**analysis["cost"], "unpriced": {
        "input": 0, "output": 0, "cache_read": 0, "eph5m": 0, "eph1h": 0, "models": ["<synthetic>"],
    }}}
    synthetic_html = render_html(synthetic_analysis)
    assert "<synthetic>" not in synthetic_html
    assert "under-count" not in synthetic_html
    assert "Excludes" not in synthetic_html

    mixed_analysis = {**analysis, "cost": {**analysis["cost"], "unpriced": {
        "input": 5, "output": 0, "cache_read": 0, "eph5m": 0, "eph1h": 0,
        "models": ["<synthetic>", "claude-mystery-1"],
    }}}
    mixed_html = render_html(mixed_analysis)
    assert "<synthetic>" not in mixed_html
    assert "claude-mystery-1" in mixed_html
    assert "under-count" in mixed_html

    # bh-cp-cmv: '<synthetic>' also shows up as a model_id in models.bySession's "models used"
    # list and as a models.beadsByModel key (both attributed straight off usageSeries/event
    # timestamps, independent of pricing) -- must be filtered from both display sites too,
    # while a real model alongside it still renders.
    synthetic_models_analysis = {
        **analysis,
        "models": {
            **analysis["models"],
            "bySession": {
                "sess-1": {"models": ["<synthetic>", "claude-sonnet-5"], "dominant": "claude-sonnet-5"},
            },
            "beadsByModel": {
                "<synthetic>": {"planned": 1, "implemented": 0, "merged": 0},
                "claude-sonnet-5": {"planned": 1, "implemented": 1, "merged": 0},
            },
        },
    }
    synthetic_models_html = render_html(synthetic_models_analysis)
    assert "<synthetic>" not in synthetic_models_html
    assert "claude-sonnet-5" in synthetic_models_html

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
