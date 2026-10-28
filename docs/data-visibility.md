# Data selection and visible views

**Current source after 0.8.0.** Install a source checkout and regenerate scripts to
use these checks. Published 0.8.0 has earlier inspection behavior; new generated
programs require the data-view inspection capability rather than silently trusting
an older checker with the same package version string.

## What is measured

Rendered rectilinear line, scatter, line-segment and polygon artists are inspected
using their actual coordinate transforms, physical x/y scales and axes bounds.
`inspection.measurements.data_view` records finite/unavailable coordinates,
nonpositive log coordinates and positions outside each view. These are **artist
coordinates, not source sample sizes**: polygon vertices and repeated segment
endpoints are not independent measurements. Masked/NaN scatter rows do not count
as observed points; line gaps remain missing.

| Condition | Result | Correction |
| --- | --- | --- |
| Finite zero/negative coordinates on a log axis, including supported interval endpoints | `log_domain_hidden` error; default strict exit code 2 | Use linear/symlog, or explicitly filter and disclose the excluded domain. |
| Finite coordinate centers/vertices outside axes bounds with clipping enabled | `data_outside_view` warning | Widen the limits or disclose the zoom and inspect which evidence is excluded. `--fail-on-warning` can require review. |
| Declared source filters | Step-by-step counts and total selection disclosure | Check the population actually selected; legitimate filters are not automatically labelled deceptive. |
| Explicit numeric axis limits | Limits disclosed in alt text and embedded export descriptions | Distinguish statistics of retained data from what fits inside the view. |

A line segment may cross the visible view even with both endpoints outside it;
large markers may also have visible ink beyond their centers. The warning does
not assert that every mark vanished or infer deceptive intent. Log coordinates
are different: zero/negative values cannot faithfully occupy a logarithmic axis.

Inspection keeps original observations and limits unchanged. It does not silently
filter, clamp, replace missing values with zero or stretch the view to hide a
warning. Existing stricter bar-body/interval/baseline checks continue to apply.
The marker-ink density heuristic now counts finite unmasked in-view centers and
their actual sizes; masked/off-view points do not inflate a supposed overlap. It
remains a heuristic rather than a measurement of overlapping pixel area.
The zoom-exaggeration heuristic also checks continuous linear numeric x axes;
calendar origins and categorical formatting do not count as numeric magnitudes.
This remains a review warning rather than a claim of deceptive intent.
Existing shared-panel identity, contrast and collision checks
remain in place.

## Selection evidence

Top-level `spec.filter` tracing in `data.counts.filtering` contains source/retained/removed row totals plus each
predicate's before/after/removed counts. Counts are captured before reshape and
transform, so long-format rows and independent units are separate denominators.
The report already contains the author-supplied spec; the trace adds counts, not
raw dataset rows. Nonzero exclusion totals are appended once to alt text, including
multi-panel figures. A no-op filter does not invent exclusions; filtering every
row preserves counts and fails before producing a figure.

For example, filters selecting one cohort then values below a threshold might
show 4→2→1 rows, with total selected 1 of 4. This is a conditional view, not evidence
that the unselected cohort or a retained outlier never existed. The tool cannot
find rows that were removed before the supplied file was created. Layer-specific
predicates remain recorded in the spec; this trace does not quantify them as new
source populations.

## Scope boundaries

The measurement checks top-level rectilinear artist coordinates against axes
bounds. It does not certify pixels/raster-image content, arbitrary custom clipping
paths, custom transforms, projection geometry or child inset axes. Blended
axes-fraction reference lines are excluded from sample counts. Intentional marked
axis-break halves retain outside-coordinate counts without treating each half as
accidental omission; the existing encoding narrative discloses the cut. Insets
already have a declared zoom narrative.

[Annotation anchors](annotations.md) separately resolve requests against primary
drawn marks and disclose unavailable/ambiguous targets. Neither these visibility
checks nor arrow placement certifies arbitrary authored prose.

Sources: [Matplotlib scale behavior](https://matplotlib.org/stable/api/scale_api.html)
and [explicit view limits/autoscaling](https://matplotlib.org/stable/users/explain/axes/autoscale.html).
Implementation: `python/graphunslopify/data_view.py`, `inspect.py`,
`src/codegen/data.ts`, `src/codegen/runtime.ts`, `src/alttext.ts`.
Measured controls: `python/tests/test_data_view.py` with actual artists, export
provenance and strict CLI exit policies. No visual-intent or scientific-validity
classifier is claimed.
