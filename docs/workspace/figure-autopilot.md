# Reviewed figure alternatives from a dataset and question

Current source includes a Python core API that proposes three figure views,
explains their trade-offs and runs actual strict native checks after review.
The CLI and editor workflow are still in progress. This is newer than published
PyPI0.8.0; use a current [local checkout](../../README.md).

```python
from graphunslopify.autopilot import propose_figures, generate_drafts

plan = propose_figures('results.csv', 'How does loss differ between models?')
print(plan.report)
for draft in plan.drafts:
    print(draft['name'], draft['why'], draft['tradeoff'], draft['assumptions'])

# After inspecting the source, mappings, units, exclusions and every assumption:
result = generate_drafts(plan, 'new-draft-folder', reviewed=True)
print(result['status'])
```

An unresolved question or ambiguous mapping returns `report['ready'] == False`
with a reason and no fabricated drafts. Specify reviewed choices and propose again:

```python
plan = propose_figures(
    'results.csv', 'How does performance differ?',
    intent='comparison', target='loss', group='model', units={'loss': 'score'},
)
```

The complete question is preserved. Mapping uses deterministic question/field
heuristics, clearly marked for review; there is no claim of arbitrary language
understanding or certified scientific appropriateness. No model service receives
data. Proposal validation and generation explicitly use the local compiler.

## The three views

| Question intent | Proposals | What to review |
| --- | --- | --- |
| Comparison | Box with raw points, empirical distribution, descriptive mean bars | Means and quartiles describe reviewed rows; no population uncertainty or significance is asserted |
| Trend or relationship | Raw scatter, ordered descriptive line, empirical distribution | Select the x field; repeated x/group rows use explicitly disclosed means; continuity is not a fitted or causal model |
| Distribution | Empirical distribution, box with raw points, raw-value scatter by source record | Record position is an index, not time or an independent unit; these are complementary views of the same data |

Each proposal includes its reason, trade-off, assumptions and canonical spec.
No units, percentage scaling, independent units, confidence intervals or
optimization directions are guessed. `units` supplies display labels for selected
fields; it does not convert values. Existing profile-role guesses remain heuristics.
Grouping/series order stays consistent across the three views.

## Inputs, exclusions and identity

CSV, regular JSON tables, Parquet and selected Excel worksheets are supported.
Parquet/Excel need the existing optional reader dependencies. Use `sheet='Results'`
for a workbook with multiple worksheets. For temporal x, select `predictor` and
explicitly set `predictor_temporal=True`; numeric row order is not inferred as time.

The plan lists original zero-based source-record positions and reasons for
missing/nonfinite/invalid values. All three views use the same reviewed joint-valid
sample across selected fields. If exclusions exist, generation requires both
`reviewed=True` and `accept_exclusions=True`. This acknowledgment is explicit;
it does not justify an exclusion scientifically.

Original inputs stay unchanged. Selected plotting values, source positions and
group identities are materialized in an owned JSON table. The native identity
loader preserves names such as001 and002. Measurement agreement with the native
JSON reader is checked at relative tolerance1e-14/absolute tolerance0. The proposal
snapshot binds question, requested/resolved choices, report metadata, drafts and
data hash. Changed sources or mutated proposals require review again.

Bounds:20MiB source/normalized table,100000 rows,128 named fields and32 groups.
Planning runs in an owned worker with a30-second deadline,1GiB process-tree RSS
budget and32MiB output budget. Reader errors/refusals are explicit; partial parser
output is never accepted.

## Actual generation and outputs

The destination must be new. It receives `autopilot-data.json`, `autopilot.json`
and one directory per draft with canonical intent, generated Python, native
reports and PNG/SVG/PDF outputs. Generation checks all three and preserves each
passed, failed or incomplete outcome. The root result is passed/exit0 only when
all three pass and source/materialized data remain unchanged. Otherwise it stays
incomplete/exit2. A failed draft is retained alongside successful alternatives.

Verification means the declared native checks passed. It does not establish
experimental independence, general scientific appropriateness, adoption or a
productivity advantage. These proposals are starting points for author decisions.

Tests cover all input readers, source/metadata/data/spec tampering, review and
exclusion requirements, question-dependent alternatives and actual strict failures.
`scripts/check-figure-autopilot.py` additionally checks public penguin observations
against actual numerical artists: raw group points, empirical steps and descriptive
means. It retains strict layout failures. GitHub Actions runs this core check on
both supported Python profiles and saves its artifacts. CLI/editor integration,
review/compare/select/apply/undo and their final acceptance remain unfinished.

See [the complete initiative](../../pipeline/research-platform-roadmap.md),
[source imports](source-imports.md) and [the local editor](../local-editor.md).
