# Renderer-bound text geometry

This is the backend foundation of workspace milestone81, after the verified80
layout. Source display aliases and [click/review/apply/undo controls](direct-text-editing.md)
are available. [Metric/panel aliases](panel-labels.md) use structured original source identities and separate base wording from automatic panel letters.

Generated programs mark text with private semantic metadata when it is created.
Axis paths therefore describe source meaning even when a forest plot draws the
measurement horizontally. Annotation paths retain the original annotation index;
units and source-field identity are separate from authored label text. Repeated
metric axes/headings now share canonical repeat.labels records. Facet targets
retain separate row/column source values; their value metadata contains editable
wording without the renderer-owned letter prefix. Named-series
legend entries use the canonical [display mappings](../legend-labels.md), including
a prospective append path for IDs without an override. Reference-line annotations and layer legend entries now use their own existing
canonical label fields. Renderer-owned identities distinguish them from source
series even when the visible wording happens to match.

The local preview runs its owned generated script through `preview_render.py`.
The adapter observes the final PNG `draw_event` inside the actual save call.
Matplotlib's initial canvas and its later tight-cropped export can have different
origins, DPI and sizes; the last real draw supplies coordinates. Annotation bounds
measure text rather than including the connecting arrow. Hidden/empty targets
are excluded. Capture disconnects its callback and does not redraw or mutate the
figure. Original strict exits and renderer errors remain intact.

The `edit_map` response uses top-left pixel coordinates of the original PNG and
includes its actual dimensions/SHA256, the report's spec hash and the owned run ID.
The server rejects a mismatched PNG hash. Geometry failures remain unavailable
and do not assert a scientific result. The normal report and export allowlist are
unchanged; the geometry sidecar is temporary session state, not source data or
an accepted standalone export. Original generated scripts still run directly.

Consumers must scale against the displayed image itself, invalidate old maps on
edits/data changes, and enforce the same current-revision checks as other results.
An absent target does not prove complete text coverage. An editable label does
not certify the truth of authored wording or experimental independence.

## Reproduce the measured controls

```sh
PYTHONPATH=python python -m pytest python/tests/test_preview_geometry.py -q
```

Fourteen actual controls cover PNG ink at73/144/300 DPI with tight crops, arrow
exclusion, vertical labels, hidden text, callback cleanup, export-error propagation,
missing geometry, failed sidecar writes, real generated previews, swapped forest
axes and original grouped/repeated identities. Before/after capture images are
compared by decoded RGBA bytes. All22 refreshed baseline/reference PNGs were also compared
to8bb1d4a's originals and have identical decoded dimensions and RGBA bytes.

Do not use `ImageChops.difference(rgba_a, rgba_b).getbbox()` alone as a pixel
equality test: Pillow13.0.0's default alpha-only bounding box can returnNone for
different RGB channels with equal alpha. Compare dimensions plus decoded bytes,
or explicitly inspect all channels. The ink probe uses a grayscale mask.


Output names such as graphunslopify, json, inspect and matplotlib must not shadow
Python dependencies. The preview adapter imports from its trusted package root;
standalone scripts exclude their own directory from module lookup before importing
dependencies. Data paths still resolve in the chosen working directory. All four
names are exercised through actual preview and direct strict standalone execution
on Python3.10.22 and3.12.14. An axis's visible flag alone is also insufficient:
axis labels can have axes=None and survive set_axis_off while no text is drawn.
The capture follows artist ownership and the Axes.draw exclusion of Axis children.
An independent blank-PNG control rejects such ghost targets.
