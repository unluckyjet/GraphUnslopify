---
id: 65
slug: accessible-editor-controls
status: ready
priority: P1
title: Edit scientific figure settings and claims through schema-driven browser controls
source_idea: review2026-10-28 item7 and source5dd3b17 basic controls require JSON for ordinary settings
---

# Researcher controls

1. Extend the packaged local editor using canonical per-kind schema choices for
   labels/units/scales, aggregation/uncertainty/repeat IDs, manuscript exports and
   kind-specific scalar/column/category settings. All21 kinds retain their existing
   schema/compiler; required specialized fields can be edited using controls.
2. Add editable claim rows with plain predicate labels, subject/reference/tolerance,
   actual strict verdicts and clear limitations. Preserve authored advanced JSON,
   custom labels and nested properties when unrelated controls change. Offer undo
   for control/recipe changes. Invalid JSON or numeric drafts never silently become
   a valid zero/default or revive old preview/download evidence.
3. Keep JSON available as advanced editing, accessible labels/help, keyboard controls
   and narrow-screen usability. Preserve loopback boundaries, owned patches, strict
   validation, stale-response refusal, real file picking and faithful exports.
4. Actual browser tests demonstrate editing without JSON, correct persisted control
   values and rendered report/bundle metadata, unsupported combinations rejected,
   invalid-draft recovery, advanced-field preservation, claim failure/recovery,
   specialized-kind controls and desktop/mobile screenshots with no external calls
   or JS errors. Fresh installed assets/behavior and all seven gates/exact CI pass.

## Implementation and local evidence (2026-10-28)

Protected info supplies canonical JSON Schema; packaged controls.js drives actual
choices/required scalar/column/category settings across21 branches. Native labels
and descriptions are separate; claim labels name literal numeric relationships,
blank new rows invent no assertion. Controls patch only their paths, batch typed
drafts, preserve custom axis labels/advanced settings, invalidate every edit and
retain bounded undo. Advanced JSON remains available for compound options.

Actual source and fresh installed Chrome workflows pass:21 workflows,21 required
kind mappings, zero external page requests/JS errors, native label lookup/live
focus, rejected incomplete exponent/required blank versus explicit0, literal
caption/category names, advanced preservation, owned fix, failed claims/recovery,
stale-response refusal and consent-controlled exports. Both controls-authored and
advanced bundles rerender outside the checkout with matching evidence. Desktop
and390px mobile screenshots inspected. No independent usability study claimed.

All seven local gates pass:222 Node/1277 Python, no skips, baseline15/render16/
recipes25/compositions7/Ruff78. One upstream SQLAlchemy warning remains visible.
Final wheel's four web assets match source bytes; agent/PDF/environment/comparison/
workflow/tracking/required-controls smoke passes with runtime network blocking.
Installed Chrome uses the actual wheel outside checkout source; the driver's
loopback fetch for held responses is separate from blocked product Python/Node.
Explicit external translator request is rejected. Legacy0.8.0 probes retain
defaultFalse for the new asset requirement. Exact pushed CI remains pending.
