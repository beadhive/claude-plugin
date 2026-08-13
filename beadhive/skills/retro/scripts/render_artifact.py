#!/usr/bin/env python3
"""Charted artifact: render analysis.json (+ optional wallclock.json) into report-artifact.html.

Stdlib only. This is the CHARTED sibling of render.py: inline CSS + inline JS builds
interactive SVG charts (bars, stacked bars, a scatter, small multiples) for every
analysis.json metric family, still with zero external refs (no CDN, no external fonts/
scripts/stylesheets) — everything ships inline in the one output file.

wallclock.json (wallclock.py's output — session-timeline waste families: totals, humanIdle,
inferenceRate, toolTime, testChurn, humanGate, plausiblyAutomatable, suspectedApprovalGate) is
charted too, opt-in the same way `--wallclock-in`/the run-dir resolves it: if it's missing (an
older run-dir predating wallclock.py), the wall-clock section says so plainly in the artifact
instead of silently omitting it or failing the whole render.

CRITICAL: every SVG mark is created via `document.createElementNS` (the SVG namespace),
never by assigning `element.innerHTML` to a string containing bare `<rect>`/`<circle>` tags
outside an `<svg>` context — those land in the HTML namespace and silently fail to render in
Brave/Chromium. `--selftest` asserts this directly (see selftest()).

Resolves analysis.json/wallclock.json/writes report-artifact.html the same way render.py does:
explicit `--run-dir` wins, else the `latest` pointer, else legacy cwd-relative defaults.
`--in`/`--wallclock-in`/`--out` always override individually.

Usage:
    render_artifact.py [--in analysis.json] [--wallclock-in wallclock.json] [--out report-artifact.html] [--run-dir DIR]
    render_artifact.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os

import _rundir
# render.py is this script's non-charted sibling; its generate_recommendations() already
# implements the two-tier grounded roll-up (metrics.md (i)) — reuse it rather than forking
# a second copy of the same logic (recommendations were the biggest gap in this artifact).
# SYNTHETIC_MODEL/is_synthetic_model are render.py's single source of truth for the
# '<synthetic>' skip rule (Claude Code's non-billed-message marker, not a real model) — reuse
# them here too rather than duplicating the literal string in a second file.
from render import SYNTHETIC_MODEL, generate_recommendations, is_synthetic_model

# ---------------------------------------------------------------------------
# Beadhive honeycomb brand palette — mirrors ../references/palette.md's "Chart chrome &
# ink" + categorical/status tables verbatim (dark is the primary/default surface, light is
# the `prefers-color-scheme: light` override). Keep in sync by hand, same convention as
# render.py's BRAND dict.
# ---------------------------------------------------------------------------
BRAND_DARK = {
    "surface": "#17140c",
    "panel": "#2a2413",
    "plane": "#0a0702",
    "ink": "#f3e9d5",
    "ink2": "#c8972e",
    "muted": "#a99a79",
    "grid": "#2a2413",
    "baseline": "#433c2e",
    "accent": "#f2b617",
    "ring": "rgba(243,233,213,0.12)",
    "cat": ["#c08700", "#00a67f", "#8680e6", "#4a9c36", "#d36394", "#de602f", "#408ae4", "#dd555d"],
    "good": "#409d48",
    "warning": "#e78c08",
    "serious": "#e06a2a",
    "critical": "#d74745",
}
BRAND_LIGHT = {
    "surface": "#fbf4e8",
    "panel": "#f7f0e2",
    "plane": "#faefda",
    "ink": "#1a150b",
    "ink2": "#564523",
    "muted": "#756a55",
    "grid": "#e4ddcf",
    "baseline": "#aca493",
    "accent": "#c8972e",
    "ring": "rgba(26,21,11,0.10)",
    "cat": ["#db9f00", "#00a37c", "#4f40ab", "#2d8810", "#e177a3", "#dd5a27", "#2274d1", "#d33949"],
}

# Cardinality thresholds — the "Scaling guidance" rule from SKILL.md: any high-cardinality
# bar family (lifecycle.byEpic, skillReads) or small-multiples family (activity) gets a
# top-N cap plus one aggregated "+N more" bucket, never an unbounded render.
EPIC_TOP_N = 12
SKILL_TOP_N = 12
SESSION_TOP_N = 24

SVG_NS_URL = "http://www.w3.org/2000/svg"


def _root_vars(b: dict) -> str:
    cats = " ".join(f"--c{i + 1}:{c};" for i, c in enumerate(b["cat"]))
    lines = [
        f"--surface:{b['surface']}; --panel:{b['panel']}; --plane:{b['plane']};",
        f"--ink:{b['ink']}; --ink2:{b['ink2']}; --muted:{b['muted']};",
        f"--grid:{b['grid']}; --baseline:{b['baseline']}; --accent:{b['accent']};",
        f"--ring:{b['ring']};",
        cats,
    ]
    if "good" in b:
        lines.append(
            f"--good:{b['good']}; --warning:{b['warning']}; --serious:{b['serious']}; "
            f"--critical:{b['critical']};"
        )
    return "\n    ".join(lines)


def build_css() -> str:
    return f"""
  :root{{
    {_root_vars(BRAND_DARK)}
  }}
  @media (prefers-color-scheme: light){{
    :root{{
      {_root_vars(BRAND_LIGHT)}
    }}
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--plane);color:var(--ink);
    font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}}
  .wrap{{max-width:1080px;margin:0 auto;padding:2rem 1.25rem 4rem;}}
  header h1{{margin:0 0 .15rem;font-size:1.7rem;letter-spacing:.2px}}
  header h1 b{{color:var(--accent)}}
  header .sub{{color:var(--muted);font-size:.9rem}}
  header .sub code{{color:var(--ink2)}}
  .est{{color:var(--warning);font-weight:600}}
  section{{background:var(--surface);border:1px solid var(--ring);border-radius:12px;
    padding:1.1rem 1.25rem;margin:1.1rem 0;}}
  h2{{font-size:1.05rem;margin:.1rem 0 .2rem;color:var(--ink)}}
  h2 .accent{{color:var(--accent)}}
  .note{{color:var(--muted);font-size:.82rem;margin:.1rem 0 .8rem}}
  .note code{{color:var(--ink2)}}
  .tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.7rem}}
  .tile{{background:var(--panel);border-radius:10px;padding:.8rem .9rem}}
  .tile .n{{font-size:1.7rem;font-weight:700;color:var(--accent);font-variant-numeric:tabular-nums}}
  .tile .l{{color:var(--muted);font-size:.78rem;margin-top:.15rem}}
  .legend{{display:flex;flex-wrap:wrap;gap:.6rem 1rem;margin:.5rem 0 .2rem;font-size:.8rem;color:var(--muted)}}
  .legend span{{display:inline-flex;align-items:center;gap:.35rem}}
  .sw{{width:11px;height:11px;border-radius:3px;display:inline-block}}
  table{{border-collapse:collapse;width:100%;font-size:.82rem;margin-top:.6rem;
    font-variant-numeric:tabular-nums}}
  th,td{{text-align:right;padding:.28rem .5rem;border-bottom:1px solid var(--ring)}}
  th:first-child,td:first-child{{text-align:left}}
  thead th{{color:var(--muted);font-weight:600}}
  .sm-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:.5rem}}
  .sm{{background:var(--panel);border-radius:8px;padding:.4rem .5rem}}
  .sm .t{{font-size:.68rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  svg{{display:block;max-width:100%;height:auto}}
  rect.bar:hover,circle.dot:hover,rect.seg:hover{{opacity:.82;cursor:default}}
  .pctbar{{display:flex;width:100%;height:26px;border-radius:5px;overflow:hidden}}
  .pctseg:hover{{opacity:.82;cursor:default}}
  #tip{{position:fixed;pointer-events:none;background:var(--plane);color:var(--ink);
    border:1px solid var(--ring);border-radius:7px;padding:.4rem .55rem;font-size:.78rem;
    opacity:0;transition:opacity .08s;z-index:9;box-shadow:0 4px 16px rgba(0,0,0,.35);max-width:260px}}
  .rec-card{{background:var(--panel);border-radius:9px;padding:.6rem .85rem;margin:.5rem 0}}
  .rec-what{{font-weight:600;color:var(--ink)}}
  .rec-why{{color:var(--muted);font-size:.85rem;margin-top:.2rem}}
  .copy-fb-btn{{background:var(--accent);color:var(--plane);border:none;border-radius:6px;
    padding:.45rem .9rem;font-size:.82rem;font-weight:600;cursor:pointer}}
  .copy-fb-btn:hover{{opacity:.85}}
  .fb-fallback{{display:none;width:100%;margin-top:.5rem;font:12px/1.4 monospace;
    background:var(--panel);color:var(--ink);border:1px solid var(--ring);border-radius:7px;
    padding:.5rem}}
  footer{{color:var(--muted);font-size:.78rem;margin-top:1.5rem;text-align:center}}
"""


# ---------------------------------------------------------------------------
# The chart-building JS is static across runs — only the `A = {...}` data block and the
# top-N cap constants vary. Every mark is built via document.createElementNS (SVGNS) inside
# a real <svg> root created the same way, or via the `$()` template-parse helper for plain
# HTML elements (div/section/table/etc — never svg marks). This is the fix for the v1 bug:
# `$()`'s innerHTML path is only ever used for HTML-namespace elements, never for
# <rect>/<circle>/<path> marks, which always go through E()/createElementNS.
# ---------------------------------------------------------------------------
JS_TEMPLATE = r"""
const EPIC_TOP_N = __EPIC_TOP_N__, SKILL_TOP_N = __SKILL_TOP_N__, SESSION_TOP_N = __SESSION_TOP_N__;
const A = __ANALYSIS_JSON__;
// wallclock.py's output (session-timeline waste families) -- null on an older run-dir that
// predates wallclock.py, or an explicit --wallclock-in that doesn't resolve. Never a fatal
// condition: the wallclock section below renders one explanatory note instead in that case.
const W = __WALLCLOCK_JSON__;
const SVGNS = '__SVG_NS_URL__';
// SVG elements MUST be created in the SVG namespace via createElementNS — assigning
// innerHTML with bare <rect>/<circle> tags puts them in the HTML namespace and they
// silently fail to render in Brave/Chromium. Every mark below goes through E().
function E(tag,attrs){const e=document.createElementNS(SVGNS,tag);for(const k in attrs)e.setAttribute(k,attrs[k]);return e;}
function T(attrs,str){const t=E('text',attrs);t.textContent=str;return t;}
// Responsive SVG: a numeric width/height presentation attribute is an intrinsic size a
// wide card can never grow past (CSS max-width:100% only shrinks) -- that's what let v1's
// bar/scatter charts letterbox short of the card's right edge. width:'100%' + no height
// attribute makes the SVG a replaced element sized by its container, with height derived
// from the viewBox's intrinsic aspect ratio (same fix family as the %-width stackedBar()
// below, adapted to SVG via the standard viewBox+preserveAspectRatio technique).
function SVG(w,h){return E('svg',{viewBox:`0 0 ${w} ${h}`,width:'100%',preserveAspectRatio:'xMidYMid meet',role:'img'});}
const $=(h)=>{const t=document.createElement('template');t.innerHTML=h.trim();return t.content.firstChild;};
const fmt=(n)=>n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'k':(''+Math.round(n));
const usd=(n)=>'$'+n.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
// compact human duration, e.g. 9951 -> '2h46m' -- same rounding convention as render.py's
// Python-side _humanize_duration, kept independent (no cross-file import in a browser script).
const dur=(s)=>{s=Math.max(0,Math.round(s));if(s<60)return s+'s';const totalMin=Math.round(s/60);
 const h=Math.floor(totalMin/60),m=totalMin%60;return h?(m?`${h}h${m}m`:`${h}h`):`${m}m`;};
// escape untrusted text (raw Bash command strings, etc.) before it lands in a table cell or
// tooltip built via the $() innerHTML-parse helper below -- table()/hov() themselves don't
// escape (existing analysis.json call sites only ever pass known-safe enum-shaped strings), so
// callers embedding free-text (wallclock.json's tool cmd/normalized-command fields) must do it
// themselves. Same three-entity escape as Python's html.escape for this purpose.
const esc=(s)=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const CATS=['--c1','--c2','--c3','--c4','--c5','--c6','--c7','--c8'].map(v=>`var(${v})`);
const app=document.getElementById('app');
const tip=document.getElementById('tip');
function hov(el,html){el.addEventListener('mousemove',e=>{tip.innerHTML=html;tip.style.opacity=1;
  tip.style.left=Math.min(e.clientX+12,innerWidth-270)+'px';tip.style.top=(e.clientY+12)+'px';});
  el.addEventListener('mouseleave',()=>tip.style.opacity=0);}
function sec(title,noteHtml){const s=$(`<section><h2>${title}</h2>${noteHtml?`<div class="note">${noteHtml}</div>`:''}</section>`);app.appendChild(s);return s;}
function legend(s,items){const l=$('<div class="legend"></div>');items.forEach(([c,t])=>l.appendChild($(`<span><i class="sw" style="background:${c}"></i>${t}</span>`)));s.appendChild(l);}
function table(s,head,rows){const t=$('<table></table>');t.appendChild($(`<thead><tr>${head.map(h=>`<th>${h}</th>`).join('')}</tr></thead>`));const b=$('<tbody></tbody>');rows.forEach(r=>b.appendChild($(`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`)));t.appendChild(b);s.appendChild(t);}

// full-width percent-of-total bar (single group, e.g. token split). CSS flex/%-width
// segments, not a fixed-viewBox SVG — a 760px SVG width attribute never grows past
// 760px even in a wider card (max-width:100% only shrinks), which is what let the v1
// bar letterbox off-center. A %-width div always fills the card.
function stackedBar(s,segments){
 const total=segments.reduce((a,b)=>a+b.value,0)||1;
 const bar=$('<div class="pctbar"></div>');
 segments.forEach(sg=>{const pct=sg.value/total*100;
   const seg=$(`<div class="pctseg" style="width:${pct}%;background:${sg.color}"></div>`);
   hov(seg,`<b>${sg.label}</b><br>${fmt(sg.value)} tok · ${pct.toFixed(1)}%`);
   bar.appendChild(seg);});
 s.appendChild(bar);}

// vertical bars (grouped or stacked). groups with `.aggregate` (the "+N more" top-N-cap
// bucket) render lower-opacity + dashed to signal "rolled up, not a single real entity".
function vbars(s,groups,series,opts={}){
 const W=760,H=260,mL=52,mB=64,mT=12,plotW=W-mL-8,plotH=H-mT-mB,stacked=opts.stacked;
 const max=Math.max(...groups.map(g=>stacked?g.vals.reduce((a,b)=>a+b,0):Math.max(...g.vals)))||1;
 const svg=SVG(W,H);const fY=opts.fmtY||fmt;
 for(let i=0;i<=4;i++){const y=mT+plotH-plotH*i/4;
   svg.appendChild(E('line',{x1:mL,y1:y,x2:W-8,y2:y,stroke:'var(--grid)','stroke-width':1}));
   svg.appendChild(T({x:mL-6,y:y+3,'text-anchor':'end','font-size':10,fill:'var(--muted)'},fY(max*i/4)));}
 const gw=plotW/groups.length,bw=stacked?gw*0.5:gw*0.7/Math.max(1,series.length);
 groups.forEach((g,gi)=>{const gx=mL+gi*gw+gw*0.5;const op=g.aggregate?0.55:1;
   const border=g.aggregate?{stroke:'var(--muted)','stroke-width':1,'stroke-dasharray':'2 2'}:{};
   if(stacked){let acc=0;g.vals.forEach((v,si)=>{const h=v/max*plotH,y=mT+plotH-acc-h;
     const r=E('rect',Object.assign({class:'bar',x:gx-bw/2,y:y,width:bw,height:Math.max(0,h-1.5),rx:3,fill:series[si].color,'fill-opacity':op},border));
     hov(r,`<b>${g.name}</b><br>${series[si].name}: ${fY(v)}`);svg.appendChild(r);acc+=h;});}
   else{g.vals.forEach((v,si)=>{const h=v/max*plotH,x=gx-(series.length*bw)/2+si*bw;
     const r=E('rect',Object.assign({class:'bar',x:x,y:mT+plotH-h,width:Math.max(0,bw-2),height:Math.max(0,h),rx:3,fill:series[si].color,'fill-opacity':op},border));
     hov(r,`<b>${g.name}</b><br>${series[si].name}: ${fY(v)}`);svg.appendChild(r);});}
   svg.appendChild(T({x:gx,y:H-mB+16,'text-anchor':'middle','font-size':10,fill:'var(--muted)',transform:`rotate(18 ${gx} ${H-mB+16})`},g.name));});
 if(opts.footnote){svg.appendChild(T({x:mL,y:H-2,'font-size':9,fill:'var(--warning)'},opts.footnote));}
 s.appendChild(svg);}

// horizontal bars: one row per named value, bar width proportional to the row max. Used for
// short (<10 row) categorical/status splits (wallclock humanIdle-by-class, toolTime-by-class)
// where a row-per-label reads clearer than rotated x-axis labels on a vertical bar chart.
function hbars(s,rows,opts={}){
 const W=760,rowH=26,gap=6,mL=150,mR=64,plotW=W-mL-mR,H=rows.length*(rowH+gap)+8;
 const max=Math.max(...rows.map(r=>r.value),0)||1;
 const svg=SVG(W,H);const fY=opts.fmtY||fmt;
 rows.forEach((r,i)=>{const y=8+i*(rowH+gap),w=Math.max(0,r.value/max*plotW);
   svg.appendChild(T({x:mL-8,y:y+rowH*0.65,'text-anchor':'end','font-size':11,fill:'var(--ink)'},r.name));
   const bar=E('rect',{class:'bar',x:mL,y:y,width:w,height:rowH,rx:4,fill:r.color||'var(--accent)'});
   hov(bar,r.tip||`<b>${r.name}</b><br>${fY(r.value)}`);svg.appendChild(bar);
   svg.appendChild(T({x:mL+w+6,y:y+rowH*0.65,'font-size':11,fill:'var(--muted)'},fY(r.value)));});
 s.appendChild(svg);}

// one small-multiple tile: a 110x12 mini stacked bar for one session's signal split.
function smallMultiple(grid,keys,cols,label,counts){
 const tot=keys.reduce((x,k)=>x+counts[k],0)||1;
 const cell=$(`<div class="sm"><div class="t">${label}</div></div>`);
 const svg=SVG(110,12);let x=0;
 keys.forEach((k,i)=>{const w=counts[k]/tot*110;if(w>0){
   const r=E('rect',{class:'seg',x:x,y:0,width:Math.max(0,w-0.5),height:12,fill:cols[i]});
   hov(r,`<b>${label}</b><br>${k}: ${counts[k]}`);svg.appendChild(r);}x+=w;});
 cell.appendChild(svg);grid.appendChild(cell);}

// recommendation card: splits a grounded recommendation sentence on its first ' — ' (every
// generate_recommendations() item is written observation-first, rationale-after, delimited by
// an em dash) into a bold "what" line + a muted "why" line, so it reads as an explained action
// instead of a bare fact. No delimiter found -> the whole sentence is the "what", no "why".
function recCard(container,item){
 const idx=item.indexOf(' — ');
 const what=idx>=0?item.slice(0,idx):item, why=idx>=0?item.slice(idx+3):'';
 container.appendChild($(`<div class="rec-card"><div class="rec-what">${what}</div>${why?`<div class="rec-why">${why}</div>`:''}</div>`));}
function recCards(container,items){
 if(!items.length){container.appendChild($('<p class="note">None grounded in this run\'s data.</p>'));return;}
 items.forEach(i=>recCard(container,i));}

// Maintainer copy-feedback message: paste-ready, grounded in THIS run's concrete data —
// the productImprovements bullets (already version-stamped by generate_recommendations()) plus
// real failing calls so a maintainer has an instance to act on, not just an aggregate count.
//
// Failing calls come from failures.groups (ranked by count) when present: "this failed 6
// times" with the COMPLETE error text beats five arbitrary chronological examples, which in
// the window that motivated this were four unrelated classifier denials. failures.examples is
// the fallback for an analysis.json written before grouping existed.
const FEEDBACK_GROUP_TOP_N=3, FEEDBACK_ERROR_MAXLEN=1200;
function feedbackFailureLines(){
 const groups=(A.failures&&A.failures.groups)||[];
 if(groups.length){
   return groups.slice(0,FEEDBACK_GROUP_TOP_N).map(g=>{
     const sig=(g.signatures&&g.signatures[0])||{}, ex=sig.exemplar||{};
     const text=(ex.errorText||'').slice(0,FEEDBACK_ERROR_MAXLEN);
     const clipped=(ex.errorChars||0)>text.length?` …[${ex.errorChars} chars total]`:'';
     return `- ${g.count}× \`${g.commandShape}\` (${(g.classes||[]).join('/')}), e.g. session ${ex.sessionId} at ${ex.ts}:\n    $ ${ex.command||ex.detail||''}\n    ${text}${clipped}`;});}
 const examples=(A.failures&&A.failures.examples)||[];
 return examples.map(e=>`- session ${e.sessionId} · ${e.tool} (${e.class}): \`${e.detail}\`${e.errorText?` — error: ${e.errorText}`:''}`);}
function buildFeedbackMessage(){
 const meta=A.meta||{};
 const stamp=`bh ${meta.bhVersion} / plugin ${meta.pluginVersion} / bd ${meta.bdVersion} (CC ${(meta.ccVersions||['unknown']).join(',')})`;
 const lines=[`Beadhive retro feedback — ${stamp}`,''];
 const prod=(A.recommendations&&A.recommendations.productImprovements)||[];
 lines.push('Observations:');
 lines.push(prod.length?prod.map((p,i)=>`${i+1}. ${p}`).join('\n'):'(none grounded in this run\'s data)');
 const failures=feedbackFailureLines();
 if(failures.length){
   lines.push('','Failing calls from this run (most frequent first):');
   failures.forEach(l=>lines.push(l));}
 return lines.join('\n');}

// Primary path: the async Clipboard API. Fallback (Clipboard API absent/denied -- common under
// a file:// origin, which is how this artifact is usually opened): reveal a pre-filled,
// pre-selected textarea so the user can Cmd/Ctrl+C manually -- a "select-text" fallback, not a
// silent failure.
async function copyFeedback(btn,fallbackTa){
 const msg=buildFeedbackMessage();
 const reset=()=>setTimeout(()=>{btn.textContent='Copy feedback';},2200);
 if(navigator.clipboard&&navigator.clipboard.writeText){
   try{await navigator.clipboard.writeText(msg);btn.textContent='Copied!';reset();return;}catch(err){/* fall through */}}
 fallbackTa.value=msg;fallbackTa.style.display='block';fallbackTa.focus();fallbackTa.select();
 btn.textContent='Select & copy below';reset();}

document.getElementById('sub').innerHTML =
  `${Object.keys(A.activity).length} sessions · bh <code>${A.meta.bhVersion}</code> · plugin <code>${A.meta.pluginVersion}</code> · bd <code>${A.meta.bdVersion}</code> · CC ${(A.meta.ccVersions||['unknown']).join(',')} · cost <span class="est">estimated</span> · pricing as of ${A.cost.pricingAsOf}`;
document.getElementById('foot').textContent =
  `Generated ${A.meta.generatedAt} · all figures read directly from the analysis data; cost is an estimate, not a billed figure`;

// headline tiles
{const s=sec('Headline');const g=$('<div class="tiles"></div>');
 [[A.cache.cacheRatio.toFixed(1)+'×','cache reuse: cache-read tokens per fresh token (cold input + cache writes); higher is better.'],
  [A.cache.significantExpiryEventCount,'cache-expiry events ≥10k wasted tokens'],
  [usd(A.cost.total),'estimated total cost'],
  [usd(A.cost.cacheWasteUSD),'est. avoidable cache-waste (already in the total above)'],
  [Object.keys(A.activity).length,'Beadhive sessions']
 ].forEach(([n,l])=>g.appendChild($(`<div class="tile"><div class="n">${n}</div><div class="l">${l}</div></div>`)));
 s.appendChild(g);}

// tokens — stacked bar (categorical color job: token category is unordered, one hue each)
{const t=A.tokens.exact.totals;
 const s=sec('Token split <span class="accent">·</span> where the tokens went',
   'cache_read dominates when the pipeline is cache-heavy. Estimated file read/write tokens omitted (rough chars÷4 estimate).');
 const order=[['input',t.input,CATS[0]],['output',t.output,CATS[1]],['cache_read',t.cache_read,CATS[2]],['cache_creation',t.cache_creation,CATS[3]]];
 legend(s,order.map(o=>[o[2],o[0]]));
 stackedBar(s,order.map(o=>({label:o[0],value:o[1],color:o[2]})));
 const tot=order.reduce((a,o)=>a+o[1],0)||1;
 table(s,['category','tokens','% of total'],order.map(o=>[o[0],fmt(o[1]),(o[1]/tot*100).toFixed(1)+'%']));}

// cost by model — stacked bar (categorical: cost components). Unpriced text is gated on
// actual unpriced TOKEN VOLUME (not just A.cost.unpriced.models being non-empty — a synthetic
// sentinel model id is always present with 0 tokens in the normal case, so a models-length
// gate always fired). The sentinel is stripped server-side (render_html()) before A is ever
// embedded, so `up.models` here is already real model ids only.
{const bm=A.cost.byModel,fams=Object.keys(bm);
 const up=A.cost.unpriced||{models:[]},upModels=up.models||[];
 const upTokens=(up.input||0)+(up.output||0)+(up.cache_read||0)+(up.eph5m||0)+(up.eph1h||0);
 const hasUnpriced=upTokens>0;
 const unpricedFootnote=hasUnpriced?
   `* Excludes ${fmt(upTokens)} tokens from model(s) ${upModels.join(', ')} with no configured rate — total is a slight under-count.`:
   '* Estimate only — not a billed figure.';
 const comps=[['inputCost','input',CATS[0]],['outputCost','output',CATS[1]],['cacheReadCost','cache read',CATS[2]],['cacheWriteCost','cache write',CATS[3]]];
 const s=sec('Estimated cost by model',
   `estimate from references/pricing.json (asOf ${A.cost.pricingAsOf}), not billed.`);
 legend(s,comps.map(c=>[c[2],c[1]]));
 vbars(s,fams.map(f=>({name:f.replace('claude-',''),vals:comps.map(c=>bm[f][c[0]])})),
   comps.map(c=>({name:c[1],color:c[2]})),
   {stacked:true,fmtY:usd,footnote:unpricedFootnote});
 const rows=fams.map(f=>[f.replace('claude-',''),usd(bm[f].inputCost),usd(bm[f].outputCost),usd(bm[f].cacheReadCost),usd(bm[f].cacheWriteCost),usd(bm[f].totalCost)]);
 if(hasUnpriced)rows.push(['unpriced ('+upModels.join('+')+')','—','—',fmt(up.cache_read||0)+' tok','—','n/a']);
 table(s,['model','input','output','cache read','cache write','total'],rows);}

// bead lifecycle events by model — stacked bar (ordered/sequential color job: the stages
// planned -> implemented -> merged are a sequence, not an unordered category)
{const bbm=A.models.beadsByModel,fams=Object.keys(bbm);
 const stages=[['planned',CATS[0]],['implemented',CATS[1]],['merged',CATS[3]]];
 const s=sec('Bead lifecycle events by model',
   'Model attribution is approximate — each tool call is credited to whichever model\'s turn shares its timestamp.');
 legend(s,stages.map(x=>[x[1],x[0]]));
 vbars(s,fams.map(f=>({name:f.replace('claude-',''),vals:stages.map(st=>bbm[f][st[0]])})),
   stages.map(st=>({name:st[0],color:st[1]})),{});
 table(s,['model','planned','implemented','merged'],fams.map(f=>[f.replace('claude-',''),bbm[f].planned,bbm[f].implemented,bbm[f].merged]));}

// cache-expiry scatter — idle gap (x, log) x wasted tokens (y); status color (warning)
{const ev=A.cache.expiryEvents.slice();
 const s=sec('Cache-expiry events <span class="accent">·</span> idle gap × wasted tokens',
   'each point is a cache that expired during an idle gap, forcing context to be re-sent. Up-and-right = starting a fresh session instead of resuming would likely have cost less.');
 if(ev.length){
 const W=760,H=300,mL=60,mB=42,mT=20,plotW=W-mL-12,plotH=H-mT-mB;
 const xs=ev.map(e=>Math.log10(Math.max(1,e.idleGapSeconds))),xmin=Math.min(...xs),xmax=Math.max(...xs);
 const ymax=Math.max(...ev.map(e=>e.wastedTokens))||1;
 const svg=SVG(W,H);
 for(let i=0;i<=4;i++){const y=mT+plotH-plotH*i/4;
   svg.appendChild(E('line',{x1:mL,y1:y,x2:W-12,y2:y,stroke:'var(--grid)'}));
   svg.appendChild(T({x:mL-6,y:y+3,'text-anchor':'end','font-size':10,fill:'var(--muted)'},fmt(ymax*i/4)));}
 // Y-axis title (rotated) so the tick numbers above read as a token count, not a bare
 // scalar — the v1 axis had no unit label at all.
 svg.appendChild(T({x:14,y:mT+plotH/2,'text-anchor':'middle','font-size':10,fill:'var(--muted)',transform:`rotate(-90 14 ${mT+plotH/2})`},'wasted tokens'));
 // Dense human-scale candidate ticks spanning sec/min/hr; only the ones landing inside
 // [xmin,xmax] render, so the visible set adapts to the actual idle-gap range instead of
 // the old sparse fixed set. Ticks render bolder (ink2, not muted) so they're legible
 // against the dashed gridlines, not faint.
 [[15,'15s'],[30,'30s'],[60,'1m'],[120,'2m'],[300,'5m'],[600,'10m'],[900,'15m'],[1800,'30m'],
  [3600,'1h'],[7200,'2h'],[10800,'3h'],[21600,'6h'],[36000,'10h'],[86400,'24h']].forEach(([g,lab])=>{
   const lx=Math.log10(g);if(lx<xmin-0.15||lx>xmax+0.15)return;const x=mL+(lx-xmin)/((xmax-xmin)||1)*plotW;
   svg.appendChild(E('line',{x1:x,y1:mT,x2:x,y2:mT+plotH,stroke:'var(--grid)','stroke-dasharray':'2 3'}));
   svg.appendChild(T({x:x,y:H-mB+16,'text-anchor':'middle','font-size':10,'font-weight':600,fill:'var(--ink2)'},lab));});
 ev.forEach(e=>{const x=mL+(Math.log10(Math.max(1,e.idleGapSeconds))-xmin)/((xmax-xmin)||1)*plotW;
   const y=mT+plotH-e.wastedTokens/ymax*plotH,r=4+Math.sqrt(e.wastedTokens)/90;
   const dot=E('circle',{class:'dot',cx:x,cy:y,r:r,fill:'var(--warning)','fill-opacity':0.8,stroke:'var(--surface)','stroke-width':1});
   hov(dot,`<b>${e.sessionId.slice(0,8)}</b><br>idle ${(e.idleGapSeconds/60).toFixed(0)} min<br>wasted ${fmt(e.wastedTokens)} tok`);svg.appendChild(dot);});
 svg.appendChild(T({x:mL,y:H-4,'font-size':10,fill:'var(--muted)'},'idle gap (log scale) →'));
 s.appendChild(svg);
 const top=ev.slice().sort((a,b)=>b.wastedTokens-a.wastedTokens).slice(0,5);
 table(s,['session','idle gap','wasted tokens'],top.map(e=>[e.sessionId.slice(0,8),(e.idleGapSeconds/60).toFixed(0)+' min',fmt(e.wastedTokens)]));
 }else{s.appendChild($('<p class="note">No cache-expiry events this run.</p>'));}}

// activity distribution — aggregate stacked bar + capped/sorted small multiples (status
// color job: planning/implementing/diagnosing/fixing are discrete states, not a sequence)
{const acts=Object.entries(A.activity),keys=['planning','implementing','diagnosing','fixing'];
 const cols=[CATS[0],CATS[3],CATS[6],CATS[7]],agg={planning:0,implementing:0,diagnosing:0,fixing:0};
 acts.forEach(([,v])=>keys.forEach(k=>agg[k]+=v.counts[k]));
 const sorted=acts.slice().sort((a,b)=>keys.reduce((x,k)=>x+b[1].counts[k],0)-keys.reduce((x,k)=>x+a[1].counts[k],0));
 const shown=sorted.slice(0,SESSION_TOP_N),rest=sorted.slice(SESSION_TOP_N);
 const s=sec('Activity distribution',
   `Each session's turns are tagged planning/implementing/diagnosing/fixing (a turn can raise >1 tag); bars show how many turns raised each tag. Small multiples capped at top ${SESSION_TOP_N} by total tagged turns` +
   (rest.length?`, remaining ${rest.length} folded into one "+N more" tile to keep the chart readable.`:'.'));
 legend(s,keys.map((k,i)=>[cols[i],k]));
 stackedBar(s,keys.map((k,i)=>({label:k,value:agg[k],color:cols[i]})));
 table(s,['activity','turns tagged'],keys.map(k=>[k,agg[k]]));
 const grid=$('<div class="sm-grid" style="margin-top:.8rem"></div>');
 shown.forEach(([sid,v])=>smallMultiple(grid,keys,cols,`${sid.slice(0,8)} · ${v.suggested||'—'}`,v.counts));
 if(rest.length){const restAgg={planning:0,implementing:0,diagnosing:0,fixing:0};
   rest.forEach(([,v])=>keys.forEach(k=>restAgg[k]+=v.counts[k]));
   smallMultiple(grid,keys,cols,`+${rest.length} more · aggregate`,restAgg);}
 s.appendChild(grid);}

// lifecycle by epic — top-N + aggregate stacked bar (ordered/sequential color job: planned
// -> implemented -> merged is a sequence, same encoding as the by-model lifecycle chart)
{const rows=Object.entries(A.lifecycle.byEpic).map(([e,v])=>({name:e,vals:[v.planned,v.implemented,v.merged]}))
   .sort((a,b)=>(b.vals[0]+b.vals[1]+b.vals[2])-(a.vals[0]+a.vals[1]+a.vals[2]));
 const topN=rows.slice(0,EPIC_TOP_N),rest=rows.slice(EPIC_TOP_N);
 // The "+N more" bundle is intentionally OMITTED from the bar chart itself: a bundle of
 // 69 rolled-up epics dwarfs any single real epic's bar, flattening the top-N differences
 // this chart exists to show. It's kept as a text note + one table row instead — real
 // numbers, just not fighting the top-N bars for vertical scale.
 const groups=topN.map(r=>({name:r.name.replace('bh-',''),vals:r.vals}));
 let restSums=[0,0,0];
 if(rest.length)rest.forEach(r=>r.vals.forEach((v,i)=>restSums[i]+=v));
 const stages=[['planned',CATS[0]],['implemented',CATS[1]],['merged',CATS[3]]];
 const s=sec(`Bead group (by id prefix) <span class="accent">·</span> top ${EPIC_TOP_N} of ${rows.length}`,
   `Bead ids grouped by bead-id prefix, a heuristic — not verified epic/parent links; many groups are a single bead. source: <code>${A.lifecycle.source}</code>.` +
   (rest.length?` Top ${EPIC_TOP_N} groups by activity shown in the chart; remaining ${rest.length} groups' bundled totals (${fmt(restSums[0])} planned, ${fmt(restSums[1])} impl, ${fmt(restSums[2])} merged) are large enough to dwarf the real top-N bars, so they're omitted from the chart and folded into one "+N more" table row instead.`:''));
 legend(s,stages.map(x=>[x[1],x[0]]));
 vbars(s,groups,stages.map(st=>({name:st[0],color:st[1]})),{stacked:true});
 const tableRows=topN.map(r=>[r.name,r.vals[0],r.vals[1],r.vals[2]]);
 if(rest.length)tableRows.push([`+${rest.length} more`,restSums[0],restSums[1],restSums[2]]);
 table(s,['group','planned','impl','merged'],tableRows);}

// Tool-class coloring shared by the skill-invocations and failed-tool-calls charts below:
// four fixed classes, in fixed order, mapped to the categorical palette's slots 1-4
// (amber/teal/violet/moss — palette.md) so the same class always reads the same color
// across both charts. `raw-beads`/`raw-git` each fold in their `bh bd`/`bh git` passthrough
// sub-case (toolClasses.byTool already sums direct+passthrough into the class total).
const TOOL_CLASSES=['beadhive','raw-beads','raw-git','other'];
const TOOL_CLASS_COLORS=[CATS[0],CATS[1],CATS[2],CATS[3]];
const TOOL_CLASS_CAPTION='beadhive = native bh commands and bh: skills; raw-beads / raw-git = the agent used bd/git directly instead of a bh verb; other = everything else (Read/Write/Edit/…).';
const byTool=(c,name)=>((A.toolClasses||{})[c]||{}).byTool?.[name];

// skill reads — top-N + aggregate bar (categorical color job: skill names are unordered),
// now colored by tool class (beadhive/raw-beads/raw-git/other) instead of a flat bh:/beads:
// vs other binary, sourced from toolClasses (a Skill event's byTool key is its skill id —
// see analyze.py's _tool_class_key — distinguished from a bare tool-type key by the ':'
// every skill id carries, e.g. 'bh:planner').
{const skillNames=new Set();
 TOOL_CLASSES.forEach(c=>Object.keys(((A.toolClasses||{})[c]||{}).byTool||{}).forEach(n=>{if(n.includes(':'))skillNames.add(n);}));
 const rows=Array.from(skillNames)
   .map(name=>[name,TOOL_CLASSES.reduce((sum,c)=>sum+(byTool(c,name)?.total||0),0)])
   .sort((a,b)=>b[1]-a[1]);
 const shown=rows.slice(0,SKILL_TOP_N),rest=rows.slice(SKILL_TOP_N);
 const groups=shown.map(([name])=>({name,vals:TOOL_CLASSES.map(c=>byTool(c,name)?.total||0)}));
 let restSum=0;if(rest.length)restSum=rest.reduce((a,[,v])=>a+v,0);
 const s=sec('Skill invocations <span class="accent">·</span> beadhive / raw-beads / raw-git / other',
   `by invocation count, top ${SKILL_TOP_N} of ${rows.length} shown in the chart` +
   (rest.length?` (remaining ${rest.length} skills — ${fmt(restSum)} invocations — see the table below)`:'') +
   `. SKILL.md itself was read ${A.skillReads.skillMdReads} time(s) across sessions. ${TOOL_CLASS_CAPTION}`);
 legend(s,TOOL_CLASSES.map((c,i)=>[TOOL_CLASS_COLORS[i],c]));
 if(groups.length)vbars(s,groups,TOOL_CLASSES.map((c,i)=>({name:c,color:TOOL_CLASS_COLORS[i]})),{stacked:true});
 table(s,['skill','invocations'],rows);}

// failed tool calls — stacked bar, now colored by tool class instead of a flat beads/bh vs
// other binary. One bar per failing NAME (a Skill event's own skill id, else its tool type —
// same byTool keying toolClasses uses everywhere), stacked/colored by class.
{const names=new Set();
 TOOL_CLASSES.forEach(c=>Object.keys(((A.toolClasses||{})[c]||{}).byTool||{}).forEach(n=>{if((byTool(c,n)?.failed||0)>0)names.add(n);}));
 const toolNames=Array.from(names)
   .sort((a,b)=>TOOL_CLASSES.reduce((s,c)=>s+(byTool(c,b)?.failed||0),0)-TOOL_CLASSES.reduce((s,c)=>s+(byTool(c,a)?.failed||0),0));
 const s=sec('Failed tool calls <span class="accent">·</span> by tool, beadhive / raw-beads / raw-git / other',
   `one bar per failing tool/skill; stacked/colored by tool class. ${TOOL_CLASS_CAPTION}`);
 legend(s,TOOL_CLASSES.map((c,i)=>[TOOL_CLASS_COLORS[i],c]));
 if(toolNames.length){
   vbars(s,toolNames.map(name=>({name,vals:TOOL_CLASSES.map(c=>byTool(c,name)?.failed||0)})),
     TOOL_CLASSES.map((c,i)=>({name:c,color:TOOL_CLASS_COLORS[i]})),{stacked:true});
 }else{s.appendChild($('<p class="note">No failed tool calls this run.</p>'));}
 const rows=TOOL_CLASSES.flatMap(c=>Object.entries(((A.toolClasses||{})[c]||{}).byTool||{})
     .filter(([,v])=>v.failed>0).map(([k,v])=>[`${c} · ${k}`,v.failed]))
   .sort((a,b)=>b[1]-a[1]);
 table(s,['group / tool','count'],rows);}

// ---------------------------------------------------------------------------
// Wall-clock waste (wallclock.json, wallclock.py's output) — session-timeline families, per
// the bh-cp-t46.5 form mapping: session-span split -> stacked bar (categorical, buckets are
// unordered); humanIdle by class -> horizontal bars (status: discrete idle-reply states);
// humanGate -> stat tiles + an explicit "inside tool time" note (n/a color job, single figure);
// inferenceRate -> stat tiles + bars (sequential: p25 -> median -> p75 is ordered);
// toolTime by class -> horizontal bars (categorical); testChurn -> table + tiles (categorical).
// W is null on an older run-dir predating wallclock.py -- render one explanatory section
// instead of silently dropping the whole family group or throwing.
// ---------------------------------------------------------------------------
if(W){
 // session-span split -- stacked bar (categorical color job: the four buckets are unordered).
 // The record-gap caveat (W.totals.note) is the section note, legible on the render itself,
 // not only in metrics.md prose.
 {const t=W.totals;
  const s=sec('Wall-clock <span class="accent">·</span> session-span split',t.note);
  const g=$('<div class="tiles"></div>');
  [[t.sessions,'sessions'],[dur(t.sessionSpanSec),'summed session span'],
   [dur(t.inferenceSec),'inference'],[dur(t.toolSec),'tool (batch span)'],
   [dur(t.humanIdleSec),'human idle'],[dur(t.unattributedSec),'unattributed']
  ].forEach(([n,l])=>g.appendChild($(`<div class="tile"><div class="n">${n}</div><div class="l">${l}</div></div>`)));
  s.appendChild(g);
  const order=[['inference',t.inferenceSec,CATS[0]],['tool',t.toolSec,CATS[1]],['humanIdle',t.humanIdleSec,CATS[2]],['unattributed',t.unattributedSec,CATS[3]]];
  legend(s,order.map(o=>[o[2],o[0]]));
  stackedBar(s,order.map(o=>({label:o[0],value:o[1],color:o[2]})));
  table(s,['bucket','seconds','human'],order.map(o=>[o[0],fmt(o[1]),dur(o[1])]));}

 // human idle by class -- horizontal bars (status color job: approval-shaped / direction /
 // parked / answering-a-question are discrete reply-shape states, not a sequence).
 {const hi=W.humanIdle,classes=Object.keys(hi.byClass);
  const idleCols={'approval-shaped':CATS[4],'direction':CATS[5],'parked':CATS[6],'answering-a-question':CATS[7]};
  const s=sec('Human idle <span class="accent">·</span> by class',`${hi.note} ${hi.recoverableNote}`);
  if(classes.length)hbars(s,classes.map(c=>({name:c,value:hi.byClass[c].sec,color:idleCols[c]||'var(--accent)',
    tip:`<b>${esc(c)}</b><br>${hi.byClass[c].count} event(s) · ${dur(hi.byClass[c].sec)}`})),{fmtY:dur});
  const g=$('<div class="tiles" style="margin-top:.7rem"></div>');
  g.appendChild($(`<div class="tile"><div class="n">${dur(hi.recoverableSec)}</div><div class="l">recoverable (approval-shaped) — a supervisor loop could plausibly have answered</div></div>`));
  s.appendChild(g);
  table(s,['class','count','seconds','human'],classes.map(c=>[c,hi.byClass[c].count,fmt(hi.byClass[c].sec),dur(hi.byClass[c].sec)]));}

 // inference rate -- stat tiles + bar (sequential/ordinal color job: p25 -> median -> p75 is
 // an ordered rate sequence, not an unordered category).
 {const ir=W.inferenceRate;
  const s=sec('Inference rate <span class="accent">·</span> output tokens/sec',ir.note);
  const g=$('<div class="tiles"></div>');
  [[ir.turns,'turns'],[ir.ratedTurns,'rated turns (≥200 out tok)'],
   [ir.p25TokPerSec.toFixed(1),'p25 tok/s'],[ir.medianTokPerSec.toFixed(1),'median tok/s'],
   [ir.p75TokPerSec.toFixed(1),'p75 tok/s'],[dur(ir.excessSecondsVsP75),'excess vs p75'],
   [ir.slowTurnCount,'slow turns (≥180s)']
  ].forEach(([n,l])=>g.appendChild($(`<div class="tile"><div class="n">${n}</div><div class="l">${l}</div></div>`)));
  s.appendChild(g);
  hbars(s,[{name:'p25',value:ir.p25TokPerSec,color:CATS[0]},{name:'median',value:ir.medianTokPerSec,color:CATS[1]},
    {name:'p75',value:ir.p75TokPerSec,color:CATS[2]}],{fmtY:(v)=>v.toFixed(1)+' tok/s'});}

 // tool time by class -- horizontal bars (categorical: class is unordered). byClassNote's
 // inflated-vs-toolSec warning is surfaced directly on the section, not only in metrics.md.
 {const tt=W.toolTime,classes=Object.keys(tt.byClass);
  const s=sec('Tool time <span class="accent">·</span> by class',`${tt.note} ${tt.byClassNote}`);
  if(classes.length)hbars(s,classes.map((c,i)=>({name:c,value:tt.byClass[c].sec,color:CATS[i%8],
    tip:`<b>${esc(c)}</b><br>${tt.byClass[c].count} call(s) · ${tt.byClass[c].failed} failed · ${dur(tt.byClass[c].sec)}`})),{fmtY:dur});
  table(s,['class','count','failed','seconds','human'],classes.map(c=>[c,tt.byClass[c].count,tt.byClass[c].failed,fmt(tt.byClass[c].sec),dur(tt.byClass[c].sec)]));}

 // human-gate wait -- stat tiles (n/a color job, single figures), plus an explicit callout
 // that this is a SUBSET already inside the "Tool time" section above -- never summed with it
 // into a new total here (the double-counting warning bh-cp-t46.5's acceptance criteria calls
 // out by name: "gate-tool time is labelled as sitting inside tool time wherever both are
 // shown together").
 {const hg=W.humanGate;
  const s=sec('Human-gate wait <span class="accent">·</span> AskUserQuestion / ExitPlanMode / EnterPlanMode',hg.note);
  const g=$('<div class="tiles"></div>');
  [[hg.count,'gate calls'],[dur(hg.sec),'gate wait (already inside Tool time above)']]
   .forEach(([n,l])=>g.appendChild($(`<div class="tile"><div class="n">${n}</div><div class="l">${l}</div></div>`)));
  s.appendChild(g);
  s.appendChild($('<p class="note"><b>Subset, not additive:</b> already counted inside the Tool time section above (toolTime.byClass[\'other\']) — do not add this figure on top of it.</p>'));
  const gateRows=Object.entries(hg.byTool).map(([k,v])=>[k,v.count,fmt(v.sec),dur(v.sec)]);
  table(s,['tool','count','seconds','human'],gateRows);}

 // test churn -- table + tiles (categorical: command identity is unordered).
 {const tc=W.testChurn;
  const s=sec('Test churn <span class="accent">·</span> repeated commands',tc.note);
  const g=$('<div class="tiles"></div>');
  [[tc.repeatedCount,'repeated commands (3+ runs)'],[dur(tc.retestTaxSec),'re-test tax'],
   [tc.mergeAdjacentUniqueRuns,'merge-adjacent re-test runs (unique)'],[dur(tc.mergeAdjacentUniqueSec),'merge-adjacent seconds (unique)']
  ].forEach(([n,l])=>g.appendChild($(`<div class="tile"><div class="n">${n}</div><div class="l">${l}</div></div>`)));
  s.appendChild(g);
  s.appendChild($(`<p class="note">${esc(tc.retestTaxNote)} ${esc(tc.mergeAdjacentNote)}</p>`));
  table(s,['class','command','runs','sessions','seconds','avg sec'],
    tc.repeated.map(r=>[r.class,esc(r.command),r.runs,r.sessions,fmt(r.sec),r.avgSec.toFixed(1)]));}

 // suspected approval gate -- heuristic call-out, stat tiles + table.
 {const ag=W.suspectedApprovalGate;
  const s=sec('Suspected approval gate <span class="accent">·</span> normally-instant calls that stalled',ag.note);
  const g=$('<div class="tiles"></div>');
  [[ag.count,'suspected gate stalls'],[dur(ag.sec),'total stalled seconds']]
   .forEach(([n,l])=>g.appendChild($(`<div class="tile"><div class="n">${n}</div><div class="l">${l}</div></div>`)));
  s.appendChild(g);
  table(s,['session','tool','command','seconds'],
    ag.top.slice(0,10).map(c=>[esc((c.sessionId||'').slice(0,8)),esc(c.tool),esc(c.cmd),fmt(c.durationSec)]));}

 // plausibly automatable -- stat tiles. Its own deliberately-scoped sum (approval-shaped idle
 // + gate-tool wait); never conflated with the toolTime/humanGate subset relationship above.
 {const pa=W.plausiblyAutomatable;
  const s=sec('Plausibly automatable <span class="accent">·</span> approval idle + gate wait',pa.note);
  const g=$('<div class="tiles"></div>');
  [[dur(pa.sec),'total plausibly automatable'],[dur(pa.humanIdleRecoverableSec),'from approval-shaped idle'],
   [dur(pa.humanGateSec),'from gate-tool wait (also inside Tool time above)']]
   .forEach(([n,l])=>g.appendChild($(`<div class="tile"><div class="n">${n}</div><div class="l">${l}</div></div>`)));
  s.appendChild(g);}
}else{
 sec('Wall-clock waste','<code>wallclock.json</code> not found for this run — re-run <code>wallclock.py</code> to include wall-clock waste sections.');
}

// recommendations — grounded two-tier roll-up, ported from render.py's
// generate_recommendations() (the biggest gap in this artifact per SKILL.md): a short
// prose summary, then Usage-pattern (for the user) and Beadhive product-improvement
// (for maintainers, version-stamped) tiers. Every item cites a specific analysis.json
// number -- computed once in Python, this block only renders what A.recommendations
// already carries.
{const r=A.recommendations||{prose:'',usagePattern:[],productImprovements:[]};
 const s=sec('Recommendations');
 if(r.prose)s.appendChild($(`<p class="note">${r.prose}</p>`));
 s.appendChild($('<h3 style="margin:.9rem 0 .3rem;color:var(--ink2);font-size:.92rem">Usage-pattern <span style="color:var(--muted);font-weight:400">(for you)</span></h3>'));
 recCards(s,r.usagePattern);
 s.appendChild($('<h3 style="margin:.9rem 0 .3rem;color:var(--ink2);font-size:.92rem">Beadhive product improvements <span style="color:var(--muted);font-weight:400">(for maintainers)</span></h3>'));
 recCards(s,r.productImprovements);
 // Maintainer copy-feedback: a paste-ready message grounded in this run's own
 // productImprovements + ranked failures.groups (see buildFeedbackMessage), with a
 // select-text fallback for contexts (e.g. file://) where the Clipboard API is denied.
 const fbWrap=$('<div style="margin-top:.7rem"></div>');
 const fbHelp=$('<p class="note">Copies a paste-ready summary (versions + concrete failing calls) to send to the Beadhive maintainers.</p>');
 const fbBtn=$('<button type="button" class="copy-fb-btn">Copy feedback</button>');
 const fbTa=$('<textarea class="fb-fallback" readonly></textarea>');
 fbBtn.addEventListener('click',()=>copyFeedback(fbBtn,fbTa));
 fbWrap.appendChild(fbHelp);fbWrap.appendChild(fbBtn);fbWrap.appendChild(fbTa);
 s.appendChild(fbWrap);}
"""

HTML_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Beadhive Retro — interactive</title>
<style>{css}</style>
</head>
<body>
<div id="tip"></div>
<div class="wrap">
<header>
  <h1>bead<b>hive</b> retro</h1>
  <div class="sub" id="sub"></div>
</header>
<div id="app"></div>
<footer id="foot"></footer>
</div>
<script>{js}</script>
</body>
</html>
"""


def build_prose_summary(analysis: dict, recs: dict) -> str:
    """A short prose lead-in for the recommendations section, grounded in the same
    headline numbers as the "Headline" tiles above it -- never invents a figure."""
    cache = analysis.get("cache", {})
    cost = analysis.get("cost", {})
    n_sessions = len(analysis.get("activity", {}))
    n_usage = len(recs["usagePattern"])
    n_product = len(recs["productImprovements"])
    summary = (
        f"{n_sessions} session(s) analyzed; est. cost ${cost.get('total', 0):,.2f} at a "
        f"{cache.get('cacheRatio', 0):.1f}\u00d7 cache reuse ratio."
    )
    if n_usage or n_product:
        summary += (
            f" {n_usage} usage-pattern item(s) and {n_product} product-improvement item(s), "
            "each tied to a specific measured number below."
        )
    else:
        summary += " No grounded recommendations surfaced from this run's numbers."
    return summary


def render_html(analysis: dict, wallclock: dict | None = None) -> str:
    recs = generate_recommendations(analysis)
    # Shallow copy + one added key -- never mutate the caller's analysis dict. Also strip the
    # '<synthetic>' sentinel model id (SYNTHETIC_MODEL, always present in cost.unpriced.models,
    # normally with 0 tokens in every bucket; also possibly a models.beadsByModel key,
    # ts-attributed independent of pricing) here, once, server-side -- so it's never embedded
    # in A and can't leak into rendered copy however the client JS slices it (H1 anchor fix,
    # extended to models.beadsByModel per bh-cp-cmv). analysis.json itself is never touched --
    # this is a display-only filter on the copy embedded in the artifact.
    cost = analysis.get("cost", {})
    unpriced = cost.get("unpriced", {})
    clean_unpriced = {**unpriced, "models": [m for m in unpriced.get("models", []) if not is_synthetic_model(m)]}
    models = analysis.get("models", {})
    beads_by_model = models.get("beadsByModel", {})
    clean_models = {
        **models,
        "beadsByModel": {m: v for m, v in beads_by_model.items() if not is_synthetic_model(m)},
    }
    analysis = {
        **analysis,
        "cost": {**cost, "unpriced": clean_unpriced},
        "models": clean_models,
        "recommendations": {
            "prose": build_prose_summary(analysis, recs),
            "usagePattern": recs["usagePattern"],
            "productImprovements": recs["productImprovements"],
        },
    }
    # ensure_ascii=True (the default) escapes non-ASCII as \\uXXXX, which sidesteps the
    # U+2028/2029 line-separator gotcha; the "</" guard below is what actually matters for
    # not breaking out of the enclosing <script> tag if a value happens to contain it.
    json_str = json.dumps(analysis, ensure_ascii=True).replace("</", "<\\/")
    # wallclock is optional (see module docstring) -- embed `null` rather than omitting the
    # `const W = ...;` binding, so the chart JS's `if(W){...}else{...}` branch always has a
    # defined name to test.
    wallclock_json_str = json.dumps(wallclock, ensure_ascii=True).replace("</", "<\\/")
    js = (
        JS_TEMPLATE.replace("__EPIC_TOP_N__", str(EPIC_TOP_N))
        .replace("__SKILL_TOP_N__", str(SKILL_TOP_N))
        .replace("__SESSION_TOP_N__", str(SESSION_TOP_N))
        .replace("__SVG_NS_URL__", SVG_NS_URL)
        .replace("__ANALYSIS_JSON__", json_str)
        .replace("__WALLCLOCK_JSON__", wallclock_json_str)
    )
    return HTML_SHELL.format(css=build_css(), js=js)


def resolve_paths(infile, wallclock_in, out, run_dir_arg) -> tuple[str, str, str]:
    """(infile, wallclock_in, out) with explicit flags winning, else the resolved run-dir,
    else legacy cwd-relative filenames. wallclock_in has no existence guarantee -- it's a
    resolved path, not a promise the file is there (render_html handles a missing/None
    wallclock gracefully)."""
    run_dir = _rundir.resolve_run_dir(run_dir_arg)
    infile = infile or (os.path.join(run_dir, "analysis.json") if run_dir else "analysis.json")
    wallclock_in = wallclock_in or (os.path.join(run_dir, "wallclock.json") if run_dir else "wallclock.json")
    out = out or (os.path.join(run_dir, "report-artifact.html") if run_dir else "report-artifact.html")
    return infile, wallclock_in, out


def selftest() -> None:
    import os as _os
    import re
    import tempfile

    analysis = {
        "lifecycle": {
            "source": "id-heuristic",
            "byEpic": {
                f"bh-cp-{i}": {"planned": i % 4, "implemented": (i + 1) % 3, "merged": i % 2}
                for i in range(20)
            },
        },
        "failures": {
            "beadsBh": {"Bash": 2}, "other": {"Edit": 1},
            "examples": [
                {
                    "sessionId": "sess-1", "ts": "2026-07-20T10:25:00Z", "tool": "Bash",
                    "class": "raw-beads", "detail": "bd show broken",
                    "errorText": "error: bh-cp-broken not found",
                },
            ],
            "groups": [
                {
                    "commandShape": "bd show <id>", "count": 2, "classes": ["raw-beads"],
                    "sessions": ["sess-1"], "signatureCount": 1,
                    "signatures": [
                        {
                            "signature": "error: <id> not found", "count": 2,
                            "exemplar": {
                                "sessionId": "sess-1", "ts": "2026-07-20T10:25:00Z",
                                "tool": "Bash", "class": "raw-beads", "detail": "bd show broken",
                                "command": "bd show broken 2>&1",
                                "errorText": "error: bh-cp-broken not found",
                                "errorChars": 28,
                            },
                        }
                    ],
                },
            ],
            "groupsMeta": {"failuresGrouped": 2, "shapes": 1, "shapesShown": 1},
        },
        "skillReads": {
            "invocations": {
                "bhBeads": {f"bh:skill-{i}": i + 1 for i in range(15)},
                "other": {"artifact-design": 2},
            },
            "skillMdReads": 5,
            "byClass": {
                "beadhive": {f"bh:skill-{i}": i + 1 for i in range(15)},
                "rawBeads": {"beads:search": 3},
                "other": {"artifact-design": 2},
            },
        },
        # tool-class split (bh-cp-vce.1): fixture exercises all 4 classes, both the
        # direct/passthrough sub-split on raw-beads/raw-git, and >SKILL_TOP_N skill-shaped
        # byTool keys (same top-N/aggregate cardinality the old skillReads fixture exercised).
        "toolClasses": {
            "beadhive": {
                "total": 18, "failed": 0,
                "byTool": {"Bash": {"total": 3, "failed": 0}, **{f"bh:skill-{i}": {"total": i + 1, "failed": 0} for i in range(15)}},
            },
            "raw-beads": {
                "total": 6, "failed": 3,
                "direct": {"total": 3, "failed": 2}, "passthrough": {"total": 3, "failed": 1},
                "byTool": {"Bash": {"total": 3, "failed": 2}, "beads:search": {"total": 3, "failed": 1}},
            },
            "raw-git": {
                "total": 4, "failed": 1,
                "direct": {"total": 3, "failed": 1}, "passthrough": {"total": 1, "failed": 0},
                "byTool": {"Bash": {"total": 4, "failed": 1}},
            },
            "other": {
                "total": 3, "failed": 1,
                "byTool": {"Edit": {"total": 1, "failed": 1}, "artifact-design": {"total": 2, "failed": 0}},
            },
        },
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
        "activity": {
            f"sess-{i}": {"counts": {"planning": i % 3, "implementing": i % 2, "diagnosing": 1, "fixing": 0}, "suggested": "implementing"}
            for i in range(30)
        },
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

    assert out_html.startswith("<!doctype html>")
    assert out_html.rstrip().endswith("</html>")

    # (1) — the load-bearing namespace assertion: SVG marks are created via createElementNS
    # against the SVG namespace, never via innerHTML of bare <rect>/<circle> tags.
    assert "document.createElementNS(SVGNS" in out_html
    assert SVG_NS_URL in out_html
    innerhtml_raw_marks = re.search(r"innerHTML\s*=[^;\n]*<(rect|circle)\b", out_html)
    assert innerhtml_raw_marks is None, "raw <rect>/<circle> tags must never be assigned via innerHTML"

    # (2) — every analysis.json metric family is bound into the chart JS.
    for family in (
        "lifecycle", "failures", "skillReads", "toolClasses", "tokens", "cache", "activity",
        "models", "cost", "meta", "recommendations",
    ):
        assert f"A.{family}" in out_html, f"missing {family} family binding"

    # (3) — brand hexes from references/palette.md appear in the output.
    for hex_value in (BRAND_DARK["surface"], BRAND_DARK["accent"], BRAND_DARK["ink"], BRAND_DARK["ink2"], BRAND_DARK["cat"][0]):
        assert hex_value in out_html, f"missing brand hex {hex_value}"

    # (4) — zero external references: no CDN/script/stylesheet fetched over the network.
    assert re.search(r'<link[^>]+href', out_html) is None
    assert re.search(r'<script[^>]+src', out_html) is None
    assert re.search(r'(?:src|href)\s*=\s*["\']https?://', out_html) is None

    # top-N + aggregate scaling rule wired in for every high-cardinality family.
    assert "EPIC_TOP_N" in out_html and "SKILL_TOP_N" in out_html and "SESSION_TOP_N" in out_html
    assert "more" in out_html and "aggregate" in out_html

    # cost caveat lands on the visual itself (an SVG footnote), not just surrounding prose.
    assert "footnote" in out_html and "under-count" in out_html

    # conditional unpriced caveat (fix 7): the chart JS's cost-by-model footnote is static
    # source text either way (both branches of a client-side conditional are always present
    # in the shipped script), so the meaningful check is the DATA side -- re-render with an
    # all-priced cost block and confirm the unpriced model id itself (embedded only via
    # A.cost.unpriced.models) is gone from the emitted analysis JSON.
    priced_analysis = {**analysis, "cost": {**analysis["cost"], "unpriced": {
        "input": 0, "output": 0, "cache_read": 0, "eph5m": 0, "eph1h": 0, "models": [],
    }}}
    priced_html = render_html(priced_analysis)
    assert "claude-mystery-1" not in priced_html

    # (H1 anchor) the '<synthetic>' sentinel -- always present in cost.unpriced.models with 0
    # tokens in every bucket in the normal case -- must never leak into the emitted analysis
    # JSON (and therefore can never be interpolated into rendered copy), whether or not there's
    # also a real unpriced model alongside it. The client-side gate/footnote text itself is
    # static JS source present in every render (both ternary branches always ship, per the
    # comment above) -- true text-visibility coverage for the "0 tokens -> emit nothing" gate
    # lives in render.py's selftest, which renders server-side with no client JS involved and
    # whose recommendations render.py's generate_recommendations() feeds this artifact too.
    synthetic_analysis = {**analysis, "cost": {**analysis["cost"], "unpriced": {
        "input": 0, "output": 0, "cache_read": 0, "eph5m": 0, "eph1h": 0, "models": ["<synthetic>"],
    }}}
    synthetic_html = render_html(synthetic_analysis)
    assert "<synthetic>" not in synthetic_html
    assert "claude-mystery-1" not in synthetic_html

    mixed_analysis = {**analysis, "cost": {**analysis["cost"], "unpriced": {
        "input": 5, "output": 0, "cache_read": 0, "eph5m": 0, "eph1h": 0,
        "models": ["<synthetic>", "claude-mystery-1"],
    }}}
    mixed_html = render_html(mixed_analysis)
    assert "<synthetic>" not in mixed_html
    assert "claude-mystery-1" in mixed_html

    # bh-cp-cmv: '<synthetic>' (SYNTHETIC_MODEL) also shows up as a models.beadsByModel key --
    # attributed straight off tool-event timestamps, independent of pricing -- feeding the
    # "Bead lifecycle events by model" chart+table. Must never render there either, while a
    # real model alongside it still does.
    beads_by_model_analysis = {
        **analysis,
        "models": {
            **analysis["models"],
            "beadsByModel": {
                SYNTHETIC_MODEL: {"planned": 1, "implemented": 0, "merged": 0},
                "claude-sonnet-5": {"planned": 1, "implemented": 1, "merged": 0},
            },
        },
    }
    beads_by_model_html = render_html(beads_by_model_analysis)
    assert SYNTHETIC_MODEL not in beads_by_model_html
    assert "sonnet-5" in beads_by_model_html

    # header shows all four distinct meta.* version fields (og2.1), not just bh/CC.
    assert "A.meta.pluginVersion" in out_html
    assert "A.meta.bdVersion" in out_html

    # (5) cache-expiry scatter: Y-axis is labelled with units, not a bare number scale.
    assert "wasted tokens" in out_html

    # (6) percentage bars are CSS %-width segments, not a fixed-viewBox SVG bar that
    # letterboxes inside a wider card.
    assert "pctbar" in out_html and "pctseg" in out_html
    assert "width:${pct}%" in out_html

    # (7) lifecycle-by-epic: the "+N more" bundle is a text/table note, not a chart bar
    # that dwarfs the real top-N epics.
    assert "omitted from the chart" in out_html

    # (8) failed tool calls are grouped per tool/skill name, stacked/colored by the 4-way
    # tool class (bh-cp-vce.2 fix 4), not the old flat beads/bh vs other binary.
    assert "by tool, beadhive / raw-beads / raw-git / other" in out_html
    assert "toolNames" in out_html

    # (9) skill invocations get the same 4-way tool-class stacked treatment.
    assert "beadhive / raw-beads / raw-git / other" in out_html

    # (9b) tool-class coloring: fixed palette slots 1-4 (amber/teal/violet/moss) mapped in
    # order to (beadhive, raw-beads, raw-git, other), a legend, and the purpose caption —
    # shared by both the failures and skills charts via TOOL_CLASS_COLORS/TOOL_CLASS_CAPTION.
    assert "TOOL_CLASSES" in out_html and "TOOL_CLASS_COLORS" in out_html
    for hex_value in (BRAND_DARK["cat"][0], BRAND_DARK["cat"][1], BRAND_DARK["cat"][2], BRAND_DARK["cat"][3]):
        assert hex_value in out_html, f"missing tool-class palette hex {hex_value}"
    assert "beadhive = native bh commands and bh: skills" in out_html

    # (10) recommendations + prose — previously entirely missing from this artifact.
    assert "A.recommendations" in out_html
    assert "Recommendations" in out_html
    assert "Usage-pattern" in out_html
    assert "Beadhive product improvements" in out_html

    # (11) rich recommendation boxes: each item renders as a what/why card, not a bare <li>.
    assert "rec-card" in out_html and "rec-what" in out_html
    assert "recCards(s,r.usagePattern)" in out_html
    assert "recCards(s,r.productImprovements)" in out_html

    # (12) maintainer copy-feedback button: Clipboard API primary path, select-text fallback
    # (file:// contexts often deny navigator.clipboard), message grounded in concrete
    # failures.examples (offending command + error text + session id) and the version stamp.
    assert "Copy feedback" in out_html
    assert "navigator.clipboard" in out_html and "navigator.clipboard.writeText" in out_html
    assert "fb-fallback" in out_html and "Select & copy below" in out_html
    assert "buildFeedbackMessage" in out_html
    assert "A.failures&&A.failures.examples" in out_html or "A.failures && A.failures.examples" in out_html
    # bh-cp-t46.2: the message leads with ranked clusters ("this failed N times") and carries
    # the exemplar's whole command + complete error text; examples stays as the fallback for a
    # pre-grouping analysis.json.
    assert "A.failures&&A.failures.groups" in out_html
    assert "Failing calls from this run (most frequent first)" in out_html
    assert "feedbackFailureLines" in out_html
    assert '"commandShape": "bd show <\\/id>"' not in out_html  # sanity: no mangled JSON escape
    assert '"commandShape": "bd show <id>"' in out_html  # the clusters reach the page's data

    # (13) full-width SVG charts: the shared SVG() helper sizes by container (width:'100%' +
    # preserveAspectRatio), not a fixed pixel width attribute that letterboxes in a wider card.
    assert "width:'100%'" in out_html
    assert "preserveAspectRatio:'xMidYMid meet'" in out_html
    assert "width:w,height:h" not in out_html  # the old fixed-size attribute pair is gone
    # grounded in this fixture's actual numbers, not generic filler:
    assert "Handoff opportunity in session sess-1" in out_html  # from cache.expiryEvents
    assert "pricing.json has no rate for model family/families claude-mystery-1" in out_html

    # ---------------------------------------------------------------------------------------
    # wallclock.json (bh-cp-t46.5): the W binding, missing/present fallback, family coverage,
    # the record-gap caveat legible on the render itself, and the humanGate/toolTime
    # double-counting guard (its own acceptance criterion, quoted by name in the bead).
    # ---------------------------------------------------------------------------------------
    assert "const W = null;" in out_html  # no wallclock passed to the top-level render_html() call
    assert "wallclock.json</code> not found for this run" in out_html

    TIMING_CAVEAT = "derived from record gaps, not measured"
    wallclock = {
        "totals": {
            "sessions": 2, "sessionSpanSec": 7200.0, "inferenceSec": 1800.0, "toolSec": 3000.0,
            "humanIdleSec": 2000.0, "unattributedSec": 400.0,
            "note": f"session-span split into inference/tool/humanIdle/unattributed; {TIMING_CAVEAT}.",
        },
        "humanIdle": {
            "byClass": {
                "approval-shaped": {"count": 3, "sec": 90.0},
                "direction": {"count": 2, "sec": 1800.0},
                "parked": {"count": 1, "sec": 110.0},
            },
            "recoverableSec": 90.0,
            "recoverableNote": "approval-shaped: a supervisor-agent loop could plausibly have "
                               "answered these without a human.",
            "top": [],
            "note": f"gapSec is {TIMING_CAVEAT} (human-prompt ts minus the preceding record's ts).",
        },
        "inferenceRate": {
            "turns": 40, "ratedTurns": 30, "p25TokPerSec": 12.5, "medianTokPerSec": 22.0,
            "p75TokPerSec": 35.0, "excessSecondsVsP75": 210.0, "slowTurnCount": 2,
            "slowTurnSec": 500.0, "top": [],
            "note": f"turn durationSec is {TIMING_CAVEAT}.",
        },
        "toolTime": {
            "byTool": {}, "byClass": {
                "test": {"count": 12, "sec": 900.0, "failed": 1},
                "beadhive": {"count": 8, "sec": 300.0, "failed": 0},
            },
            "note": f"durationSec per call is {TIMING_CAVEAT}.",
            "byClassNote": "byClass/byTool sum every call's durationSec individually; parallel "
            "calls overlap in real time, so these totals are inflated vs totals.toolSec.",
            "slowest": [], "slowestByClass": {},
        },
        "testChurn": {
            "commands": [],
            "repeated": [
                {"class": "test", "command": "pytest tests/test_x.py <a", "runs": 5, "sec": 250.0,
                 "sessions": 2, "example": "pytest tests/test_x.py", "avgSec": 50.0},
            ],
            "repeatedCount": 1, "retestTaxSec": 200.0,
            "retestTaxNote": "seconds in runs 2..N of every command run >=3 times.",
            "mergeAdjacent": [], "mergeAdjacentSec": 0.0, "mergeAdjacentRuns": 0,
            "mergeAdjacentUniqueRuns": 1, "mergeAdjacentUniqueSec": 40.0,
            "mergeAdjacentNote": "windows overlap; the unique* figures count each run once.",
            "note": f"every sec figure here is {TIMING_CAVEAT} (summed).",
        },
        "humanGate": {
            "count": 4, "sec": 220.0,
            "byTool": {"AskUserQuestion": {"count": 3, "sec": 180.0}, "ExitPlanMode": {"count": 1, "sec": 40.0}},
            "top": [],
            "note": "AskUserQuestion/ExitPlanMode/EnterPlanMode block on a human answer but are "
            "recorded as ordinary tool calls, so this figure is a labelled SUBSET already "
            "INSIDE totals.toolSec / toolTime.byClass['other'] / toolTime.byTool above — do "
            "NOT add humanGate.sec on top of those or you will double count.",
        },
        "plausiblyAutomatable": {
            "sec": 310.0, "humanIdleRecoverableSec": 90.0, "humanGateSec": 220.0,
            "note": "approval-shaped human idle plus gate-tool wait — deliberately EXCLUDES "
            "humanIdle's direction and parked time. humanGateSec is also counted inside "
            "totals.toolSec, so this total is not a partition of session span alongside totals.",
        },
        "suspectedApprovalGate": {
            "count": 1, "sec": 60.0,
            "top": [{"sessionId": "sess-1", "tool": "Bash", "cmd": "git status && echo <ok>", "durationSec": 60.0}],
            "note": f"heuristic, not observed: a normally-instant command that took a long "
            f"time was probably parked in a permission prompt. Durations are otherwise "
            f"{TIMING_CAVEAT}, same as toolTime.",
        },
        "bySession": {},
    }
    wc_html = render_html(analysis, wallclock=wallclock)

    # W is bound to the real payload now, not null. Note: the "not found" fallback text
    # itself is static JS source that ships in every render either way (both branches of the
    # client-side `if(W){...}else{...}` are always present in the shipped script — same
    # "static source text either way" nuance the cost-unpriced footnote check above already
    # documents); the meaningful check is the DATA side, i.e. W is no longer null.
    assert "const W = null;" not in wc_html
    assert '"sessionSpanSec": 7200.0' in wc_html

    # every wallclock.json top-level family is charted (createElementNS-built, via hbars/
    # vbars/stackedBar — see the namespace assertion (1) above, which covers this file's
    # entire output including these new sections).
    for family in (
        "W.totals", "W.humanIdle", "W.inferenceRate", "W.toolTime", "W.testChurn",
        "W.humanGate", "W.suspectedApprovalGate", "W.plausiblyAutomatable",
    ):
        assert family in wc_html, f"missing wallclock family binding {family}"

    # the record-gap caveat is legible on the render itself (each family's own `.note`),
    # not only in wallclock.py's docstring or metrics.md prose.
    assert TIMING_CAVEAT in wc_html

    # humanGate is rendered as an explicit SUBSET of Tool time, never summed with it: the
    # bead's own acceptance wording ("gate-tool time is labelled as sitting inside tool time
    # wherever both are shown together") is on the page, and no computed total anywhere adds
    # toolTime's byClass sum (900+300=1,200s) to humanGate's 220s.
    assert "Subset, not additive" in wc_html
    assert "already counted inside" in wc_html
    assert "1420" not in wc_html  # 900+300 (toolTime) + 220 (humanGate) never appears as a sum

    # plausiblyAutomatable renders its own deliberately-scoped sum (90 + 220 = 310s) without
    # conflating it with the toolTime/humanGate subset relationship above.
    assert "310.0" in wc_html

    # raw command/tool-class text (shell metacharacters included) is escaped client-side, at
    # DOM-build time, via this file's own esc() -- table()/hov() don't escape by default
    # (existing analysis.json call sites only ever pass enum-shaped strings), so every JS
    # call site that embeds wallclock.json free text must route it through esc() first. The
    # escaping itself only happens when a browser runs the script (this Python selftest can't
    # execute JS), so assert the JS SOURCE calls esc() at each free-text call site rather than
    # asserting an already-escaped substring in the static output.
    for call_site in (
        "esc(r.command)", "esc(c.tool)", "esc(c.cmd)", "esc((c.sessionId||'').slice(0,8))",
        "esc(tc.retestTaxNote)", "esc(tc.mergeAdjacentNote)",
    ):
        assert call_site in wc_html, f"free-text field not escaped: {call_site}"

    print("render_artifact.py wallclock coverage: OK")

    # run-dir resolution: explicit flags win; else resolved run-dir; else legacy cwd filenames.
    orig_root, orig_latest = _rundir.RETROS_ROOT, _rundir.LATEST_POINTER
    tmpdir = tempfile.mkdtemp()
    _rundir.RETROS_ROOT = _os.path.join(tmpdir, "retros")
    _rundir.LATEST_POINTER = _os.path.join(_rundir.RETROS_ROOT, "latest")
    try:
        assert resolve_paths(None, None, None, None) == ("analysis.json", "wallclock.json", "report-artifact.html")

        run_dir, _ = _rundir.new_run_dir("20260101-000000-deadbeef")
        _rundir.write_latest_pointer(run_dir)
        assert resolve_paths(None, None, None, None) == (
            _os.path.join(run_dir, "analysis.json"),
            _os.path.join(run_dir, "wallclock.json"),
            _os.path.join(run_dir, "report-artifact.html"),
        )
        assert resolve_paths(None, None, "custom.html", None) == (
            _os.path.join(run_dir, "analysis.json"),
            _os.path.join(run_dir, "wallclock.json"),
            "custom.html",
        )
        assert resolve_paths(None, "custom-wallclock.json", None, None) == (
            _os.path.join(run_dir, "analysis.json"),
            "custom-wallclock.json",
            _os.path.join(run_dir, "report-artifact.html"),
        )
        assert resolve_paths(None, None, None, "/explicit/dir") == (
            "/explicit/dir/analysis.json",
            "/explicit/dir/wallclock.json",
            "/explicit/dir/report-artifact.html",
        )
    finally:
        _rundir.RETROS_ROOT, _rundir.LATEST_POINTER = orig_root, orig_latest

    print("render_artifact.py --selftest: OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="infile", default=None, help="analysis.json path (default: <run-dir>/analysis.json)")
    parser.add_argument("--wallclock-in", dest="wallclock_in", default=None, help="wallclock.json path (default: <run-dir>/wallclock.json; missing file renders a fallback note, not an error)")
    parser.add_argument("--out", default=None, help="default: <run-dir>/report-artifact.html")
    parser.add_argument("--run-dir", dest="run_dir", default=None, help="run-dir to resolve analysis.json/wallclock.json/report-artifact.html in (default: latest pointer, else cwd)")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    infile, wallclock_in, out = resolve_paths(args.infile, args.wallclock_in, args.out, args.run_dir)
    with open(infile) as f:
        analysis = json.load(f)

    wallclock = None
    if os.path.exists(wallclock_in):
        with open(wallclock_in) as f:
            wallclock = json.load(f)

    with open(out, "w") as f:
        f.write(render_html(analysis, wallclock=wallclock))

    print(f"render_artifact.py: rendered {infile} (+ wallclock: {'yes' if wallclock else 'no'}) -> {out}")


if __name__ == "__main__":
    main()
