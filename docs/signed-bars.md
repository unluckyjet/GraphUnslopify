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
clipped by that axes boundary. This is a check of standard bar bodies, not every
custom clip path, error-bar cap, raster image or arbitrary authored transformation.
A logarithmic bar cannot show its zero origin; use a non-length-bearing mark when
its full bar extent cannot be shown.

`python/tests/test_signed_bars.py` has44 independent artist/geometry/inspector/
export controls: signed/fractional/zero/grouped values, both orientations, excluded
baselines, clipped endpoints, floating origins, non-bar rectangles, percentage
labels and strict positive/negative exports. The initial37 controls measured26
failures/11 passes before the fix. Installed offline wheel checks independently
verify actual signed magnitudes/ranges/labels and a failing clipped-limit export.
The broader21-kind scientific reference matrix remains separate.
