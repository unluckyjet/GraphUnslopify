# Actual diagnostic geometry: backend checkpoint 83c

The local preview response now includes `diagnostic_map`, binding measured
locations to entries in the actual runtime `report.findings`. This checkpoint
provides the backend contract; [clickable diagnostic controls](clickable-diagnostics.md)
use it in checkpoint83d.

## Ownership and meaning

Inspector checks record private, non-owning source locators for small text,
tick/text collisions, legend occlusion, clipped bar bodies and clipped interval
stems. Public finding dataclass fields and scientific acceptance remain intact.
Process-local IDs stay inside the renderer and do not retain closed figures.

The PNG observer captures those primitives during the last actual tight-cropped
draw, at export DPI. The later inspector uses actual export widths. Its findings
resolve against that earlier snapshot; coordinates are pixels from the final
PNG's top-left corner. Interval boxes include the measured stroke width and
visible axes clipping. Text targets measure text rather than annotation arrows.

The parent checks the actual PNG bytes, dimensions and name, supported metadata
version, finite in-image bounds and a unique match to an actual finding. It
binds `run_id`/`spec_hash` and refuses stale generations. Unknown checks, custom
clip paths and invisible/uncaptured sources remain explicitly unlocated.
Capture capacity is 8192 sources, with an explicit truncation flag; the metadata
validator bounds total supplied regions to 16384.

`available: true` describes location metadata. Scientific status comes from the
runtime report. The [actual synthetic API example](diagnostic-geometry/source-preview-example.json)
locates a clipped 1..9 interval in a 0..5 view while retaining strict failed
status/exit 2. Existing text-edit geometry remains available.

## Response shape

`diagnostic_map` has `schema_version: 1`, `coordinates: "pixels_top_left"`,
the final `image` name/width/height/SHA256, current `run_id`/`spec_hash`, `targets`
and `unlocated`. Each target references a real `finding_index`, a primitive
`kind` and `[left, top, width, height]` bounds. Unlocated entries reference their
finding index and explain the missing location. Unavailable metadata supplies
an error and no targets; the actual scientific findings remain in the report.

## Verification scope

`python/tests/test_preview_diagnostics.py` contains 34 focused controls: actual
font/collision/legend/bar/interval sources, three export DPIs, inverted/native
orientations, independent red-stem pixel checks, original PNG pixel and finding
preservation, public serialization, figure collection, metadata/version/hash/
bounds/identity refusal, unknown/custom-clipped sources, capture failure,
capacity, missing files and actual preview-process generation/status binding.
Current/minimum Python and fresh offline installed runs pass all 34 cases.
All seven gates pass on stable source/test files: 234 Node/1637 Python, zero
skips/one existing upstream MLflow/SQLAlchemy warning. Source/fresh browsers
each pass 66 workflows across 21 kinds, zero errors/external browser requests;
18 installed assets match. Gallery passes 15/15 and all 75 tracked PNG files
are byte-identical. The translator rebuild has no bundle difference. See
[verification](diagnostic-geometry/verification.json). Existing 106 inspection/editor
controls also pass; the exact new-commit CI gate follows publication.

Sources: `inspect.py`, `preview_diagnostics.py`, `preview_geometry.py`,
`preview_render.py` and `preview.py` in `python/graphunslopify/`. The observer is
restored in `finally`, and optional geometry failure leaves scientific inspection
and text geometry in place. It adds no automatic scientific repair or data edit.

Preceding 34dd28d exact main 41068733016 all nine jobs and Figure 41068733020
passed before implementation. Full 83 overlay interaction/owned layout and
84–89 remain open. This is source work after the published 0.8.0 release.
