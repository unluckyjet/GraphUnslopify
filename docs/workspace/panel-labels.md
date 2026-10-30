# Metric and facet display labels

Current source supports editing repeated metric labels and facet headings directly on the PNG preview. Select **Edit figure text**, click the label (or use its keyboard target/selector), review the wording, and **Apply and verify**. A metric's axis and heading share one wording record. Panel letters stay automatic.

The records describe display wording. Original data columns, facet values, report panel names, claim subjects and numerical marks stay unchanged. Accessible text discloses the mapping; exported specifications and standalone Python reproduce it. Authored wording still needs scientific review.

Advanced JSON can express the same records. These are fragments for existing figures:

```json
{"repeat":{"fields":["score","loss"],"labels":[{"field":"score","text":"Quality"},{"field":"loss","text":"Error"}]}}
```

```json
{"facet":{"by":"condition","rows":"phase","labels":[{"value":"A","row":"early","text":"Early control"},{"value":"A","row":"late","text":"Late control"}]}}
```

For a one-dimensional facet, omit `row`. A two-dimensional facet requires it. Values use the renderer's captured source strings. Separate row and column values form the identity; joined headings such as `early / A` and panel order are not keys. The click editor creates complete records without requiring JSON authoring or guesswork about append positions.

Unknown prepared sources, duplicate overrides, blank wording and ambiguous effective display names fail strict rendering. Labels on empty facet cells preserve the original **No data** evidence. Unsupported combinations such as repeated forest metrics remain explicitly rejected; a normal horizontal forest uses the semantic y-label path for its horizontal measurement axis.

Repeated metrics retain their existing unit/scale rules. The base y-label/unit does not automatically describe every repeated column, and changing wording never rescales observations. Data/spec changes invalidate pending edits; undo restores the previous applied intent.

Implementation: `src/schema.ts`, emitter runtime/index/decorate and `web/text-editing.js`. Actual controls are in `python/tests/test_panel_labels.py` and `scripts/preview-check.ts`. See [text editing](direct-text-editing.md) and [geometry](geometry.md). These additions are source-only beyond immutable PyPI0.8.0.
