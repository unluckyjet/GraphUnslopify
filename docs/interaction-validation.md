# Cross-feature regression coverage

This is a bounded integration matrix for the current source checkout, extending
[the 21-kind numerical references](scientific-validation.md). It tests combinations
that individual feature checks cannot establish. It does not claim an exhaustive
Cartesian product, independent researcher validation, or that an experiment's
sampling/design assumptions are true.

`python/tests/test_interaction_matrix.py` has34 cases:

| Cases | Combined behavior | Independent answer / evidence |
| --- | --- | --- |
|18 | Line with bars/bands, vertical/horizontal bar, forest and table × mean/SEM, median/bootstrap CI, median/IQR; uneven technical repeats, lexical unit IDs, missing measurements/IDs and static/HTML exports | Unit summaries1/2/9 have mean4, median2, SEM√(19/3), bootstrap-median bounds1/9 and IQR1.5/5.5. A second coordinate's4/6/20 units have mean10, median6 and correspondingly transformed bounds. Actual marks/cells and saved HTML trace values must match. |
|2 | Unknown middle-coordinate interval × line error bars/bands × static/HTML | Actual line keeps a NaN gap and HTML keeps null; no false zero. Required uncertainty remains incomplete/strict exit2. |
|2 | Sparse heatmap × sum/count × zero/missing/absent cells × cell annotations/static/HTML | Sum cells are[[0,4],[unknown,unknown]]. Counts are[[2,2],[0,unknown]]: counting an observed entirely missing cell legitimately gives0; an absent cell stays unavailable. |
|2 | Scatter × log scale × explicit source filtering × static exports | Retaining a negative log coordinate fails strict; filtering it explicitly retains three of four source rows, discloses selection, and preserves the three actual positive points. |
|2 | Repeated metrics × named-unit SEM × annotation targets × shuffled/unshuffled rows | Score curves4/10 and transformed cost11/23 remain separate, including each panel's requested last-point anchor and metric identity. |
|2 | Faceted paired tests × technical repeats/01-versus-1 IDs × explicit category order × Holm/BH × unavailable planned comparisons | Four differences1/4/2/6 give two-sided exact sign-flip p=2/16. Both three-comparison corrections give3/8; two unavailable pairs remain in each panel's family and make strict incomplete. Actual category-labelled bars retain25/28.25, with an independently shifted second panel. |
|4 | Refused estimator, stack/interval, facet/repeat and unsupported interactive combinations | Translation errors remain present in reports; directly running the generated program cannot turn them into a strict pass. |
|2 | Actual separate-process generated CLI × valid/gapped median CI × annotation/static exports | Default strict exit0 versus2, stdout/disk report equality, actual end value6, report schema, and saved artifact evidence. |

## What the checks observe

Numeric cases inspect actual Matplotlib lines, bar containers/error segments,
forest centers/bounds, matrix arrays and table cells. The test does not use the
generator's summary function as its expected-value oracle. Uneven raw row counts
would produce different estimates if named units were accidentally given unequal
weight;01 and1 must remain distinct units after CSV loading.

Generated programs run their actual CLI policy and inspector; a wrapper captures
the figure without replacing inspection. Two additional cases run a separate
Python process through the generated script's normal entry point. Reports are
validated against the runtime schema. Expected incomplete/failed controls remain
explicit; warnings are not automatically reclassified as failures.

Saved PNG/SVG/PDF/HTML artifacts are read back. Checks compare recorded byte counts
and hashes, common data/spec/source fingerprints and descriptions; read PNG pixels,
SVG structure/native accessibility descriptions and PDF pages/text; and parse the
actual `Plotly.newPlot` data call in saved self-contained HTML. Numerical HTML
values and interval arrays/bands are compared with hand answers and static marks.
Markdown/LaTeX table output hashes are also checked. Artifact provenance alone is
not the numerical oracle, and PNG color presence is not a full pixel-level semantic
comparison. Existing browser and real-LaTeX CI remain separate checks.

## Reproduce

Use the development environment described in the repository README, including
`dev,interactive,statistics` extras, then run:

```sh
python -m pytest python/tests/test_interaction_matrix.py -q
```

The normal `npm run test:python` and Python3.10/3.12 CI include these tests.
Source additions after0.8.0 are not attributed to its immutable published wheel.

## Limits

Six supported kinds and representative presentations are integrated here; the
existing core suite covers all21 kinds separately. Specialized estimators,
transforms, date axes, category overlays, custom clips, arbitrary optional
combinations, browser interactions, visual pixel equivalence, experimental
independence and population interval coverage are not comprehensively established
by these34 cases. Follow the focused suites and contracts for their separate
measured domains. New failures should add a concrete counterexample rather than
merely enlarge a Cartesian test count.
