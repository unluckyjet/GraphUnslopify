# Display names without renaming observations

Current source after0.8.0 can display a clearer name for a source series. For
example, a CSV can keep its `base` and `ours` IDs while the figure shows Control
and Treatment. Add this to an existing specification:

```json
{
  "legend": {
    "labels": [
      {"series": "base", "text": "Control"},
      {"series": "ours", "text": "Treatment"}
    ]
  }
}
```

This example is a specification fragment. Use **Advanced JSON specification** or
the [direct text editor](workspace/direct-text-editing.md) to review and apply
the visible names. Derived metric/panel aliases are also supported in the current source editor; see
the [workspace initiative](../pipeline/visual-workspace-roadmap.md).
The public PyPI0.8.0 wheel does not include these source additions.

Source IDs, input bytes, grouping, quantities and claim subjects remain unchanged.
A claim about `ours` is still checked against those original observations.
Display names apply to boxed legends, direct series labels and sparkline group
headings; computed details such as calibration ECE stay attached to the source
series. Artist style/colour checks retain original identity, including IDs that
begin with an underscore. Named-series order and sparse-panel styles are retained.

The spec and export provenance retain the explicit mappings. Accessible text
also explains each display name's source ID. PNG/SVG/PDF show literal text;
supported interactive HTML exports use escaped display names and keep the
original ID in each data trace's `meta.source_series`. Display wording is authored
text, not a verified experimental interpretation or a new statistical claim.

## Review failures

Unknown source IDs in the prepared data, repeated overrides for one ID, blank
names, and indistinguishable display names fail explicitly. A name must not
collide with another visible legend entry, including a reference layer. Ordinary
reference entries are not guessed to be data series merely because their text
matches an ID. Array records keep source values such as `__proto__` literal.

Longer text can still produce a real layout finding. The renderer keeps the
authored wording and the strict verifier's failed/incomplete result. It does not
hide data, shrink fonts below the checked size or silently accept a collision.
Nested sparkline grids reserve heading space separately from their parent facet
or repeated-metric heading. Further layout refinements remain in the roadmap.

## Renderer and editor contract

The renderer marks actual source artists when they are created. Legend discovery
uses those identities, rather than interpreting label text; an unowned reference
stays distinct. Geometry targets identify the original series and a canonical
`legend.labels[index].text` path. For an ID without an override, the index is a
prospective append slot: a consumer must append a complete `{series, text}`
record, recheck the current source ID and obey the existing revision fence. It
must not overwrite another series merely because an older map used that index.

Reproduce the independent actual-artist, strict-failure, provenance and HTML-data
controls with `python -m pytest python/tests/test_legend_labels.py
python/tests/test_shared_series.py python/tests/test_preview_geometry.py
python/tests/test_inspect.py -q` from a source installation. Real browser checks
also render the names, reject ambiguous edits and recover to current exports:
`PYTHON=python npm run preview-check`.


The current-source [direct text editor](workspace/direct-text-editing.md) can create these records by clicking a series name and reviewing the change. The current source editor also supports canonical derived metric/panel aliases.


Current-source [measured outside legends](workspace/outside-legend-layout.md) wrap
complete names/titles and choose fitting native columns while retaining source
identities and panel-specific statistics. Unbreakable wording and constrained
layouts can still fail strict verification. Sparkline child-heading and table
context refinements remain separate roadmap work.
