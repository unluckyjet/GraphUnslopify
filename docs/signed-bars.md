# Signed bars and visible value extents

A zero baseline includes zero and the data on either side. Automatic linear/symlog
bar ranges preserve positive, negative and mixed magnitudes in either orientation.
The negative values-30/-20/-10.5 previously appeared as equal bars clipped near0;
that export incorrectly passed strict inspection. Automatic bounds now retain the
full signed range. Value labels sit outward from either endpoint and respect
percentage display, while raw summaries and actual bar values stay unchanged.

Inspection identifies standard Matplotlib bars from `BarContainer.orientation`,
not rectangle aspect or sign. It checks transformed value extents against the axes,
reporting `bar_mark_clipped` when clipping hides a value or origin. Explicit limits
can therefore fail strict mode even if they include zero. Review files are retained.
The existing `truncated_bar_axis` check also catches either side excluding zero.

Floating bars may start away from zero; their full extents still need to be visible.
A common nonzero floating origin is also permitted. Unrelated rectangles are not
inferred to be bars, and artists with axes clipping disabled are not reported as
clipped by that axes boundary. Standard bar interval stems are also checked against
the value-axis boundary, reporting `bar_interval_clipped` even when the body is fully
visible. This does not certify every custom clip path, cap size, raster image or
arbitrary authored transformation.
A logarithmic bar cannot show its zero origin; use a non-length-bearing mark when
its full bar extent cannot be shown.

`python/tests/test_signed_bars.py` has44 independent artist/geometry/inspector/
export controls: signed/fractional/zero/grouped values, both orientations, excluded
baselines, clipped endpoints, floating origins, non-bar rectangles, percentage
labels and strict positive/negative exports. The initial37 controls measured26
failures/11 passes before the fix. Installed offline wheel checks independently
verify actual signed magnitudes/ranges/labels and a failing clipped-limit export.
The broader21-kind scientific reference matrix remains separate.

## Shared automatic ranges (source after0.8.0)

The zero-baseline adjustment preserves automatic scaling. Later shared panels
can extend the value range to include their actual bars and interval endpoints.
Previously, a first panel with maximum2 froze shared limits at2.1 and clipped a
later maximum4. The same specification and CSV now produce shared limits0..4.2.
Explicit authored limits still take effect and fail strict verification if they
hide a bar or interval. Independent panels retain their independent ranges.

Seventeen actual-render controls cover supported vertical repeats, vertical and
horizontal facets, signed values, intervals, stacks and deliberate clipping.
Horizontal repeats remain unsupported. See the
[measured before/after evidence](workspace/shared-bar-range.md).

## Preserve actual interval endpoints

Bar errorbars require their interval to enclose the estimate. A mean of20 with
quartile bounds0/0 from values0/0/0/0/100 previously drew0..40 by reflecting one
endpoint. It now raises a clear data-dependent error: select median+IQR when that
is the intended summary, or a forest plot/table that can show detached bounds.
The requested estimator is never substituted. Signed widths allow only16 machine
epsilons of relative rounding tolerance, with no absolute-unit tolerance; unknown
bounds remain unknown. Valid asymmetric intervals retain their actual endpoints.

`stacked_uncertainty_unsupported` refuses stacked bars with requested uncertainty:
the old branch omitted intervals entirely. Grouped bars can display individual
intervals; total-stack uncertainty would require an explicit dependence contract.
Stacked bars without requested uncertainty remain supported.

`python/tests/test_bar_intervals.py` adds41 independent controls: both orientations,
positive/negative/rescaled detached bounds, actual bootstrap endpoints1..9,
rounding, unavailable singleton SEM, complete/clipped stems on both sides, semantic
and direct stacked refusal, and real strict positive/runtime/policy exports. Initial37
controls measured26 failures/11 passes before the fix; four additional positive/inverted/
clip-disabled controls cover retained behavior. A crop of1..9 into0..5 now retains review artifacts and exits2
with failed status; detached intervals exit1 rather than publish false bounds.
