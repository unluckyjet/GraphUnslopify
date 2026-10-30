---
id: 81
slug: direct-visual-editing
status: ready
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
