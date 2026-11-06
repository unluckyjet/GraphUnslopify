# Portable templates and export presets

Use **Templates & export presets** in the figure editor's settings or the paper
workspace's original-definition card. These controls work locally without a model.

Open **Browse figure templates** and filter by use case. The gallery includes
trends, category comparisons, relationships, distributions and parameter grids.
Each card shows a checked synthetic example and describes its calculation choices.
Choosing a design starts the same field-mapping and review flow as an uploaded
template. The preview is an example. Map your columns and review the proposed
labels, units and calculations before applying to your figure.

Save a named template to download a versioned `.gu-template.json` file. It contains
canonical chart intent, including calculations, units, authored wording and any
claims. It excludes the dataset binding, palette path and output filename. Share
or keep that file like any other design resource; review its wording and numerical
thresholds for the next dataset.

Open a saved file to review it against the current figure. Map each source column
to an available column in the selected data, then choose **Review template** again.
Repeated references to a column move together. Derived axes and wide-data output
columns stay derived; remapping wide input columns keeps their series references
attached. Current claims are preserved unless you explicitly choose to replace
them with the template's claims. No computed data or verification result is transferred; authored wording and numerical thresholds still need review.

Inspect the changed settings and findings, confirm the review, then apply. The
figure editor uses its normal undo and strict render. In a paper, Apply edits an
unsaved original-definition draft: save it explicitly, then audit. Shared source
aliases are identified. Manifest overrides and shared/selected presentation
settings still take precedence when the paper runs. Authored Python and source-free
PDF evidence use their existing review controls rather than canonical imports.

| Export preset | Intent |
| --- | --- |
| Paper · single column | Single-column paper layout, 600 DPI, PNG/SVG/PDF |
| Paper · double column | Double-column paper layout, 600 DPI, PNG/SVG/PDF |
| Review copy · PNG | Single-column 144 DPI PNG; interactive/TeX exports disabled |

Presets also require review. They preserve data fields, calculations and claims,
plus the active dataset, palette and output name. Check your venue's requirements;
these are useful starting choices, not a journal-compliance certificate. Failed
scientific checks still fail after applying a preset. Only the current run supplies
its downloadable outputs.

Cancel a pending review, close the panel or change its inputs to invalidate it.
Older replies cannot replace a newer proposal. A local template must be no larger
than 1 MiB and must pass canonical validation. Unknown settings and embedded data
or palette bindings are refused.

Implementation: `figure_templates.py`, `src/template-fields.ts`, and the shared
`web/reuse-intent.js` component. `npm run intent-check` exercises actual downloads,
cross-dataset mapping, review/undo, strict results and paper source ownership.
Regenerate the packaged catalog and sample thumbnails with
`PYTHONPATH=python python scripts/build-template-gallery.py` from the repository
root using the verification Python environment.
`PYTHONPATH=python python scripts/check-template-replay.py --out /tmp/template-replay`
requires a new output directory and exercises all 21 kinds against the frozen
runtime corpus, retaining original round-trip code identity and real remapped CSV
execution. Other formats retain their native bindings. This is a conformance check,
not a productivity or scientific-superiority benchmark.
