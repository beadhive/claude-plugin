# Beadhive honeycomb palette

This is the **brand instance** of the `dataviz` skill's color method (see that skill's
`references/palette.md` / `color-formula.md` for the method itself — jobs, six checks, the
validator). Every value below is validated, not eyeballed: run
`node <dataviz>/scripts/validate_palette.js` on the categorical set for both modes before
changing anything here (see "Validation" at the bottom for the exact commands + output).

**Dark-first.** The dark columns are this palette's primary/default surface — `report.html`
renders dark by default. Light values exist for completeness (a printed report, a light-theme
Artifact, embedding) and are validated to the same bar.

Starting tokens were eyeballed from `beadhive/docs/assets/brand/banner-readme.png` (surface-dark
`#17140C`, hex-grid `#2A2413`, amber `#F2B617`, cream ink `#F3E9D5`, bronze `#C8972E`, muted-tan
`#A99A79`) — five/six brand anchors, not a full 8-slot categorical set. The categorical,
sequential, diverging, and status scales below were *derived* from those anchors (amber as the
fixed slot-1 anchor) and then snapped to pass the validator, per `color-formula.md`'s
"Snap-to-passing" and "Deriving an order when a system has no theme yet" procedures.

## How to use these values

Same pattern as the dataviz reference: define the slots you use as CSS custom properties in a
local `<style>` block, dark as the default and a `(prefers-color-scheme: light)` override for the
light values (dark-first, so light is the override here — opposite of the dataviz reference's
light-default convention):

```css
.viz-root {
  --surface-1:      #17140c;   /* chart/page surface, dark (default) */
  --text-primary:   #f3e9d5;   /* cream ink */
  --text-secondary: #c8972e;   /* bronze */
  --series-1:       #c08700;   /* categorical slot 1 (amber) */
  /* …only the roles this chart uses */
}
@media (prefers-color-scheme: light) {
  .viz-root {
    --surface-1:      #fbf4e8;
    --text-primary:   #1a150b;
    --text-secondary: #564523;
    --series-1:       #db9f00;
  }
}
```

## Categorical palette

8 hues, fixed order — slot 1 (amber) is the brand anchor; the remaining 7 were placed to
maximize CVD separation (enumerated every ordering of the other 7 hues around the pinned
amber, kept the one with the best worst-adjacent ΔE — see "Deriving an order" in
`color-formula.md`). Both modes are selected; the dark column is the same eight hue families
stepped for the dark surface, not a separate palette.

| Slot | Hue | Light | Dark |
|------|-----|-------|------|
| 1 | amber (brand primary) | `#db9f00` | `#c08700` |
| 2 | teal | `#00a37c` | `#00a67f` |
| 3 | violet | `#4f40ab` | `#8680e6` |
| 4 | moss | `#2d8810` | `#4a9c36` |
| 5 | rose | `#e177a3` | `#d36394` |
| 6 | copper | `#dd5a27` | `#de602f` |
| 7 | blue | `#2274d1` | `#408ae4` |
| 8 | crimson | `#d33949` | `#dd555d` |

Light-mode worst adjacent CVD ΔE is 48.7 (rose↔moss) — well clear of the ≥12 target. Three
light-mode slots (amber, teal, rose) sit below 3:1 contrast on the light surface (`#fbf4e8`):
the **relief rule** applies — `report.html`'s tables always carry a visible label next to every
colored value, and any Artifact built from this palette must ship a table view too (per the
dataviz accessibility pass), so this is satisfied by construction, not a gap. The dark steps
were chosen for the dark band (OKLCH L ≈ 0.48–0.67, ≥ 3:1 on the dark surface `#17140c`) and
validated as a set — worst adjacent ΔE 41.3 (rose↔moss again), comfortably clear of the target;
all 8 dark slots clear 3:1 contrast outright (no relief needed in dark mode).

The slot **ordering** is the CVD-safety mechanism, not cosmetic (see `color-formula.md` §
Themes). Amber is pinned to slot 1 as the brand anchor; don't reorder without re-running the
validator on the full permutation search.

## Sequential hue

Default single hue: **amber** (the brand primary), light→dark. When a second sequential context
appears at once, it takes the next categorical slot's hue (teal), as its own one-hue ramp.

| step | hex | step | hex |
|---|---|---|---|
| 100 | `#f3e6ce` | 500 | `#b37b00` |
| 200 | `#e8ce99` | 600 | `#895800` |
| 300 | `#dfb459` | 700 | `#5f3a00` |
| 400 | `#d29a00` | | |

Step 100 (`#f3e6ce`) is deliberately close to the brand's cream-ink token — the ramp recedes
toward the honeycomb identity, not toward a generic gray. Step 400 (`#d29a00`) is the
categorical-band-snapped version of the eyeballed brand amber `#F2B617`; the two read as the
same hue, `#F2B617` is simply lighter than the sequential/categorical bands allow (it's reserved
for headings/large accents in `report.html`, not chart marks — see "Chart chrome & ink" below).

## Diverging pair

**blue ↔ crimson** — cool/warm poles, distinct from the sequential hue (amber), so a diverging
chart never gets confused with a magnitude ramp. Neutral midpoint is a warm-tinted gray (light
`#dbd7cf`, dark `#332d22`). Equal step count per arm (reuse the categorical blue/crimson slot
hexes above as the pole tips).

## Status palette (fixed — never themed)

| role | Light | Dark | light-surface contrast | dark-surface contrast |
|---|---|---|---|---|
| good | `#278733` | `#409d48` | 4.18 | 5.37 |
| warning | `#f29520` | `#e78c08` | 2.11 | 7.14 |
| serious | `#d55c13` | `#e06a2a` | 3.58 | 5.49 |
| critical | `#c92f33` | `#d74745` | 4.88 | 4.27 |

Warning sits below 3:1 on the light surface by design (mirrors the dataviz reference's own
warning WARN) — the **icon + label** pairing is the mitigation, a status color never carries
meaning alone. These steps are deliberately distinct from the categorical slots (different
lightness/chroma even where the hue family overlaps, e.g. good vs. moss, critical vs. crimson)
so a status color never impersonates a series.

## Texture fill (the accessibility channel)

Same as the dataviz method: one hand-drawn **"Lines"** fill at 45°/135°, tone-on-tone. Not
implemented in `report.html` (stdlib HTML/CSS has no hand-drawn fill primitive) — reserved for
the Artifact path (SVG pattern), triggered by the accessibility setting/print/`forced-colors`,
never decorative.

## Surfaces (for the validator)

- Dark chart/page surface (default): `#17140c` — the eyeballed brand surface-dark, used as-is
  (no categorical-slot snapping needed — it's a surface, not a mark).
- Dark secondary panel (hex-grid tint, honeycomb texture / card-on-page separation): `#2a2413`
- Dark page plane (behind the chart surface, one step darker): `#0a0702`
- Light chart/page surface: `#fbf4e8`
- Light page plane (one step darker than the chart surface): `#faefda`

`report.html --plain` does not use these — the plain fallback keeps the old neutral gray theme.

## Chart chrome & ink

| Role | Light | Dark |
|---|---|---|
| Chart/page surface | `#fbf4e8` | `#17140c` |
| Page plane | `#faefda` | `#0a0702` |
| Panel / card (honeycomb hex-grid tint) | `#f7f0e2` | `#2a2413` |
| Primary ink | `#1a150b` | `#f3e9d5` (brand cream ink) |
| Secondary ink | `#564523` | `#c8972e` (brand bronze) |
| Muted (axis/labels) | `#756a55` | `#a99a79` (brand muted-tan) |
| Gridline (hairline) | `#e4ddcf` | `#2a2413` |
| Baseline / axis | `#aca493` | `#433c2e` |
| Delta ↑ good (success text) | `#278733` | `#409d48` |
| Border (hairline ring) | `rgba(26,21,11,0.10)` | `rgba(243,233,213,0.12)` |
| Brand accent (headings/links, large-scale only) | `#c8972e` (bronze) | `#f2b617` (amber, eyeballed brand primary — above the categorical/sequential band, reserved for headings/large accents) |

## Filter controls

Same as `dataviz`'s reference — filters are standard UI, not chart components. Not currently
used by `report.html` (a static, single-view report has nothing to filter) or by the retro
Artifact's v1 form mapping; documented here for parity if a future interactive Artifact adds one.

## Typeface & figures

`report.html` stays in the system sans (`-apple-system, BlinkMacSystemFont, "Segoe UI",
sans-serif` — stdlib, no web font). Large standalone numbers (stat tiles, hero figures in an
Artifact) use default proportional figures; reserve `font-variant-numeric: tabular-nums` for
table rows / axis ticks that must align vertically.

## Validation

Both modes, run from this skill's `references/` directory (path to `dataviz`'s script will
differ per install — this is the exact invocation used to validate the table above):

```sh
node <dataviz>/scripts/validate_palette.js \
  "#db9f00,#00a37c,#4f40ab,#2d8810,#e177a3,#dd5a27,#2274d1,#d33949" \
  --mode light --surface "#fbf4e8"

node <dataviz>/scripts/validate_palette.js \
  "#c08700,#00a67f,#8680e6,#4a9c36,#d36394,#de602f,#408ae4,#dd555d" \
  --mode dark --surface "#17140C"
```

Both exit 0 (ALL CHECKS PASS): lightness band, chroma floor, and CVD separation all PASS in both
modes; light-mode contrast is a WARN (relief rule — visible labels / table view, satisfied by
`report.html`'s table-based layout), dark-mode contrast is a clean PASS.
