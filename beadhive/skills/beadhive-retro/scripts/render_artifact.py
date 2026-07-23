#!/usr/bin/env python3
"""Charted artifact: render analysis.json into a single self-contained report-artifact.html.

Stdlib only. This is the CHARTED sibling of render.py: inline CSS + inline JS builds
interactive SVG charts (bars, stacked bars, a scatter, small multiples) for every
analysis.json metric family, still with zero external refs (no CDN, no external fonts/
scripts/stylesheets) — everything ships inline in the one output file.

CRITICAL: every SVG mark is created via `document.createElementNS` (the SVG namespace),
never by assigning `element.innerHTML` to a string containing bare `<rect>`/`<circle>` tags
outside an `<svg>` context — those land in the HTML namespace and silently fail to render in
Brave/Chromium. `--selftest` asserts this directly (see selftest()).

Resolves analysis.json/writes report-artifact.html the same way render.py does: explicit
`--run-dir` wins, else the `latest` pointer, else legacy cwd-relative defaults. `--in`/`--out`
always override individually.

Usage:
    render_artifact.py [--in analysis.json] [--out report-artifact.html] [--run-dir DIR]
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
from render import generate_recommendations

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
const SVGNS = '__SVG_NS_URL__';
// SVG elements MUST be created in the SVG namespace via createElementNS — assigning
// innerHTML with bare <rect>/<circle> tags puts them in the HTML namespace and they
// silently fail to render in Brave/Chromium. Every mark below goes through E().
function E(tag,attrs){const e=document.createElementNS(SVGNS,tag);for(const k in attrs)e.setAttribute(k,attrs[k]);return e;}
function T(attrs,str){const t=E('text',attrs);t.textContent=str;return t;}
function SVG(w,h){return E('svg',{viewBox:`0 0 ${w} ${h}`,width:w,height:h,role:'img'});}
const $=(h)=>{const t=document.createElement('template');t.innerHTML=h.trim();return t.content.firstChild;};
const fmt=(n)=>n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'k':(''+Math.round(n));
const usd=(n)=>'$'+n.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
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

// one small-multiple tile: a 110x12 mini stacked bar for one session's signal split.
function smallMultiple(grid,keys,cols,label,counts){
 const tot=keys.reduce((x,k)=>x+counts[k],0)||1;
 const cell=$(`<div class="sm"><div class="t">${label}</div></div>`);
 const svg=SVG(110,12);let x=0;
 keys.forEach((k,i)=>{const w=counts[k]/tot*110;if(w>0){
   const r=E('rect',{class:'seg',x:x,y:0,width:Math.max(0,w-0.5),height:12,fill:cols[i]});
   hov(r,`<b>${label}</b><br>${k}: ${counts[k]}`);svg.appendChild(r);}x+=w;});
 cell.appendChild(svg);grid.appendChild(cell);}

document.getElementById('sub').innerHTML =
  `${Object.keys(A.activity).length} sessions · bh <code>${A.meta.bhVersion}</code> · plugin <code>${A.meta.pluginVersion}</code> · bd <code>${A.meta.bdVersion}</code> · CC ${(A.meta.ccVersions||['unknown']).join(',')} · cost <span class="est">estimated</span> asOf ${A.cost.pricingAsOf}`;
document.getElementById('foot').textContent =
  `Generated ${A.meta.generatedAt} · every number bound verbatim from analysis.json · cost is an estimate, not a billed figure`;

// headline tiles
{const s=sec('Headline');const g=$('<div class="tiles"></div>');
 [[A.cache.cacheRatio.toFixed(1)+'×','cache reuse ratio (read ÷ uncached+writes)'],
  [A.cache.significantExpiryEventCount,'significant cache-expiry events'],
  [usd(A.cost.total),'est. cost (priced models only)'],
  [usd(A.cost.cacheWasteUSD),'est. cache-waste cost'],
  [Object.keys(A.activity).length,'Beadhive sessions']
 ].forEach(([n,l])=>g.appendChild($(`<div class="tile"><div class="n">${n}</div><div class="l">${l}</div></div>`)));
 s.appendChild(g);}

// tokens — stacked bar (categorical color job: token category is unordered, one hue each)
{const t=A.tokens.exact.totals;
 const s=sec('Token split <span class="accent">·</span> where the tokens went',
   'cache_read dominates when the pipeline is cache-heavy. approximateFileIo omitted (chars/4 estimate, not exact).');
 const order=[['input',t.input,CATS[0]],['output',t.output,CATS[1]],['cache_read',t.cache_read,CATS[2]],['cache_creation',t.cache_creation,CATS[3]]];
 legend(s,order.map(o=>[o[2],o[0]]));
 stackedBar(s,order.map(o=>({label:o[0],value:o[1],color:o[2]})));
 const tot=order.reduce((a,o)=>a+o[1],0)||1;
 table(s,['category','tokens','% of total'],order.map(o=>[o[0],fmt(o[1]),(o[1]/tot*100).toFixed(1)+'%']));}

// cost by model — stacked bar (categorical: cost components), unpriced caveat is a
// footnote baked into the chart itself (not just the surrounding prose).
{const bm=A.cost.byModel,fams=Object.keys(bm),up=A.cost.unpriced||{models:[],cache_read:0};
 const comps=[['inputCost','input',CATS[0]],['outputCost','output',CATS[1]],['cacheReadCost','cache read',CATS[2]],['cacheWriteCost','cache write',CATS[3]]];
 const hasUnpriced=(up.models||[]).length>0;
 const s=sec('Estimated cost by model',
   `estimate from references/pricing.json (asOf ${A.cost.pricingAsOf}), not billed.` +
   (hasUnpriced?` <b class="est">Unpriced &amp; excluded:</b> ${up.models.join(', ')} — ${fmt(up.cache_read||0)} cache-read tokens with no rate, so the ${usd(A.cost.total)} total is an <b>under-count</b>.`:''));
 legend(s,comps.map(c=>[c[2],c[1]]));
 vbars(s,fams.map(f=>({name:f.replace('claude-',''),vals:comps.map(c=>bm[f][c[0]])})),
   comps.map(c=>({name:c[1],color:c[2]})),
   {stacked:true,fmtY:usd,footnote:hasUnpriced?`* excludes unpriced: ${up.models.join(', ')} — estimate is an under-count`:'* estimate only, not a billed figure'});
 const rows=fams.map(f=>[f.replace('claude-',''),usd(bm[f].inputCost),usd(bm[f].outputCost),usd(bm[f].cacheReadCost),usd(bm[f].cacheWriteCost),usd(bm[f].totalCost)]);
 if(hasUnpriced)rows.push(['unpriced ('+up.models.join('+')+')','—','—',fmt(up.cache_read||0)+' tok','—','n/a']);
 table(s,['model','input','output','cache read','cache write','total'],rows);}

// bead lifecycle events by model — stacked bar (ordered/sequential color job: the stages
// planned -> implemented -> merged are a sequence, not an unordered category)
{const bbm=A.models.beadsByModel,fams=Object.keys(bbm);
 const stages=[['planned',CATS[0]],['implemented',CATS[1]],['merged',CATS[3]]];
 const s=sec('Bead lifecycle events by model',
   'approximate ts→model attribution (metrics.md f).');
 legend(s,stages.map(x=>[x[1],x[0]]));
 vbars(s,fams.map(f=>({name:f.replace('claude-',''),vals:stages.map(st=>bbm[f][st[0]])})),
   stages.map(st=>({name:st[0],color:st[1]})),{});
 table(s,['model','planned','implemented','merged'],fams.map(f=>[f.replace('claude-',''),bbm[f].planned,bbm[f].implemented,bbm[f].merged]));}

// cache-expiry scatter — idle gap (x, log) x wasted tokens (y); status color (warning)
{const ev=A.cache.expiryEvents.slice();
 const s=sec('Cache-expiry events <span class="accent">·</span> idle gap × wasted tokens',
   'each point = a cache that went cold after an idle gap and had to be re-fed. Up-and-right = a fresh handoff would have been cheaper.');
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
   `aggregate turn-signals across ${acts.length} sessions; small multiples capped at top ${SESSION_TOP_N} by signal volume` +
   (rest.length?`, remaining ${rest.length} folded into one "+N more" tile (SKILL.md scaling rule).`:'.'));
 legend(s,keys.map((k,i)=>[cols[i],k]));
 stackedBar(s,keys.map((k,i)=>({label:k,value:agg[k],color:cols[i]})));
 table(s,['activity','total turn-signals'],keys.map(k=>[k,agg[k]]));
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
 const s=sec(`Lifecycle by epic <span class="accent">·</span> top ${EPIC_TOP_N} of ${rows.length}`,
   `source: <code>${A.lifecycle.source}</code> — epic grouping inferred from bead-id shape, not verified parent links.` +
   (rest.length?` Top ${EPIC_TOP_N} epics by activity shown in the chart; remaining ${rest.length} epics' bundled totals (${fmt(restSums[0])} planned, ${fmt(restSums[1])} impl, ${fmt(restSums[2])} merged) are large enough to dwarf the real top-N bars, so they're omitted from the chart and folded into one "+N more" table row instead.`:''));
 legend(s,stages.map(x=>[x[1],x[0]]));
 vbars(s,groups,stages.map(st=>({name:st[0],color:st[1]})),{stacked:true});
 const tableRows=topN.map(r=>[r.name,r.vals[0],r.vals[1],r.vals[2]]);
 if(rest.length)tableRows.push([`+${rest.length} more`,restSums[0],restSums[1],restSums[2]]);
 table(s,['epic','planned','impl','merged'],tableRows);}

// skill reads — top-N + aggregate bar (categorical color job: skill names are unordered).
// Absent from the v1 form-map; added per SKILL.md's form-map coverage fix.
{const inv=A.skillReads.invocations||{};
 const bh=inv.bhBeads||{},oth=inv.other||{};
 const rows=Object.entries(Object.assign({},bh,oth)).sort((a,b)=>b[1]-a[1]);
 const shown=rows.slice(0,SKILL_TOP_N),rest=rows.slice(SKILL_TOP_N);
 // One bar per skill NAME, stacked/colored by the same binary bh:/beads: vs other tier
 // used for the failed-tool-calls chart — a skill only ever lands in one tier, so this
 // reads as "bar height = invocations, bar color = which tier", not a real 2-part stack.
 const groups=shown.map(([k])=>({name:k,vals:[bh[k]||0,oth[k]||0]}));
 let restSum=0;if(rest.length)restSum=rest.reduce((a,[,v])=>a+v,0);
 const s=sec('Skill invocations <span class="accent">·</span> bh:/beads: vs other',
   `by invocation count, top ${SKILL_TOP_N} of ${rows.length} shown in the chart` +
   (rest.length?` (remaining ${rest.length} skills — ${fmt(restSum)} invocations — see the table below)`:'') +
   `. SKILL.md itself was read ${A.skillReads.skillMdReads} time(s) across sessions.`);
 legend(s,[[CATS[0],'bh:/beads:'],[CATS[7],'other']]);
 if(groups.length)vbars(s,groups,[{name:'bh:/beads:',color:CATS[0]},{name:'other',color:CATS[7]}],{stacked:true});
 table(s,['skill','invocations'],rows.map(([k,v])=>[k,v]));}

// failed tool calls — grouped bar (status color job: failed is a state, beads/bh vs other
// is the grouping). Absent from the v1 form-map; added per SKILL.md's form-map coverage fix.
{const f=A.failures;const bh=f.beadsBh||{},oth=f.other||{};
 // One bar per failing TOOL NAME (Bash, Edit, Read, ...), stacked/colored by the binary
 // beads/bh vs other tier — a tool like Bash can fail in both tiers (a beads/bh command
 // vs any other), so this is a real 2-color stack, unlike the skill-invocations chart.
 const toolNames=Array.from(new Set([...Object.keys(bh),...Object.keys(oth)]))
   .sort((a,b)=>((bh[b]||0)+(oth[b]||0))-((bh[a]||0)+(oth[a]||0)));
 const s=sec('Failed tool calls <span class="accent">·</span> by tool, beads/bh vs other',
   'one bar per failing tool; stacked/colored by whether that failure was a bd/bh invocation or another tool.');
 legend(s,[[CATS[0],'beads/bh'],[CATS[7],'other']]);
 if(toolNames.length){
   vbars(s,toolNames.map(t=>({name:t,vals:[bh[t]||0,oth[t]||0]})),
     [{name:'beads/bh',color:CATS[0]},{name:'other',color:CATS[7]}],{stacked:true});
 }else{s.appendChild($('<p class="note">No failed tool calls this run.</p>'));}
 const rows=Object.entries(bh).map(([k,v])=>['beads/bh · '+k,v])
   .concat(Object.entries(oth).map(([k,v])=>['other · '+k,v]))
   .sort((a,b)=>b[1]-a[1]);
 table(s,['group / tool','count'],rows);}

// recommendations — grounded two-tier roll-up, ported from render.py's
// generate_recommendations() (the biggest gap in this artifact per SKILL.md): a short
// prose summary, then Usage-pattern (for the user) and Beadhive product-improvement
// (for maintainers, version-stamped) tiers. Every item cites a specific analysis.json
// number -- computed once in Python, this block only renders what A.recommendations
// already carries.
{const r=A.recommendations||{prose:'',usagePattern:[],productImprovements:[]};
 const s=sec('Recommendations');
 if(r.prose)s.appendChild($(`<p class="note">${r.prose}</p>`));
 const bullets=(items)=>items.length
   ?`<ul>${items.map(i=>`<li>${i}</li>`).join('')}</ul>`
   :`<p class="note">None grounded in this run's data.</p>`;
 s.appendChild($('<h3 style="margin:.9rem 0 .3rem;color:var(--ink2);font-size:.92rem">Usage-pattern <span style="color:var(--muted);font-weight:400">(for you)</span></h3>'));
 s.appendChild($(bullets(r.usagePattern)));
 s.appendChild($('<h3 style="margin:.9rem 0 .3rem;color:var(--ink2);font-size:.92rem">Beadhive product improvements <span style="color:var(--muted);font-weight:400">(for maintainers)</span></h3>'));
 s.appendChild($(bullets(r.productImprovements)));}
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
            f" {n_usage} usage-pattern item(s) and {n_product} product-improvement item(s) "
            "below, each grounded in a specific analysis.json number."
        )
    else:
        summary += " No grounded recommendations surfaced from this run's numbers."
    return summary


def render_html(analysis: dict) -> str:
    recs = generate_recommendations(analysis)
    # Shallow copy + one added key -- never mutate the caller's analysis dict.
    analysis = {
        **analysis,
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
    js = (
        JS_TEMPLATE.replace("__EPIC_TOP_N__", str(EPIC_TOP_N))
        .replace("__SKILL_TOP_N__", str(SKILL_TOP_N))
        .replace("__SESSION_TOP_N__", str(SESSION_TOP_N))
        .replace("__SVG_NS_URL__", SVG_NS_URL)
        .replace("__ANALYSIS_JSON__", json_str)
    )
    return HTML_SHELL.format(css=build_css(), js=js)


def resolve_paths(infile, out, run_dir_arg) -> tuple[str, str]:
    """(infile, out) with explicit flags winning, else the resolved run-dir, else legacy
    cwd-relative filenames."""
    run_dir = _rundir.resolve_run_dir(run_dir_arg)
    infile = infile or (os.path.join(run_dir, "analysis.json") if run_dir else "analysis.json")
    out = out or (os.path.join(run_dir, "report-artifact.html") if run_dir else "report-artifact.html")
    return infile, out


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
        "failures": {"beadsBh": {"Bash": 2}, "other": {"Edit": 1}},
        "skillReads": {
            "invocations": {
                "bhBeads": {f"bh:skill-{i}": i + 1 for i in range(15)},
                "other": {"artifact-design": 2},
            },
            "skillMdReads": 5,
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
        "lifecycle", "failures", "skillReads", "tokens", "cache", "activity", "models",
        "cost", "meta", "recommendations",
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

    # conditional unpriced caveat (fix 7): the chart JS's "Unpriced & excluded" ternary
    # is static source text either way (both branches of a client-side conditional are
    # always present in the shipped script), so the meaningful check is the DATA side --
    # re-render with an all-priced cost block and confirm the unpriced model id itself
    # (embedded only via A.cost.unpriced.models) is gone from the emitted analysis JSON.
    priced_analysis = {**analysis, "cost": {**analysis["cost"], "unpriced": {
        "input": 0, "output": 0, "cache_read": 0, "eph5m": 0, "eph1h": 0, "models": [],
    }}}
    priced_html = render_html(priced_analysis)
    assert "claude-mystery-1" not in priced_html

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

    # (8) failed tool calls are grouped per tool name, stacked/colored by beads/bh vs other.
    assert "by tool, beads/bh vs other" in out_html
    assert "toolNames" in out_html

    # (9) skill invocations get the same two-tier (bh:/beads: vs other) stacked treatment.
    assert "'bh:/beads:'" in out_html

    # (10) recommendations + prose — previously entirely missing from this artifact.
    assert "A.recommendations" in out_html
    assert "Recommendations" in out_html
    assert "Usage-pattern" in out_html
    assert "Beadhive product improvements" in out_html
    # grounded in this fixture's actual numbers, not generic filler:
    assert "Handoff opportunity in session sess-1" in out_html  # from cache.expiryEvents
    assert "pricing.json has no rate for model family/families claude-mystery-1" in out_html

    # run-dir resolution: explicit flags win; else resolved run-dir; else legacy cwd filenames.
    orig_root, orig_latest = _rundir.RETROS_ROOT, _rundir.LATEST_POINTER
    tmpdir = tempfile.mkdtemp()
    _rundir.RETROS_ROOT = _os.path.join(tmpdir, "retros")
    _rundir.LATEST_POINTER = _os.path.join(_rundir.RETROS_ROOT, "latest")
    try:
        assert resolve_paths(None, None, None) == ("analysis.json", "report-artifact.html")

        run_dir, _ = _rundir.new_run_dir("20260101-000000-deadbeef")
        _rundir.write_latest_pointer(run_dir)
        assert resolve_paths(None, None, None) == (
            _os.path.join(run_dir, "analysis.json"),
            _os.path.join(run_dir, "report-artifact.html"),
        )
        assert resolve_paths(None, "custom.html", None) == (
            _os.path.join(run_dir, "analysis.json"),
            "custom.html",
        )
        assert resolve_paths(None, None, "/explicit/dir") == (
            "/explicit/dir/analysis.json",
            "/explicit/dir/report-artifact.html",
        )
    finally:
        _rundir.RETROS_ROOT, _rundir.LATEST_POINTER = orig_root, orig_latest

    print("render_artifact.py --selftest: OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="infile", default=None, help="analysis.json path (default: <run-dir>/analysis.json)")
    parser.add_argument("--out", default=None, help="default: <run-dir>/report-artifact.html")
    parser.add_argument("--run-dir", dest="run_dir", default=None, help="run-dir to resolve analysis.json/report-artifact.html in (default: latest pointer, else cwd)")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    infile, out = resolve_paths(args.infile, args.out, args.run_dir)
    with open(infile) as f:
        analysis = json.load(f)

    with open(out, "w") as f:
        f.write(render_html(analysis))

    print(f"render_artifact.py: rendered {infile} -> {out}")


if __name__ == "__main__":
    main()
