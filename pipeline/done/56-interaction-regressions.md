---
id: 56
slug: interaction-regressions
status: done
priority: P0
title: Exercise chart aggregation missingness uncertainty and export interactions
source_idea: review2026-10-28 item5 broader regression and edge-case coverage
---

# Interaction matrix

Add a reproducible, bounded cross-feature matrix with independent numerical/artist and actual exported-file assertions. Cover representative supported chart kinds, aggregation, finite/missing/unit rows, estimator-specific intervals and PNG/SVG/PDF/HTML; include unsupported combinations and strict failures. Document the matrix and exclusions, avoid treating Cartesian test volume as a correctness claim, run seven gates/gallery and commit/push only verified evidence.


## Delivery evidence

`python/tests/test_interaction_matrix.py` adds34 combined controls; see
`docs/interaction-validation.md` for the bounded matrix and exclusions. Eighteen
presentation/estimator cells combine actual line/bar/forest/table values and
intervals with uneven technical repeats, missing measurements/IDs, lexical units
and PNG/SVG/PDF/HTML. Other cases cover unknown interval gaps, sparse heatmap
sum/count semantics, filtered/retained log coordinates, shuffled repeated metrics
and annotation targets, faceted paired tests/planned correction families, four
explicit unsupported combinations and two separate-process generated CLI runs.

Hand unit summaries1/2/9 and transformed4/6/20 are independent of generated
summarization. Real artist positions/intervals/table text and actual saved HTML
data calls match those quantities. Written artifacts have checked hashes/bytes,
provenance, PNG content, SVG structure/descriptions and PDF pages/text. Missing
quantities remain incomplete and unsupported combinations remain failed; this
is not a claim of exhaustive feature products, population coverage or external
researcher validity.

All seven local gates pass:222 Node/1158 Python (zero local skips/warnings),15
matching baselines,16 renders,25 recipes and7 composition cases. Ruff65 and strict
gallery15 pass. Only tests/docs/queue change; emitter, bundle and published
artifacts remain unchanged. General and Figure CI for the exact pushed commit
are checked before advancing. This delivers review item5; remaining review items
are tracked separately even if this focused implementation queue becomes empty.
