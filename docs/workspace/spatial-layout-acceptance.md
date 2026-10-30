# Spatial diagnostics and owned layout: acceptance review

**Implementation accepted at `de6571009b2a3e4f3d29e9a02053e51a83a0b447`.**
All nine main jobs in run41137594346 and Figure run41137594427 completed
successfully; final metadata and all ten named checks were verified22:41UTC on
2026-10-30. [Exact acceptance](owned-text-layout/ci-acceptance.json),
[actual CI browser results](owned-text-layout/ci-editor-checks.json), and
[actual CI NIST results](owned-text-layout/ci-certified-summary.json) bind this
conclusion to source and digest-verified downloaded ZIPs.

The separate closing-record checkpoint has its own fresh seven-gate pass on
unchanged production/test files ([receipts](spatial-layout-acceptance/local-gates.json),
[source hashes](spatial-layout-acceptance/tested-source-manifest.json)). Closing bb4c231 exact main41140106558 all nine/Figure41140106580 passed;
[final source-bound metadata](spatial-layout-acceptance/closing-ci-acceptance.json)
was verified before84 implementation. Tasks84–89 retain their full
scope; this acceptance publishes no release.

## Required scope mapped to actual evidence

| Requirement | Implementation and observed acceptance |
| --- | --- |
| Select actual collision, small-text and clipped-interval locations | [Inspector/final-PNG geometry](diagnostic-geometry.md), python/tests/test_preview_diagnostics.py and preview-diagnostics-check.ts cover actual ink, inverted/native axes, capture failures, unknown findings and bounded capacity. [Clickable overlays](clickable-diagnostics.md) preserve existing problem/consequence/fix guidance. |
| Final image/spec/data/run ownership, responsive/keyboard alignment and stale refusal | Version/hash/dimensions/finding identity/current generation are checked; missing/unknown/partial locations stay explicit. Real normal/narrow/wide/short-height, picker/card/keyboard and one-CSS-pixel geometry cases remain in the source/fresh editor suite. |
| No mutation merely from diagnostic selection; explicit strict repairs | Selection keeps current intent/exports/text drafts; explicit verifier fixes rerender even in manual mode and native undo invalidates newer evidence. Wrong/stale/malformed maps cannot create targets. |
| Complete shared automatic bar extents | [Original2/4 failure](shared-bar-range.md) and17 native controls show automatic0..2.1 becoming0..4.2 without authored limits. Value/interval/signed/stacked/native orientation controls remain; authored clipping still fails. Unsupported horizontal repeats remain refused. |
| Prepared duplicate keys preserve panel/group identity | [Panel-aware duplicates](panel-duplicate-keys.md) and21 controls keep the original8row/four-panel CSV/spec/pixels while removing the false global warning. Actual within-panel duplicates and ambiguous bars remain warned/refused. |
| Date labels, complete long/nested headings and native title ownership | [Measured dates](date-label-layout.md), [headings](heading-layout.md), [available-margin regression](heading-margin-regression.md), [literal/math](heading-literal-context.md) and [title ownership](heading-ownership.md) preserve source words/units/letters/data-area heights and real glyphs. Single-facet/global and broken-axis titles remain distinct. |
| Complete source legends and correct label meaning | [Outside boxes](outside-legend-layout.md) retain full words/source handles/native fonts/panel ECE values; shared boxes clear the full grid. [Direct names](direct-series-endpoints.md) use actual rendered means/probabilities/fits/categories/bar ends, preserve raw IDs/aliases and remove duplicate sparkline parent names. |
| Complete child/table text with current source quantities | [Owned child/table layout](owned-text-layout.md) replays the original three failures2→0 at full text scale, keeping child numeric arrays/shared ranges/data height, fonts, literal/math interpretation, table numbers/units and identical Markdown/TeX bytes. Other insets keep ownership; unfit columns/names still fail. |
| Strict checks, genuine exports and reusable knowledge | Final local seven gates232/1816/Ruff108;25 new and236 minimum/fresh controls; source/fresh101 workflows/21 kinds and five minimum-browser workflows;19 installed asset matches; genuine15 baselines/seven references/gallery15;115/115 prior PNG pixels unchanged. Shared Obsidian canonical notes and investigation evidence are maintained. |

## Independent checks of the measured result

The frozen NIST protocol/evaluator/producers remain unchanged. The current72-run
replay (nine datasets, two arms, repeated clean/missing-interval variants) accepts
18 clean runs and rejects18 interval controls per arm with zero execution
failures. Current source/fresh tests and actual downloaded CI archives are kept
separate from the immutable PyPI0.8.0 release. Earlier failed c02c43f margin and
aace57e incomplete-provenance checkpoints remain explicit historical failures;
they are not counted as accepted revisions.

The actual old/current label replay records original passes honestly: a pooled
mean could exit0 with an absent name, and duplicated sparkline names also passed.
Native exported-text/coordinate checks establish the corrected binding. No
before image is invented for an original program that failed before export.

## Boundaries retained

- Geometry is observational. Unlocated semantic findings and incomplete capture
  are not assigned invented positions; arbitrary external outputs lack this
  generated-artist ownership contract.
- The generic legend data-occlusion inspector is owner-local; an old shared box
  could intersect another data axes region while strict inspection passed. The
  owned formatter independently clears the full grid; this is not universal
  external cross-panel occlusion detection.
- Unbreakable wording, constrained many-column tables, coincident direct labels
  and dense foreign insets can remain strict failures. Fitting does not truncate
  names, discard observations, alter estimators/units or make claims pass.
- These are deterministic controlled regressions and project-run external-fact
  checks. They establish no blind reviewer preference, human/model quality,
  independent adoption, causal productivity or general speed advantage. Researcher
  volunteers remain deferred at the user's request.

The complete milestone83 implementation and its controlled acceptance are verified.
Closing bb4c231 passed its separate exact-CI gate before84. The full84–89
roadmap now continues with measured rendering overhead; this acceptance does not
claim those remaining milestones complete.
