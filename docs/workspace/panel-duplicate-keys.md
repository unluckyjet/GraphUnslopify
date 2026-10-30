# Panel-aware duplicate warnings: checkpoint 83b

Unaggregated line/bar scripts check duplicate x values after input filtering,
identifier normalization and numeric preparation. The prepared frame includes
all facets. The check now includes the original facet column and optional row
identities alongside x and series, so observations in separate panels cannot
trigger each other's warning. Display aliases do not replace source identities.

The original eight-row/four-panel browser export has no duplicate
`(epoch, condition, phase)` tuples. Before the repair it printed
`repeated_x_values`; afterward it does not. Both strict exports pass, retain the
same canonical spec hash and original CSV bytes, and produce exactly identical
4160×4986 RGBA pixels. See [measured evidence](panel-duplicate-keys/measurements.json).

This preserves the existing advisory-log contract: `repeated_x_values` is printed
with consequence/correction guidance and is not a machine finding. It does not
gain invented spatial coordinates or a different failure policy.

`python/tests/test_panel_duplicate_warnings.py` has 21 focused cases: 20 actual
strict script executions and one semantic refusal. They cover vertical/horizontal
bars, lines, one/two-dimensional facets, original identities under display
aliases, series groups and raw filters. Fourteen valid executions pass; six
ambiguous unaggregated-bar executions retain their native runtime refusal and
duplicate warning. Faceting by the series group remains a semantic error.
Actual within-series line duplicates still render with the existing warning.
No observations are averaged or removed to make a case pass.

The preceding range repair, 9b4c1c1, passed exact main 41064322822 all nine jobs
and Figure 41064322645 before this checkpoint began. All seven new local gates pass on stable source/test files: 234 Node/1603 Python,
zero skips/one existing upstream MLflow/SQLAlchemy warning. The 21 focused cases
pass on actual Python 3.10.22, 3.12.14 and a fresh offline installed wheel. Source
and installed browsers each pass 66 workflows across all 21 native kinds, with
zero JavaScript errors/external requests. All 14 installed assets match source.
The model cases use a controlled provider; no new inference-quality claim is made.
Baseline 15/reference 7 programs were genuinely regenerated; gallery passes 15/15.
All 75 pre-existing tracked PNG bytes remain identical. See
[verification](panel-duplicate-keys/verification.json) and the adjacent browser,
installation and PNG audit JSON. Exact new-commit CI is checked after pushing. Spatial overlays and measured owned layout remain
open in 83, with the full 84–89 roadmap preserved. This is later source work,
separate from the published 0.8.0 release.
