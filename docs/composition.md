# Composition contracts

Facets split rows; repeat switches numeric metrics. They are separate operators.

```json
{"facet":{"by":"dataset","rows":"split","columns":3}}
```

A two-key grid places `by` levels across columns and `rows` levels down rows,
in their encountered order. `columns` is the maximum supported column count;
if the data need more, the program explains how to increase it. Empty combinations
retain their location, display “No data” and make strict verification incomplete.
Counts and uncertainty keep both keys separate. Missing plotting keys are disclosed.

`repeat.share_x` and `repeat.share_y` control actual shared Matplotlib axes.
Repeat accepts distinct numeric y metrics on supported vertical value axes.
Derived-axis kinds, matrix kinds, nested grids, and swapped value orientations
are rejected where their metric semantics are not implemented.

Wide data can establish its own series:

```json
{"y":{"field":"value","label":"Score"},
 "series_from_columns":{"fields":["baseline","ours"],"series_name":"model","value_name":"value"}}
```

Leave `group` unset. Raw filters run before reshaping; layers use prepared columns.
`data.columns` describes raw input, while axis/metric/overlay references are checked
against the columns available after reshaping. Output names must be distinct and
must not overwrite retained input columns. Embedded specs retain the original
reshape declaration and can be translated again.

Tables support summaries, intervals, highlighting and static/Markdown/LaTeX
outputs. Panel/overlay/cut/animation/interactive table options are rejected.
Only standalone y breaks are implemented; x breaks and combinations of breaks
with panels/overlays are rejected. A cut requires `from < to` and cannot also
set explicit limits on the cut axis. Bands need an upper column; rules need a
value. These errors prevent accepted options from silently changing meaning.

## Overlay coordinates

Layers draw **raw prepared rows**, after their own filters; they do not silently
aggregate to match a base summary. Continuous x retains its actual coordinates.
On vertical bar, box, violin, raincloud and slope charts, line/scatter/rug/band
layers use the base panel's actual category positions. Custom or encountered order,
lexical names such as `01` and `1`, and facet-specific levels are preserved. Rows
are stably ordered by those plotted positions. Grouped-bar overlays sit at the
category centre; they do not inherit individual series' offsets. Use explicit
filters/columns when a reference should represent one series.

With shared categorical x axes, the generated workflow establishes one order
from the complete prepared data before drawing panels. Missing local levels keep
their shared positions. Unshared panels retain their own order. The mapping reads
the base formatter even when shared axes hide a panel's tick labels.

An unknown category or ambiguous base labels fail instead of inventing a second
categorical axis or discarding rows. User columns and row/value associations are
preserved. Rules are horizontal numeric-y constants and need no raw x column;
Q–Q and waterfall permit these rules while rejecting raw-x layers. Derived-y
ECDF/calibration/survival plots need an explicit overlay y column for a line,
scatter or band; the figure's derived output name is not an input measurement.

Raw overlays on horizontal bars, forest, ridgeline, dumbbell, paired-difference,
matrix and sparkline-grid coordinate systems are explicitly unsupported. Table
overlays remain unsupported too. A semantic `unsupported_layer_coordinates` error
explains the boundary, and directly running a refused layer also raises. These
restrictions avoid plausible marks at unrelated coordinates; they do not claim
every composition or scientific assumption has been validated.

Independent actual-artist tests cover category/value associations, filtered rugs,
band bounds, grouping/facets, unknown/ambiguous labels, derived-axis refusals,
horizontal rules and unchanged continuous coordinates. An actual strict PNG/SVG
render and the fresh offline wheel test exercise the same contract outside unit
translation. Parent scientific reference matrix24 remains open.

## Shared categorical panels

Shared axes use one category mapping across all participating panels, including
categories missing from an individual panel. This covers vertical/horizontal bar,
box, violin, raincloud, ridgeline, forest, slope and dumbbell presentations, with
or without overlays. Sharing follows the **physical** category axis: horizontal
bars, forest, ridgeline and dumbbell share category positions through `share_y`;
the other listed kinds use `share_x`. An unshared category axis retains its local
encountered or declared order. Explicit shared orders can reserve empty positions.

Missing categories stay empty; they acquire no invented estimate or density.
Box/violin/raincloud draw only groups with observations, retaining their global
positions and category colours. Supported repeated metrics use the same mapping;
re-running their generated module resets the original metric before sorting.
Swapped-axis repeat layouts retain the existing `unsupported_repeat` refusal.
Waterfall totals and paired-difference conditions have specialized coordinates;
this contract does not reinterpret them as raw category slots.

The regression probe has B=30/01=10 in one panel and1=20/01=11 in another.
Previously, final labels1/01 made B's30 appear to belong to1. Current marks use
B/01/1 consistently and leave missing positions blank.51 actual-workflow controls
cover nine presentations, sharing/order options, repeated metrics, sparse density
groups/colours and repeat-run state. The installed offline wheel independently
checks real marks and common labels. This is category identity evidence; the full
per-kind numerical/domain matrix remains separate. Independent numeric ranges
can still trigger the inspector's existing panel-comparability findings.
