# Scaling fits: parameters, uncertainty and input domains

`scaling_fit` models `log10(y) = intercept + exponent * log10(x)` using least squares. Each
retained row is an observation; authors must choose appropriate independent units. The input
and every plotted cohort/panel need at least two observations with representable variation in
log x. Retained x/y must be numeric, finite and strictly positive. Missing/blank/nonfinite
series/panel labels fail before grouping. Explicit filters run first, and supported transforms
are validated again afterwards. Invalid rows are not silently clipped or omitted.

One centered estimator owns actual curves, parameter descriptions and per-series/panel runtime
evidence. Sorting observations before calculation makes results invariant to row permutations.
Predictions use the centered log model over the observed x range. Nonfinite parameters and
nonpositive/nonfinite fitted values fail explicitly, including numerical overflow/underflow.
This fit does not establish that the data follow a power law.

## Confidence and point-only fits

The default `interval: "t95"` uses a conditional two-sided 95% Student-t interval for the
exponent, with `n-2` residual degrees of freedom. This replaces the earlier unqualified `1.96*SE`
margin. The [SciPy linear-regression reference](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.linregress.html)
uses the same slope/standard-error and degrees-of-freedom construction. The conditional interval
assumes an appropriate log-linear model with independent, homoscedastic normal residuals.
Numerical agreement does not establish those assumptions or population coverage.

For log x `[0,1,2]` and log y `[0,1,3]`, the fitted exponent is `1.5`, intercept `-1/6`, slope
standard error `sqrt(1/12)` and residual standard error `sqrt(1/6)`. The conditional t95 margin
at df=1 is approximately `3.66796536`; the old normal margin was approximately `0.56580326`.
Slope SE and residual SE are different quantities. Descriptions and console output print the
conditional margin with significant digits so a small positive interval does not round into
two identical displayed endpoints. JSON also preserves actual lower/upper bounds and the margin.

Install the existing `[statistics]` extra for SciPy Student-t quantiles. Without it, the curve
and identifiable parameters remain available, requested confidence bounds stay unknown, and
strict verification is incomplete with an actionable dependency message. Rendering never
installs dependencies or contacts a service automatically.

Choose explicit `interval: "none"` for a point-only fit without SciPy. Two distinct points
identify the curve but have zero residual degrees of freedom: both standard errors remain
unknown, never zero. With t95 requested, the missing interval makes strict status incomplete;
with interval none, no interval is required and the lack of residual variance is still disclosed.
A singleton or constant log x cannot identify the two parameters and fails. Constant positive
responses can have exponent/estimated standard error zero; R-squared is undefined without
response variation. This differs from missing uncertainty due to absent degrees of freedom.

## Claims, labels and reports

Literal series claims refer to the observed values used in the fit when observed points are
enabled. They do not compare fitted endpoints, exponents or statistical significance. Raw-point
claims/semantic annotations are refused when `show_points: false`. Direct series labels attach
to actual fitted endpoints on every facet. Point-only series have named curve handles and
distinct line patterns. Continuous overlays retain their actual numeric x coordinates.
Temporal axes, ambiguous claim/annotation field roles and min-max normalization are refused;
normalization would create zero values outside the log model's domain.

Runtime `data.counts.scaling_fits` records the panel, series, metric, n/df, exponent/log-intercept,
both standard errors, centered log coordinates, nullable R-squared, constant-response flag and
interval method/level/status/critical/margin/bounds/reason. Descriptions use those fitted
quantities rather than the raw score mean. All interval bounds describe the exponent parameter,
not individual observations or a prediction band. Marginal intervals do not supply a simultaneous
multiple-model comparison or establish equivalence. PNG/SVG descriptions preserve the same narrative.

## Verification

`python/tests/test_scaling_references.py` compares independent hand and SciPy parameters,
conditional intervals, actual curve/data artists, permutations, domains, degenerate fits,
overflow, filtering/transforms, missing-SciPy/point-only cases, scoped reports, visible-observation
claims, labels, overlays and provenance. The initial focused contract failed 42 of 43 cases;
the already-correct observation-based claim behavior is retained. A narrow two-point log plot
also exposed off-screen minor ticks being treated as colliding text. Inspector regressions
exclude those undrawn labels while still detecting genuine visible minor-label collisions.

```sh
python -m pytest python/tests/test_scaling_references.py python/tests/test_inspect.py -q
```

Fresh-wheel checks exercise a genuine base environment without SciPy: a two-point point-only
curve passes, while a three-point requested t95 interval remains incomplete. Independent SciPy
references and full intervals run with `[statistics]`. The complete scientific reference matrix
for all 21 chart kinds remains separate work.
