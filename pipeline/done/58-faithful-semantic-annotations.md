---
id: 58
slug: faithful-semantic-annotations
status: done
priority: P0
title: Resolve requested annotations against the actual drawn data and disclose unavailable anchors
source_idea: review item4 misleading annotations; actual atx100 on x1..3 silently attaches to3 and passes strict
---

# Faithful annotation anchors

Source review also finds mean-line semantic maxima are located in raw rows rather
than the drawn summary, and absent annotations generally only log a message.
Finish this part of review item4 after visibility milestone55, before claiming
item4 complete. Do not attempt to certify arbitrary authored prose as scientific truth.

1. Anchor supported marks to the actual displayed summary/coordinates, including categorical
ordering/orientation and supported derived estimates; explicitly refuse undefined coordinate
contracts instead of drawing a different quantity.
2. Expose requested/resolved anchor and text-verification scope in machine evidence; unavailable
series/x/crossover and off-view requested anchors must not silently pass strict. Exact requested
x and nearest-observation behavior must be honest about the actual location and observed domain.
3. Actual artist and full strict CLI controls prove mean/median versus outliers, missing/reordered
cohorts, temporal/categorical axes, clipped anchors and valid controls. Inspect any changed
published graphics; regenerate baseline/source/bundle/provenance and document actual pixel changes.
4. Run seven gates/gallery/lint, commit/push this separately and verify exact CI. Only then mark
review item4 delivered with stated source/visual-scope limits.


## Delivery evidence

Primary drawn geometry now owns anchor resolution; unavailable, ambiguous, off-view
and absent-series requests remain untested and default strict exits2. Reports expose
requested/resolved values, per-panel/region scope and unverified authored text.
Thirty new actual-artist/strict-CLI controls cover raw outliers versus mean/median,
smoothing, numeric/date/category/hidden-label targets, grouped/stacked bars,
normalized cells, matched differences, forest estimates, waterfall endpoints,
sparklines, snapping/ambiguity and intentional axis-break regions. Static validation
also refuses a named annotation series without a group.

Seven local gates pass:222 Node/1124 Python (zero local skips/warnings),15 matching
baselines,16 renders,25 recipes and7 composition cases. Ruff64 and strict gallery15
pass. Source bundle,15 baseline scripts and seven owned reference fingerprints
are refreshed.58of60 prior PNG pixels/dimensions remain identical;09 and15 change
intentionally and were visually inspected.09 moves raw(30,82.006) to the displayed
mean(28,81.091).15 moves raw2025-08-07/39.5 to the centered rolling minimum
2025-08-05/40.913; its false lag/causal wording is replaced with a centered-window
explanation.09 dimensions remain4322x2400;15 changes4098x2466 to4147x2466.

Fresh final source-wheel installation passes agent/PDF/offline runtime controls.
Four extra actual installed offline probes verify the mean70 anchor, outside-domain
and clipped strict rejection, and disclosed nearest-point snapping. No PyPI upload
or version/tag mutation is made; these are source additions after immutable0.8.0.
Exact pushed general/Figure CI is checked before advancing. This completes the
scoped source implementation of review4 with milestone55; arbitrary authored prose,
custom clipping/edited artists and exhaustive optional combinations are not certified.
