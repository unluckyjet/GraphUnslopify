# Q–Q plots: quantiles, reference lines and sample evidence

`qq` sorts finite observations in `y.field` and plots them against the specified reference
distribution. `x.field` names a derived output and need not exist in the input. Standard normal
and standard uniform references are supported. Each series/panel needs at least two finite
observations; a singleton cannot produce a successfully verified empty plot.

Plotting positions are explicitly Blom's `(rank - 0.375)/(n + 0.25)`. Normal coordinates use
Python's [NormalDist inverse CDF](https://docs.python.org/3/library/statistics.html#statistics.NormalDist.inv_cdf),
without clipping tails or requiring SciPy for rendering. Uniform coordinates equal the plotting
probabilities. Sample quartiles use NumPy's linear percentile convention. The reference line maps
the reference distribution's population quartiles at probabilities `.25/.75` to the observed
sample quartiles. This follows the population-quartile construction shown in
[statsmodels' quartile reference line](https://www.statsmodels.org/stable/_modules/statsmodels/graphics/gofplots.html#qqline).
It replaces the previous finite-grid-quartile line, which depended on the plotting grid size.

For observed `[1,2,3,4]` against uniform, positions are `[5,13,21,29]/34`, sample quartiles are
`1.75/3.25`, and the reference line is `y = 1 + 3x`. Constant samples remain plotted with a warning
that distribution shape cannot be assessed. The reference line estimates a location/scale
relationship; following it does not establish normality or distributional equivalence.

Missing measurements are omitted with per-series/panel counts. Nonmissing measurements must be
numeric and finite. Missing/blank/nonfinite series/panel labels fail before grouping can discard
them. Explicit author filters run first. Nonfinite derived quartiles/lines and invalid log domains
fail rather than hide points or parts of the reference. Valid nonlinear axes sample the reference
curve with 100 vertices. Normal theoretical quantiles cannot use log x because they include
nonpositive values. Uniform log x and compatible log y remain supported.

The plot, descriptions, direct labels, semantic annotations and claims share the same estimator.
Descriptions disclose observations/missingness, sample quartiles, distribution, plotting positions
and reference coefficients. Runtime JSON adds `data.counts.qq` records with the panel, series,
metric and those quantities. PNG/SVG descriptions preserve the same narrative.

Literal claims compare observed quantiles at identical theoretical coordinates. Different sample
sizes generally have different grids and produce UNTESTED without interpolation. These predicates
do not test distributional fit, statistical superiority or study design. Raw x columns cannot
change claim results. Crossover annotations also require complete shared coverage; an annotation
that cannot be located is reported as unavailable and makes strict verification incomplete.
Direct labels are placed separately on every facet using actual quantile endpoints.

Per-series `normalize` is supported before quantiles, across the prepared data before faceting.
It is disclosed as a unitless observed range, and the y label drops the original physical unit.
Numeric strings are converted before normalization; missing rows stay missing. Cumulative and
baseline transforms requiring a raw x coordinate, raw overlays, temporal x and ambiguous derived
claim/annotation field roles are refused explicitly. Preprocess source observations when other
transformations are needed.

## Verification

`python/tests/test_qq_references.py` checks actual marks and reference lines against independent
hand uniform answers and SciPy normal inverse-CDF values at the declared positions. It covers
sample sizes 2..10,000, probabilities down to `1e-14`/up to `1-1e-14`, row permutations, missing and
invalid samples, constants, filtering, normalization, true/false/unknown/scoped claims, labels,
annotations, scale domains and PNG/SVG provenance. The initial 37-case contract failed all cases.
The 10,000-point maximum normal-coordinate error changed from `0.0072563687` to
`1.7763568394e-15` in the measured Python 3.12/SciPy 1.18.1 environment.

```sh
python -m pytest python/tests/test_qq_references.py -q
```

SciPy is an optional test oracle through `[statistics]`; base rendering and hand cases need no
SciPy. Fresh-wheel smoke checks render from observations without a raw x column, with external
connections blocked after installation. These checks verify the stated numerical contract;
they do not certify normality, independence, sample representativeness or all 21 chart kinds.

The README illustration now uses a committed [spec](../examples/references/qq.figure.json) and
[160-row synthetic dataset](../examples/references/qq.csv). A regression checks the published PNG's
data/source fingerprints against that dataset and the current canonical emitter. Reproduce its
data/spec with `graphunslopify render examples/references/qq.figure.json --out-dir figures --strict`.
