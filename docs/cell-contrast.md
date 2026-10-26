# Cell annotation contrast

Annotated heatmaps and confusion matrices choose pure black or white against each
cell's actual normalized colormap colour. A raw data midpoint is not a luminance
midpoint: the previous sequential heatmap `[[1,2],[3,4]]` produced text/background
ratios of 1.2407, 3.1384, 2.5543 and 1.2611 despite passing strict inspection.
Changing the annotation colour preserves the plotted quantities, cell positions,
precision, labels and aggregation. An all-zero diverging grid now retains a
symmetric nonzero colour domain so zero maps to the neutral centre.

## Criterion and scope

The internal criterion for these small annotations is an **unrounded contrast
ratio of at least 4.5:1**, using sRGB relative luminance. This follows the normal
text threshold and declared-colour method in the
[W3C contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
Antialiased glyph edges are not the colours used in this calculation. Passing
this check does not certify the whole figure's accessibility, font size, layout,
statistical validity or publication readiness.

For opaque backgrounds, choosing whichever of pure black and white has greater
contrast gives a minimum possible ratio of `sqrt(21)`, about 4.5826. Choosing a
dark gray instead of pure black loses that guarantee. Transparency is composited
before evaluating contrast; a transparent figure canvas is assessed on white
paper. A dark viewer background can therefore require another assessment.

The inspector reports `cell_text_low_contrast` errors for supported image/text
pairs. It accounts for normalized scalar or RGB(A) cell colours, masks, scalar
and array alpha, axes/figure backgrounds, image origin/extent, text transforms,
text alpha, filled text boxes and image drawing order. An image that completely
covers an annotation cannot pass by hiding its letters. Outlined text is explicitly
`cell_text_contrast_untested`; generated annotated-cell programs treat that as
incomplete required evidence. Plain figures without images do not acquire cell
findings. Arbitrary photographs, interpolated texture details, non-image marks,
custom text effects and contrast across an entire glyph footprint need further
assessment; this cell-anchor model is not a general visual scene analyser.

## Shared implementation and HTML

`python/graphunslopify/cell_colour.py` is the canonical implementation. The build
embeds it into the TypeScript emitter so standalone plotting scripts need no
GraphUnslopify package import to choose readable colours. Installed inspection
uses the same module. `npm run build:translator` refreshes both the embedded
source and the wheel's translator; CI rejects stale generated assets.

HTML uses the actual Plotly colour scale to choose each annotation's colour.
Plotly's automatic colours failed the criterion for 75 of 256 viridis samples,
with a worst ratio of 3.1269. Explicit annotations preserve hover values and use
categorical axes plus numeric category positions: this avoids merging names
such as `01` and `1` or placing their annotations on top of one another.

## Evidence

`python/tests/test_cell_contrast.py` has independent luminance references, actual
artist/value checks, confusion normalization and zero cases, positive/negative
inspector controls, raster alpha probes, provenance and standalone execution
without the optional inspector. The initial suite exposed 17 failures; the
completed suite has 34 passing cases.

`PYTHON=python npm run cell-contrast-check` opens real self-contained HTML with
external connections blocked. It reads the displayed text colours and the actual
heatmap PNG pixels, verifies category identity and cell placement, and checks
522 labels across five cases. Measured minimum ratios are 4.6007 for the sequential
sweep and 4.5921 for the diverging sweep. CI retains screenshots and JSON evidence.
The fresh-wheel smoke also checks real cell artists and a deliberately unreadable
annotation outside the checkout, with external runtime connections blocked.

Only gallery example 12 changes; the other 14 baseline PNGs retain identical
pixels. Public heatmap/confusion illustrations have committed synthetic inputs
in `examples/references/`, with source/data fingerprint regressions. These
contrast checks do not complete the broader 21-kind scientific reference matrix.
