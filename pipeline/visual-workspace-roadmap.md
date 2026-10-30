# Visual research workspace

This is the user's next initiative after the [completed scoped review](../docs/review-completion-2026-10-29.md).
The supplied advice calls for easier visual authoring and a connected scientific
review workflow. The existing 21 kinds, strict verification, local data boundaries,
source-data export consent and reproducible evidence remain the foundation.
Commit and push each coherent milestone, run the seven required local checks,
and verify both workflows for that exact commit before advancing.

The earlier familiarized-agent timings favor Matplotlib on the measured workload.
They are historical observations, not current editor timings or human productivity
evidence. Profile before replacing rendering architecture. Version suggestions in
the advice describe goals; this initiative does not publish or promise a release.
Outside researcher trials remain deferred at the user's request.

## Implementation order

| Milestone | Scope and acceptance | State |
| --- | --- | --- |
| 78 Dataset profile foundation | Actual types, missing/non-missing and finite counts, finite-only summaries, explicit heuristic limits, JSON-safe dates/nonfinite data, bounded repeat discovery, and atomic upload failure cleanup. Original input bytes and canonical suggestion integration remain intact. | Verified b95f833; seven local gates225/1429, exact main40895079839 all9/Figure40895079807 pass. [Details](done/78-dataset-profile-foundation.md). |
| 79 Native Excel import | Optional reader dependency, explicit worksheet selection, source/type preservation and reproduction through the canonical schema, generated reader, auditing and bundles. Multiple sheets must not silently choose data. | Backend be160ba exact all9/Figure verified. Browser6d7a085 passes227/1444/seven gates and exact main40909604542 all9/Figure40909604658; actual source/fresh installed26 workflows verified. [Details](done/79-native-excel-input.md). |
| 80 Central figure workspace | Drop/picker import and data explorer left; central figure; settings/verification right; responsive layout, real profile details and reviewed recommendations. Existing controls, JSON, drafts, undo, stale-result handling, consent and exports remain usable. | Implemented; seven gates227/1444, source/fresh installed31 browser workflows/all21 kinds and paper13 workflows pass. Actual measured before/after board and unchanged rendered pixels retained. Exact8bb1d4a main40915277406 all9/Figure40915277467 pass. [Details](done/80-central-figure-workspace.md). |
| 81 Direct visual editing | Actual figure geometry targets for titles, axis labels, legends and annotations; edits update canonical intent. Review any change to data interpretation. Demonstrate actual render and export behavior. | Geometry d0178e0 exact all9/Figure verified. Display-alias81b local seven gates227/1485,114 minimum-Python controls, source/fresh installed33 workflows, actual literal HTML and22 default PNG identities verified; 7ab724f exact main41024904963 all9/Figure41024904907 passed. Actual click/review/apply/undo81c passes230/1485/seven gates, source/fresh installed41 workflows/12 source matches and strict reproduced artists; 57b4652 exact all9/Figure passed. Reference/layer81d passes232/1494/seven gates,123 actual3.10/3.12 controls and source/fresh installed45 workflows; 5773d58 exact main41033640343 all9/Figure41033640564 passed. Metric/facet81e and full local81 acceptance pass234/1511/seven gates,140 actual3.10/3.12 controls and source/fresh offline53 workflows/12 source matches; 9d79aa8 exact main41038823610 all9/Figure41038823929 passed; actual CI artifact12969657911 confirms53 workflows. Complete. [Acceptance audit](../docs/workspace/direct-editing-acceptance.md). [Details](done/81-direct-visual-editing.md). |
| 82 Natural-language drafts | Model-backed proposed specifications grounded in selected data, disclosed assumptions and explicit review before applying. Validate with the deterministic compiler; do not fabricate observations, confidence or successful checks. Make provider/data disclosure explicit and retain offline manual authoring. | Backend82a in progress: actual source/fresh-installed local-model inference and strict exports pass; browser consent/review/apply/undo/stale fences remain. [Details](specs/82-model-backed-drafts.md). |
| 83 Spatial diagnostics and owned layout | Clickable locations for actual collision, text/legibility and clipped-interval evidence, with the existing problem/consequence/fix guidance and verifier-owned repairs. Measure layout refinements for nested/long headings and complete shared value ranges; unknown locations remain unknown. | Pending. |
| 84 Measured rendering overhead | Record cold/warm translation, reading, statistics, draw, inspection and export costs first. Evaluate persistent workers with ownership, bounded lifecycle, timeout recovery and no state leakage. Retain evidence when an idea does not help. | Pending. |
| 85 Incremental and staged preview | Cache processing by input contents, transforms, calculation settings and dependency/runtime versions; presentation-only changes reuse appropriate calculations. Fast previews remain visibly unverified; final strict checks and current-revision exports cannot use stale acceptance. | Pending; depends on profiling. |
| 86 Compact versioned runtime | Reuse actual runtime functions through a versioned library, preserve scientific/report/export behavior and retain a genuinely standalone bundled export. Measure script size and execution effects. | Pending; depends on profiling. |
| 87 Scientific Figure Review Mode | Connect existing paper projects, generated or inspected figures, claims/uncertainty/legibility/repro evidence, fixes/reruns, batch/shared-style updates, selective regeneration, history and auditable export. Keep source-free inspection limits visible. | Pending. |
| 88 Repeated-work controls | Keyboard shortcuts, command search, multi-select edits, reusable templates and publication/export presets after the core interactions work. Preserve renderer-owned layout and scientific semantics. | Pending. |
| 89 Comparative evaluation and delivery audit | Freeze comparable tasks and unchanged correctness gates before measuring the new workflow. Report time to verified figure, render latency, batch update time, errors/false alarms and reproducibility with actual denominators and negative outcomes. Independent/blind human judgments stay future work while volunteers are deferred. | Pending. |

Do not mark the initiative complete from an empty focused queue, a visual mockup,
synthetic model responses, or passing unit tests alone. Preserve observed failures
and distinguish installed/source behavior from the immutable PyPI 0.8.0 release.

## Editor design boundary

Job: import real data, choose fields, review the figure and evidence, and export
without needing to edit JSON. Current baseline is the packaged local editor in
`python/graphunslopify/web/`; capture actual desktop/mobile views before layout
changes. Preserve its palette, typography, schema controls and all result states.

Structural references inspected through Mobbin:

- [Retool](https://mobbin.com/screens/ca7c6cd0-39cd-4956-9359-20c8456a14a4): central selected chart, left navigation/components, right property inspector.
- [Databricks](https://mobbin.com/screens/5b995fc9-de89-490c-a906-1a5e33345f37): dataset context and central chart with a separate field/settings inspector.
- [Rows](https://mobbin.com/screens/9091edab-43d4-4bbd-9ca3-dce92b2bac3f): data table and chart next to explicit chart properties.

These inform hierarchy and placement; their branding and data are not part of
GraphUnslopify. No usability or speed improvement has yet been measured.
