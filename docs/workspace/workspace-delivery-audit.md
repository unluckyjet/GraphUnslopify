# Visual research workspace: 78–89 delivery audit

The authorized development scope is implemented and the frozen comparative study
is complete. The result is a connected local workspace for importing real data,
visually editing canonical figures, reviewing scientific evidence and maintaining
paper projects. The [436-cell comparison](../../benchmarks/workspace/results/formal-v1/README.md)
also records a significant limit: GraphUnslopify fails the frozen physical-width
tasks and has no verified-speed advantage over the strong Matplotlib baseline.

This audit separates implemented capabilities, measured engineering effects and
unavailable outside judgments. It does not infer completion from an empty queue
or passing unit tests alone. Public PyPI 0.8.0 remains immutable and older than
the measured source; no new release/tag is part of this delivery.

## Source and verification basis

The measured implementation is full Git
`d9d4b694f54c6f4fd5bb2027090e50c54c0b2cba`. Its 77 production SDK files
byte-match accepted `df85f0b651c2b1b247edece9c166d3f531b8b304`. The final delivery
adds documentation, original results and read-only recovery/analysis tools;
it does not change those production files or retrospectively change the study.

On D9, all seven required local checks, both actual complete CI Ruff invocations
and strict gallery regeneration pass: 235 Node tests, 2,155 Python tests, zero
local skips, one upstream warning, 233 Ruff-formatted files, 15 gallery figures.
All 943 tested working/index/commit paths match. Exact 14 checks pass across
[main](https://github.com/unluckyjet/GraphUnslopify/actions/runs/41454996425),
[Figure CI](https://github.com/unluckyjet/GraphUnslopify/actions/runs/41454996404) and
[native preparation](https://github.com/unluckyjet/GraphUnslopify/actions/runs/41454996450).
The complete main Python jobs retain 2,150 passed/5 skipped each; warning counts
are 28 on 3.10 and one on 3.12. Those CI skips are distinct from the local suite.

Actual original D9 artifacts were independently read and checked: four platform
wheel/sdist/resource and installed-interface archives; the complete browser
archive; paper and source-replay archives on both Linux Python versions; genuine
SDK-free standalone replay; and four native preparation archives. Their original
inputs, programs, saved artists, reports, source/package bytes, contexts and
current-evidence bindings remain separate from new rendering. The subsequent
[formal native run](https://github.com/unluckyjet/GraphUnslopify/actions/runs/41473938665)
also passes all four jobs; its 192 original exports were re-evaluated against the
unchanged independent oracle.

The capability evidence below reuses accepted observations where source bytes
remain applicable, with current source/gates and focused actual replays. It does
not relabel earlier workloads as new measurements or claim every historical
browser workflow was rerun during the formal study. The delivery commit must
also pass its own required local checks and exact main/Figure/native CI before
the work is reported complete to the user.

## Complete scope map

| Scope | Delivered behavior and source | Evidence and practical limits |
| --- | --- | --- |
| [78 Dataset profiles](../../pipeline/done/78-dataset-profile-foundation.md) | `describe.py`, `preview.py` and data-explorer controls report actual types, missing/finite counts and finite summaries; reviewed heuristic suggestions feed canonical intent. | `test_describe.py`, `test_preview.py`, real drop/picker browser checks and source-bound fixture profiles. JSON-safe dates/nonfinite values, bounded discovery and atomic failed-upload cleanup remain explicit. Suggestions are not scientific conclusions. |
| [79 Excel](../../pipeline/done/79-native-excel-input.md) | `workbook.py`, the generated reader and audit/bundle paths preserve selected worksheet/source types; a multi-sheet workbook requires selection. | `test_workbook.py`, actual source/fresh worksheet workflows and native Excel artifacts in all four D9 distribution jobs. Excel/Parquet remain optional extras, not silently available in a minimal install. |
| [80 Central workspace](../../pipeline/done/80-central-figure-workspace.md) | The packaged `web/` editor provides left data exploration, central figure and right settings/verification, with responsive import, JSON/drafts/undo and current-result/export boundaries. | Actual source/fresh browser workflows, all-kind native checks and preserved default pixels. The real browser remains the evidence; a conceptual mockup is not a shipped feature. |
| [81 Direct editing](../../pipeline/done/81-direct-visual-editing.md) | `preview_geometry.py`, canonical display aliases and text controls bind title/axis/series/legend/annotation/metric/facet edits to actual saved geometry and reviewed intent. | [Acceptance](direct-editing-acceptance.md), `test_preview_geometry.py`, source/fresh actual click/review/apply/undo and strict original-artist replays. Data/claim IDs, units, orientation and stale revisions stay guarded. |
| [82 Natural-language drafts](../../pipeline/done/82-model-backed-drafts.md) | `drafts.py` and `preview_drafts.py` ground a provider proposal in selected data context, disclose assumptions and require review before canonical apply/undo and deterministic validation. Manual authoring works offline. | [Acceptance](model-draft-acceptance.md), actual historical local-model source/fresh proposals and native replays, plus transport/consent/failure tests. Contract doubles are not model-quality evidence; no general model-quality or provider-latency study is claimed. |
| [83 Spatial diagnostics/layout](../../pipeline/done/83-spatial-diagnostics-layout.md) | `preview_diagnostics.py`, verifier-owned text geometry, complete nested headings and shared ranges connect actual findings to visible evidence and supported fixes. | [Acceptance](spatial-layout-acceptance.md), geometry/diagnostics tests and actual browser/native controls. Unknown or stale locations remain unknown; preserved pixels and measured layout do not establish blind visual-quality superiority. |
| [84 Persistent workers](../../pipeline/done/84-measured-rendering-overhead.md) | Owned renderer/compiler workers retain imports with explicit state reset, lifecycle budgets, failure/timeout recovery and clean ownership. | [Original versioned measurements](../../benchmarks/rendering/README.md), worker/translator tests and actual current/minimum/fresh/Windows controls. All first-start, setup, slower and strict-negative outcomes remain; historical 135 formal records are not pooled with 89. |
| [85 Incremental/staged work](../../pipeline/done/85-incremental-staged-preview.md) | `numerical_cache.py` binds reusable calculations to current data, transformed arguments, scientific settings, helpers and versions. `preview_staging.py` exposes a current unverified image without granting final acceptance. | [Accepted full85](staged-preview-acceptance.md), cache/staging controls and original 510 numerical/612 staged outcomes. First-image medians improve in 42/42 variants; final results are slower in 31/42. Current acceptance, export, consent and stale-image fences remain mandatory. |
| [86 Compact runtime/bundles](../../pipeline/done/86-compact-versioned-runtime.md) | `figure_runtime.py` and `runtime_bundle.py` reuse versioned runtime code and preserve a genuinely standalone export, with source/licence/capability checks. | [Original 900-record/30-case comparison](../../benchmarks/runtime/results/measured-v1/README.md), all 21 kinds, runtime/bundle guards and actual D9 minimum/source/fresh/SDK-free artifacts. Script-size improvements and mixed latency are reported separately; missing/wrong runtime never becomes a stale success. |
| [87 Scientific review](../../pipeline/done/87-scientific-figure-review-mode.md) | `project_review.py`, inspections, reviewed shared changes/undo, selective regeneration and `project_export.py` join claims, uncertainty, legibility and reproduction with original-run ancestry. | Review/PDF/shared-change/reuse/export tests, accepted source/fresh review workflows, actual portable packets and D9 paper/current-evidence artifacts. Imported/PDF evidence is bounded; unsupported claims remain unavailable and source-data export requires consent. |
| [88 Repeated work](../../pipeline/done/88-repeated-work-controls.md) | Command search/shortcuts, selected presentation edits, canonical templates and publication/export presets preserve intent, renderer-owned layout, review and undo. | [Intent reuse](intent-reuse.md), actual source/fresh 248-workflow acceptance and 30 native replays/all 21 kinds, current original controls and unchanged source. Focused typing, per-figure overrides, incompatible/PDF exclusions and changed data/unit assumptions remain guarded. Presets prepare exports; they do not guarantee physical compliance. |
| 89 Comparison and delivery | Complete fixed controllers, native dispatch, prospective qualified seal, strong independently authored baseline, unchanged task gates, all actual cells and published byte-preserving originals. | [Formal report](../../benchmarks/workspace/results/formal-v1/README.md): 192/54/48/64/64/14 retained. Both arms match all 24 classifications; Graph has no fully task-correct width outcomes or verified-speed winner. All 13,800 originals round-trip, and the restored Python3.10 analysis matches the original apart from file locations. |

The named tests live under `python/tests/`; browser and native acceptance drivers
live under `scripts/`. Each linked original contract retains its full scope and
checkpoint evidence. The preserved `pipeline/specs/87-scientific-review-workspace.md`
is a link to completed87, not a second unfinished implementation.

## Documentation, installation and preserved evidence

The main README retains all 52 image placements and 51 original graphics across
the main/Python READMEs. The current source-install guide distinguishes clone,
virtual environment, Python 3.10+, package extras, local editor launch,
PowerShell and offline use after installation. Actual D9 source/minimum/fresh,
four-platform installed interfaces and native Excel/bundle evidence support
those routes; a description alone is not an installation test.

The protocol README stays frozen. Current comparison status is corrected in the
main README, implementation/controller guides and roadmap. Full85's old
pending-publication wording is explicitly resolved against its actual accepted
closing commit and CI, without rewriting its measurements. Queue closure is
bounded to78–89; it does not refill itself with unrelated features.

The shared Obsidian project folder `JsonTransalter/` records canonical current
behavior, known gaps, original evidence and investigation history. Its spelling
and existing shared-vault links are preserved. Raw inputs and logs are public
benchmark evidence; no credentials or private datasets belong in those notes.

## Remaining limitations and deferred work

- **Physical export width:** tight cropping defeats the frozen exact-width
  task. Do not weaken the gate or advertise verified-speed superiority. A future
  production fix needs its own normal behavior tests and new prospective study.
- **Public filter control:** the frozen redundant sex filter has no public
  control; that browser task remains incomplete against its full task gate.
- **Startup observations:** older source/installed loading stalls remain
  preserved with unknown original cause. The later 5-to-128 socket backlog
  change has its own 56/64 versus64/64 control; it does not prove those older
  stalls had the same cause.
- **Outside judgments:** researcher volunteers, blind ratings, adoption and
  general model quality remain user-deferred/unmeasured. Familiar public data
  and scripted project-run evidence do not substitute for them.
- **Release:** no new publication is authorized. `pip install graphunslopify`
  still refers to immutable public0.8.0; use the documented source route for
  newer capabilities.

These limitations remain searchable in the project knowledge and report. They
are not silently dropped because the development initiative is closed.
