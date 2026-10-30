---
id: 81
slug: direct-visual-editing
status: done
priority: P1
title: Edit actual rendered text through canonical figure intent
source_idea: User visual-workspace advice and direct chart manipulation requirement
---

# 81 — Direct visual editing

Prerequisite8bb1d4a exact main40915277406 all9/Figure40915277467 pass.
Actual CI browser12915019920 has31 workflows/all21 kinds/0 external requests or
JS errors; downloaded Linux3.10 wheel12916006318 matches7 checked source assets.

Full scope: click actual chart titles, axis labels, legend entries and annotations;
review the proposed text/source meaning; apply to canonical intent, rerender and
export. Preserve data, units, strict checks, local ownership, advanced JSON,
drafts/undo, panel semantics, stale-result fences and source consent.

## Checkpoints

1. Capture actual text positions during the final PNG draw, including tight
   cropping/DPI, and bind the map to the original PNG hash and current render.
   Register semantic paths at the renderer's source, without inferring a label's
   meaning from matching text. Read-only derived labels remain explicit.
2. Complete literal display aliases and source mappings for legend entries and
   derived panel labels. Keep data/claim identity separate from display text.
3. Add keyboard-accessible click targets and a review/apply form on the real
   figure. Canonical updates, rerender, undo and exported reproduction must work.

These are implementation checkpoints, not narrower completion criteria. A
geometry file alone does not deliver direct editing. Model drafts82/spatial
diagnostics83 remain separate full requirements in the workspace roadmap.

## Acceptance evidence required

- Known-position real PNGs at multiple DPI/tight crops, vertical and rotated
  labels, annotations excluding arrows, and hidden/empty artists. Actual encoded
  pixels and image hash, not a diagram with guessed rectangles.
- Actual generated figures and packaged preview API geometry; no plot pixel or
  strict-acceptance changes merely from capture. Missing geometry stays unknown.
- Click/edit/review/apply/undo for all four requested roles; validate special
  axis orientation, units, multiple panels/repeated metrics and original series
  identity. Require explicit review of authored meaning.
- Actual source/fresh-installed browser behavior, strict failures/recovery,
  old-map/new-data refusal, narrow layouts, exported spec/text and extracted
  strict reproduction. All seven gates and exact pushed CI per checkpoint.
- Update canonical Obsidian notes with source/evidence and remaining scope.

## Geometry checkpoint81a verified locally

Actual source/fresh installed preview returns original-PNG-bound target geometry.
Fourteen controls pass on real3.10.22/3.12.14; ownership traversal excludes
axis-off ghost text, semantic paths survive swapped forest axes and derived
labels retain read-only identity. Actual preview and direct strict standalone
execution succeed for graphunslopify/json/inspect/matplotlib output names.

Final seven gates227/1458 pass, zero skips/one existing upstream MLflow warning;
Ruff/format/translator rebuild and strict gallery15 pass. Source/fresh offline
installed Chrome31 workflows/all21 kinds pass,0 external requests/JS errors.
All9 installed sources match, and all22 refreshed PNG decoded RGBA pixels match
8bb1d4a while regenerated provenance matches the current emitter. Actual measured
proof is in docs/workspace/geometry-verification.json and geometry.md.

This is a coherent backend checkpoint to commit/push and verify in exact CI before
the remaining81 work. Canonical display aliases and actual click/review/apply/undo
remain open; neither this spec nor the full workspace goal is complete.


Geometry81a exact d0178e0 main40962707353 all9/Figure40962707278 passed before81b.

## Display-alias checkpoint81b verified locally

Typed source-series/text array records drive visible box/direct/sparkline names
without renaming data, quantities or claim IDs. Renderer-owned artist identity
distinguishes references and preserves ECE details, ordering and style checks.
Underscore IDs and literal text work in PNG/SVG/PDF and supported native HTML;
HTML trace metadata and accessible provenance retain original IDs. Invalid, stale,
blank or ambiguous mappings fail strictly. Nested sparkline facet/repeat headings
reserve a separate row; shared-bar auto-range defect is explicitly retained in
Obsidian for83 rather than hidden by the identity fixture's authored0..5 limits.

114 focused controls pass on actual3.10.22; final3.12.14 full suite1485/Node227 and
all seven gates pass, zero skips/one existing upstream warning. Strict gallery15
and Ruff pass. Source/fresh offline installed Chrome33 workflows/all21 kinds pass,
0 external page requests/JS errors. Actual HTML Chrome shows literal text;10 wheel
assets match source and22 refreshed default PNG RGBA byte identities are retained.
Proof: docs/workspace/legend-labels-verification.json; contract: docs/legend-labels.md.

Commit/push and exact CI precede the next microchange. Derived metric/panel labels
and click/review/apply/undo are still open;81 and the full workspace remain unfinished.


## Actual text interaction checkpoint81c

Prerequisite7ab724f exact main41024904963 all9/Figure41024904907 passed.
Source Chrome40 workflows pass: actual PNG title/axis/series/annotation/legend-title
clicks, review before mutation, explicit meaning confirmation, canonical text
changes, strict rerender with live mode off, original units/claim/source identity,
strict duplicate-name refusal and actual undo/recovery. Keyboard/mobile hit
positions match the scaled image within1px; new data cancels old reviews/targets.
Extracted bundle executes strictly outside checkout and actual Matplotlib artists
retain the applied wording and raw line labels.3 Node intent/security invariants
and25 preview/geometry tests on both3.10.22/3.12.14 pass.

Final seven gates230 Node/1485 Python pass, zero skips/one existing upstream
warning. Ruff/gallery15 pass; final source/fresh offline installed Chrome41
workflows/21 required-kind controls pass,0 external requests/JS errors.12 installed
assets match source. Mobile/rapid viewport correction uses one CSS surface, with
actual title/rotated-axis x/y/width/height within1px; no tolerance weakening.
No published scientific artifacts changed. Proof: docs/workspace/direct-text-verification.json.
57b4652 exact main41029266281 all9/Figure41029266288 passed.
Repeated-metric/facet heading aliases, reference/layer labels with existing
canonical fields, and remaining full81 acceptance coverage stay open. Guide: docs/workspace/direct-text-editing.md.


## Reference/layer checkpoint81d (local verification)

Prerequisite57b4652 exact main41029266281 all9/Figure41029266288 passed. Actual
reference annotation paths and layer legend paths retain numeric anchors/marks/
filters; all five layer kinds have actual measured text. Layer/source IDs have
separate namespaces for legend deduplication and panel-colour checks. A new shared
fixture initially exposed a false colour-drift failure when a layer and a raw
series shared a name; the corrected inspector retains actual colour separation
and detects deliberately mutated source and layer colours across panels.

123 focused controls pass on actual3.10.22/3.12.14; five Node semantic/unsafe-path
controls pass. Source browser45 workflows pass, including actual reference/layer
click/review/apply/strict duplicate-name refusal/undo and strict exported51/50
anchor reproduction. Unknown-version transport mutation disables editing without
changing the actual scientific report. Renderer-default legend editing works
without adding unrelated defaults.22 refreshed PNG decoded RGBA bytes match
57b4652; gallery15/Ruff pass. Final seven gates232/1494 pass,0 skips/1 existing
upstream warning; fresh offline installed browser45 workflows/21 required-kind
controls pass with0 external requests/JS errors.12 installed assets match.
Push/exact CI pending. Proof: docs/workspace/reference-labels-verification.json. Derived metric/facet aliases and remaining full81 coverage stay open.


## Metric/facet checkpoint81e (local; final gates running)

Prerequisite5773d58 exact main41033640343 all9/Figure41033640564 passed, including
actual CI artifact12966984021/45 workflows with verified ZIP digest. Optional
repeat.labels[{field,text}] and facet.labels[{value,row?,text}] preserve raw data/
claim/report IDs. Actual headers and repeated axes carry canonical paths and a
separate base value; the edit form does not copy automatic letters into intent.
Prepared source membership, row shape, duplicate/blank/ambiguous names fail strictly.
Empty cells retain No data/untested evidence, and unsupported forest-repeat
combinations retain the original explicit rejection. Native horizontal forest
editing retains semantic y-path/points units.

140 actual3.10.22/3.12.14 controls pass, including failed/holding metric claims,
empty/grid/concatenated-name/reserved-name cases. Seven Node semantic/path controls
pass. Source Chrome53 workflows pass, including metric axis/header edits/undo,
prospective append paths, old-review/new-data cancellation,1D strict ambiguity/
undo,2D structured keys, mobile keyboard/actual1px target bounds, strict extracted
metric/facet artists with original numeric marks and native forest orientation.
22 refreshed default PNGs retain exact decoded RGBA bytes relative to5773d58.
Final seven gates234/1511, zero skips/1 existing upstream warning, Ruff/gallery15
and source/fresh offline installed Chrome53 workflows/21 required-kind controls/
12 source matches pass,0 external requests/JS errors.140 final3.10/3.12 controls
pass; actual exported metric/facet text/numbers and native forest path/unit
semantics are checked. Proof: docs/workspace/panel-labels-verification.json.
Commit/exact CI pending. Full81 local acceptance is audited in
docs/workspace/direct-editing-acceptance.md;82–89 retain full original scope.


Requirement audit: docs/workspace/direct-editing-acceptance.md maps all original81
acceptance items to actual implementation/controls and states the measurement
scope. Local implementation is complete; final seven gates and exact pushed CI
are required before closing81. This does not close82–89 or the native goal.


## Final exact-commit acceptance

Implementation9d79aa838644b00d064063b05318b064c5c5477a is on main; exact main
41038823610 all nine jobs and Figure41038823929 passed. Actual CI editor
artifact12969657911 matches GitHub SHA256
47905ee77d23a233dcc880f33ab6b056651216b953cd99cb3affed70dc1f2923;
its actual checks.json confirms53 workflows/21 required-kind controls/0 external
page requests/JS errors. All original81 acceptance items are mapped to actual
implementation/measurement in docs/workspace/direct-editing-acceptance.md.
234 Node/1511 Python/seven gates/Ruff/gallery15,140 actual3.10/3.12 controls,
source/fresh offline53 workflows/12 source matches and22 default PNG RGBA
identities passed.81 is complete;82–89 and the native full goal are not.
