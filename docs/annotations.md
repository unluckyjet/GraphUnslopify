# Faithful annotation anchors

**Development source after 0.8.0.** Install the source checkout and regenerate
scripts. The immutable PyPI 0.8.0 release has earlier annotation behavior.

Annotations now use the primary marks that were drawn, before optional layers
and insets, rather than independently searching raw input rows. For example, if
raw scores include 100 but the displayed mean curve peaks at 70, `at: "max"`
attaches to the displayed 70. Smoothing uses the primary smoothed curve rather
than the faint raw trace. Authored text remains **unverified**: resolving an arrow
does not establish that “significant,” “best,” or a causal explanation is true.

```json
"annotate": [{"at": "max", "series": "new", "text": "Displayed peak"}]
```

Omit `series` when there is no group. A named series requires a declared group;
grouped annotations require an explicit series. Original identities are retained,
including labels that resemble Matplotlib's internal names.

## Selection and chart quantities

| Mark | Quantity used for maximum/minimum and physical anchor |
| --- | --- |
| Line | Actual primary curve vertices, including aggregation and smoothing. |
| Scatter, raincloud, scaling observations | Finite drawn observation centers. Scaling annotations still require `show_points: true`. |
| Bar | Signed displayed bar value, at the actual group offset and endpoint. A stacked segment's value differs from its cumulative endpoint. |
| Forest, dumbbell | Estimate/endpoint marker, using the actual horizontal coordinate and category row. |
| Paired difference, Q-Q, calibration | Drawn matched differences, quantiles, or binned rates; raw scores are not substituted. Paired maxima refer to individual difference points rather than the mean marker. |
| Heatmap, confusion matrix | Actual cell value, including requested normalization. |
| Box, violin, ridgeline | Drawn distribution marks/boundary vertices. These are not an inferred mean or a newly computed density mode. Ridgeline magnitudes use its horizontal measurement axis. |
| ECDF, survival | Drawn curve coordinates; exact repeated step coordinates resolve to the final/right-continuous value. |
| Waterfall | Signed contribution and its running endpoint; the final total uses the displayed total bar. |
| Sparkline grid | Primary curve in the explicitly selected series's child axes. |

`first`/`last` follow numeric/date order, or physical category order; an unsorted
line follows its drawn order. A category containing several distinct possible
anchors is unavailable rather than an arbitrary distribution vertex. Maximum and
minimum ties use the first captured primary mark; no unique optimum is asserted.
An object such as `{"x": "max"}` requests the literal category named “max.”

For numeric/date `{"x": ...}` requests, an exact unique observed coordinate is
preferred. A unique nearest point **inside the selected series's observed domain**
is allowed with `annotation_snapped_to_observation`, requested/resolved evidence,
and `snapped: true`. Equidistant points, conflicting duplicate coordinates,
missing categories/series, and out-of-domain requests are unavailable. This does
not interpolate or extrapolate a new observation.

`crossover` means the first aligned observed point where the selected series
leads all other drawn series, following an earlier non-leading point. It requires
complete aligned coverage and an unambiguous value for every series/coordinate.
An always-leading series has no observed crossover. It does not locate the exact
intersection between observations or establish statistical significance.

## Evidence and strict behavior

Every generated report contains `annotations`. Attempts record panel, metric,
region, original request, authored text, `text_verified: false`, status/reason,
and available physical `x`/`y`, logical key, displayed value and basis. Dates also
include an ISO timestamp. The version1 report schema accepts this optional field
so earlier reports remain readable.

A point outside the final axes view or a logarithm's positive domain is not drawn.
Unresolved required requests add `annotation_unavailable` and untested evidence
(Q-Q retains `qq_annotation_unavailable`). Default strict execution exits2 with
an incomplete report; a separate failed check takes precedence. A visible copy
in one intentional axis-break region satisfies that panel's request. Every facet
must satisfy its own requests. `--fail-on-warning` also rejects disclosed snapping.

This checks generated primary mark coordinates and axes bounds, not arbitrary
user-edited artists, custom clipping, arbitrary overlay targets, text semantics,
or all possible optional combinations. Readability/contrast checks still apply;
correct anchoring alone does not guarantee a passing inspection. Matrix labels
use a light text background for contrast.

Implementation: `src/codegen/annotations.ts`, `draw.ts`, `decorate.ts`, `runtime.ts`.
Measured actual artists and strict CLI cases: `python/tests/test_annotations.py`.
The underlying distinction between target and label position is documented in
[Matplotlib's annotation API](https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.annotate.html);
[line coordinates](https://matplotlib.org/stable/api/_as_gen/matplotlib.lines.Line2D.html)
come from the drawn artist, rather than a second statistical estimate.
