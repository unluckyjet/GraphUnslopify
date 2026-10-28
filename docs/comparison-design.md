# Statistical comparison design

**Available in current source, after 0.8.0.** Install a checkout with
`python -m pip install -e './python[statistics]'`. Published0.8.0 supports
independent comparisons; it does not implement the paired fields below.
Regenerate scripts after upgrading. A successful render does not prove that an
experiment's sampling design, normality or exchangeability assumptions hold.

A complete synthetic example (four independent participants, two technical measurements
per participant and condition) is in [examples/statistical-design](../examples/statistical-design/paired.json).
Run from the repository root after the source installation:

```sh
graphunslopify render examples/statistical-design/paired.json --out-dir /tmp/paired-review --json
```

The matching-independent example is a deliberate counterexample: its shared-ID
warning explains why independent testing is inappropriate if these are the same
participants. It is not a second valid analysis of this declared paired design.

## Choose the actual experimental unit

`uncertainty.over` identifies units assumed independent, such as participant,
independently trained model, animal or experimental batch. Technical measurements
within a unit/category are summarized before either uncertainty or comparisons.
Rows are treated as independent when no unit is declared; this is now explicitly
recorded in comparison evidence. Reused labels alone do not establish dependence:
independent tests report shared IDs and warn that actual matched subjects need a
paired design.

For the same subjects under two conditions, use:

```json
{
  "kind": "bar",
  "data": {"path": "measurements.csv"},
  "x": {"field": "condition", "label": "Condition"},
  "y": {"field": "score", "label": "Score"},
  "aggregation": "mean",
  "uncertainty": {"kind": "sem", "over": "participant", "display": "bar"},
  "significance": {
    "design": "paired",
    "pair_by": "participant",
    "method": "ttest",
    "pairs": [["before", "after"]],
    "correction": "holm"
  }
}
```

Pairing uses lexical IDs, never row order: `01` and `1` remain distinct. Only
matched pairs with finite measurements enter the test. Reports include complete
pairs, left/right-only units, nonfinite pairs and missing IDs. Bars still summarize
available units in each category; a warning discloses when exclusion changes the
tested population. Filter to complete units first when you want the displayed and
tested means to describe exactly the same cohort. Missingness can bias the result;
this tool does not establish that complete cases represent the population.

## What each test claims

| Method | Independent design (default) | Paired design |
| --- | --- | --- |
| `ttest` | Welch test of equal population means; does not assume equal variances. | Paired t-test of the mean within-unit difference. |
| `bootstrap` | Historical name: permutation test using absolute mean gap and independent-label exchangeability. | Within-pair sign-flip test using absolute mean difference and within-pair exchangeability. |
| `mannwhitney` | Two-sided rank test of distributions; not a general test of median equality. | Rejected; choose paired t or sign flips. |

T-tests need an appropriate sampling approximation (normal within-pair differences
for the classical paired t model); permutation tests require the selected
exchangeability model. These assumptions are disclosed, not automatically certified.
All records say `assumptions_verified: false`. A small p-value does not measure
effect importance, causality or reproducibility; a large p-value does not prove
equivalence. Distribution/interval estimation needs its own appropriate method.

Mean-difference tests require mean bars. Self/reversed/duplicate pairs, independent
`pair_by`, incompatible pairing/uncertainty units and separately drawn groups or
stacks pooled into one category test are errors. Use single-cohort filters or
facets instead. Mann-Whitney can accompany median bars if its distributional null
is described honestly. The existing `paired_difference` chart also directly shows
matched effects and their uncertainty.

## Correction and unavailable tests

Holm remains the default within each panel; optional Benjamini-Hochberg needs a
suitable dependence structure. Every distinct **planned** pair stays in the family.
If a category, finite pair or dependency is unavailable, its report is `untested`;
correction conservatively uses p=1 for that missing comparison. Reported raw p-values
remain actual test results, and missing tests make strict verification incomplete.
`family_size` and `tested_family_size` disclose both denominators. This does not
adjust an undisclosed family spanning other figures, endpoints or analyses.

Small permutation problems are enumerated exactly; larger problems use 2,000
seeded draws with the observed assignment included, giving nonzero randomized
p-values. This absolute-tail convention is explicit and may differ from another
tool's two-sided convention.

Mean statistics use matched differences (paired) or a shared origin (independent),
then a bounded positive working scale. This avoids losing representable small gaps
when observations share a very large offset, without changing drawn observations.
Rank tests retain original values. Differences that overflow the finite working
representation remain unavailable, so strict verification cannot certify a test.
Regression controls include the offset/scaled variants of a hand-enumerated case.

Sources: [SciPy independent t-test](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_ind.html),
[paired t-test](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_rel.html),
[Mann-Whitney](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.mannwhitneyu.html),
and [permutation types/counting](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html).
Numerical, matching, actual-artist and strict-CLI controls live in
`python/tests/test_comparison_design.py`; static refusals in
`test/comparison-design.test.ts`. These cover implementation behavior rather than
population coverage or validation of the experiment itself.
