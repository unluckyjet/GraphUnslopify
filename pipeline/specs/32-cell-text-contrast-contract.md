---
id: 32
slug: cell-text-contrast-contract
status: ready
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
