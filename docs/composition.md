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
