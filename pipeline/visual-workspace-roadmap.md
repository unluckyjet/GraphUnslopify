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
| 78 Dataset profile foundation | Actual types, missing/non-missing and finite counts, finite-only summaries, explicit heuristic limits, JSON-safe dates/nonfinite data, bounded repeat discovery, and atomic upload failure cleanup. Original input bytes and canonical suggestion integration remain intact. | Implemented; seven local gates225/1429 pass. Exact pushed CI pending. [Details](done/78-dataset-profile-foundation.md). |
| 79 Native Excel import | Optional reader dependency, explicit worksheet selection, source/type preservation and reproduction through the canonical schema, generated reader, auditing and bundles. Multiple sheets must not silently choose data. | Pending. |
| 80 Central figure workspace | Drop/picker import and data explorer left; central figure; settings/verification right; responsive layout, real profile details and reviewed recommendations. Existing controls, JSON, drafts, undo, stale-result handling, consent and exports remain usable. | Pending. |
| 81 Direct visual editing | Actual figure geometry targets for titles, axis labels, legends and annotations; edits update canonical intent. Review any change to data interpretation. Demonstrate actual render and export behavior. | Pending. |
| 82 Natural-language drafts | Model-backed proposed specifications grounded in selected data, disclosed assumptions and explicit review before applying. Validate with the deterministic compiler; do not fabricate observations, confidence or successful checks. Make provider/data disclosure explicit and retain offline manual authoring. | Pending; no model connection assumed. |
| 83 Spatial diagnostics | Clickable locations for actual collision, text/legibility and clipped-interval evidence, with the existing problem/consequence/fix guidance and verifier-owned repairs. Unknown locations remain unknown. | Pending. |
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
