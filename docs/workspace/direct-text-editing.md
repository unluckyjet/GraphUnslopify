# Edit wording on the figure

Available from the current source checkout. Published PyPI0.8.0 predates this workspace feature.

1. Choose your data and render a figure.
2. Select **Edit figure text**, then click a highlighted title, axis label, series name, annotation, reference-line label, layer legend entry or legend title. Keyboard users can tab to the same targets; the **Figure text** selector also lists them.
3. Enter the wording and select **Review change**. Compare the old and proposed text and review its scientific meaning. The figure and specification have not changed yet.
4. Confirm the review and select **Apply and verify**. The editor updates the specification and reruns the original strict checks, even with live preview turned off.
5. Use **Undo change** to restore the previous applied text/settings, then render again if live preview is off. The open page retains up to20 changes.

The wording field contains the authored label. The **Currently shown** line includes renderer-owned details such as units. Editing `Accuracy` does not remove or duplicate its `(%)` suffix. Renaming a series changes its display-name record; source IDs, data, claim subjects, numerical checks and computed calibration details remain attached to their original source. Shared labels/annotations change wherever the same intent appears.

The exported specification, report and standalone Python reproduce the applied wording. Draft/review text is not applied to exports. A misleading or ambiguous series name can still fail strict verification; use undo or correct it. Numerical checks do not establish the truth of authored wording.

Targets come from text measured during the actual final cropped PNG draw, bound to its hash and current render. Mobile resizing uses the displayed image's actual dimensions. Data changes, specification edits and new checks discard old targets and pending reviews. Geometry unavailable, hidden text and unsupported computed labels remain uneditable; this does not convert an unknown verification result into a pass.

Repeated-metric labels and facet/panel heading aliases remain a further checkpoint of roadmap81. Model drafts, spatial findings, worker/cache improvements and the remaining workspace roadmap are also unfinished.

Implementation: `web/text-editing.js`, `web/app.js`, the packaged preview asset route, and the [geometry contract](geometry.md). [Series display names](../legend-labels.md) documents the canonical alias records. `scripts/preview-check.ts` checks the real click/review/apply/undo workflow and exported Matplotlib artists.

Reference/layer labels update their existing `reference_lines[index].label` or
`layers[index].label`; numerical reference values, filters, marks and observations
stay unchanged. A layer has its own identity even when its original name matches
a source series. Duplicate visible names fail strictly. The inspector still
compares actual colours and catches deliberately changed source or layer colours
across panels. Renderer-default legends can receive display-name records without
materializing unrelated settings. Unknown geometry versions disable text editing
while retaining the original scientific result.
