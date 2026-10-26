---
id: 32
slug: cell-text-contrast-contract
status: done
priority: P0
title: Choose and inspect cell annotation text against actual rendered backgrounds
source_idea: visual review of identifier matrix exposes low-contrast heatmap text despite strict passed
---

# Cell text contrast contract

Measured during spec31 review: a sequential heatmap with cells [[1,2],[3,4]] and annotations
returns strict passed, but its actual text/background contrast ratios are1.2407296,3.1383521,
2.5543478,1.2611451. Low cells get dark text on dark viridis; high cells get white on bright
viridis. Source picks by a raw-value midpoint rather than actual cell color. Confusion matrices
also choose white above a raw-value threshold; inspect their actual palette behavior independently.
The current inspector checks mark/series color separation, not these text/background pairs.

Use actual normalized colormap RGBA and effective backgrounds when choosing readable annotation
colors; retain values, cell geometry, axis/colorbar scales, labels and normalization semantics.
Handle sequential/diverging maps, negative/constant values, missing cells and supported alpha.
Inspect supported rendered text/cell pairs and report genuinely unreadable annotations rather
than certifying clean inspection. Do not fix failures by suppressing annotations or the checker.
Review supported HTML output against the same values and readable annotation contract.

Acceptance requires independent luminance/contrast references, actual artist/background checks,
true/false inspector controls, relevant per-normalization cases and exported visibility. Establish
and cite the applicable contrast criterion; numerical threshold compliance alone is not proof of
all visual accessibility. Refresh affected illustrations only after reviewing actual results.
Run the required seven gates, strict gallery and relevant browser/fresh-wheel checks; update
Obsidian and inspect both GitHub workflows. The full scientific reference matrix24 remains open.

## Verified implementation

Cell labels now choose pure black/white from actual normalized RGBA, with effective alpha/
background and image-order inspection. Unknown outlined text is explicit incomplete evidence.
All-zero diverging normalization retains a neutral centre. The shared canonical Python helper
is embedded in standalone generated programs and guarded against stale build assets. HTML
uses explicit per-cell colours from its own colour scale and category serial positions.

Independent initial controls failed17/25 before the fix. There are now34 passing artist/math/
normalization/alpha/raster/inspector/runtime/provenance controls; full local gates pass215 Node/
449 Python, zero skips,15 baselines,16 renders,25 recipes/seven compositions. Strict gallery15/15
and Ruff pass. Real offline Chromium checks522 labels over five cases: sequential/diverging
sweep minima4.6006883/4.5920818, replacing75 failures in the original256-colour HTML sweep.
The installed offline wheel checks actual cell artists and a deliberately unreadable annotation.

Only baseline12 changes (26358 pixels, same dimensions); the other14 PNGs are identical.
Published heatmap/confusion inputs are now committed synthetic fixtures with data/source hash
regressions, and their actual images plus HTML were visually reviewed. See docs/cell-contrast.md
for the W3C criterion and explicit limits. Full scientific matrix24 remains open.
