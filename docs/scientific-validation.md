# Scientific reference matrix

All 21 figure kinds have independent numerical or observation-level references. This is
implementation evidence for the declared computations and tested domains. It does not establish
that an experiment is sound, that units are independent, that a fitted model is appropriate,
or that a bootstrap interval has nominal population coverage. It is not an exhaustive
cross-product of styling, transformation, composition and export options.

`python/tests/test_core_plot_references.py` contributes 108 controls for the fifteen ordinary
presentations below, including actual artists, descriptions, missing/invalid inputs, both
pandas 2.3/3.1 categorical behavior, real strict exports and the public sparkline fingerprint.
The six specialized estimator suites provide their separate known-answer/domain evidence.
Shared uncertainty, identity, grouping, appearance, composition, exported-width and contrast
suites exercise contracts that cross these rows.

| Kind | Independent reference and actual output | Domain/accounting controls |
| --- | --- | --- |
| line | Observations1/3 give mean2;5/9 give7, with a missing middle value remaining a NaN gap. `test_interactive.py` also compares static/HTML summary intervals. | Raw numeric inputs, finite-value summary policy, missing gaps, named units and unknown strict exports. |
| scatter | Actual retained x/y pairs match supplied observations, including duplicate x values. Missing pairs stay masked. | Numeric axes and invalid raw measurements; existing frontier/trend tests remain separate. |
| bar |1/2/9 give mean4, median2, sum12 and count3 in actual bar heights. | Signed/oriented/shared bars, true endpoints, clipped stems, stacked unknowns and explicit unsupported uncertainty; `test_bar_intervals.py`, `test_signed_bars.py`. |
| box |1/2/3/4/100 give Q1=2, median3, Q3=4, whiskers1/4 and outlier100 in actual artists. | Missing measurements, numeric domain, singleton/constant point masses and categorical grouping restrictions. |
| violin | Actual polygon widths match independent SciPy Gaussian KDE with Scott bandwidth, rescaled to the declared width. | Singleton/constant values retain a visible empirical point mass without invented spread. Numeric domain/group restrictions apply. |
| ecdf | Ties1/1/3 give steps0,1/3,2/3,1; complements and singleton5 have exact endpoints and vertical jumps. | X measurements are counted; missing values are excluded from the denominator, invalid raw values fail, all-unknown strict output cannot pass. |
| raincloud | Independent Scott KDE checks the half polygon; actual rain points and quartile/median components retain input values. | Small/constant samples and invalid numeric inputs; unsupported groups are explicitly refused. |
| ridgeline | Hand Gaussian density, bandwidth, affine/scaled profiles and independent SciPy reference. `test_density_references.py`; [density contract](density-validation.md). | Unavailable automatic bandwidth retains observations and remains untested; no finite observations or unrepresentable domain fails. |
| forest | A mean20 with IQR0/0 stays a dot20 plus detached endpoints0/0, without reflection. Shared SEM/bootstrap references check other quantities. | Named units, unknown intervals, categorical row mapping and unused-group refusal. |
| paired_difference | Hand/SciPy matched differences, unit repeats, means and bootstrap endpoints in actual artists. `test_paired_references.py`; [paired contract](paired-validation.md). | Missing/unmatched/repeated units, invalid domains, scoped counts and explicit unavailable intervals. |
| slope | Actual means2/9 remain separated by a missing middle-condition NaN, while another series retains its own middle point. | Category/series identity, observed missingness and numeric-domain checks. |
| dumbbell | Actual group means2/7 and the connector span match inputs; a missing group produces no invented dot. | Requested value/category sorting controls actual rows; missing groups and later legend handles remain distinguishable. |
| calibration | Hand bin boundaries, empirical ECE, known frequencies and independent oracle comparisons. `test_calibration_references.py`; [calibration contract](calibration-validation.md). | Probability/outcome domains, empty samples, scoped labels/counts, descriptions and claims. |
| qq | Hand/SciPy normal/uniform quantiles and population-quartile reference lines. `test_qq_references.py`; [Q–Q contract](qq-validation.md). | Small/empty/invalid samples, invalid reference domains, scoped descriptions/claims and actual curves. |
| kaplan_meier | Hand/SciPy product-limit curves, tied risk sets, censor marks, median and tail boundaries. `test_survival_references.py`; [survival contract](survival-validation.md). | Event/time domains, empty cohorts, censoring, follow-up limitations, scoped descriptions/claims. |
| scaling_fit | Hand/SciPy log-space coefficients, actual fitted curves and conditional Student-t intervals. `test_scaling_references.py`; [scaling contract](scaling-validation.md). | Positive finite log domains, identifiability, two-point estimates, unknown/unrequested intervals and scoped records. |
| confusion_matrix | Counts[[3,1],[2,4]], row/column normalization and diagonal7/10 are checked against actual image arrays/descriptions. | Integer nonnegative finite precomputed counts, sparse labels and zero totals; existing invalid-count and contrast suites. |
| waterfall | Start10, summed contributions+5/-1 and prefixes10/15/14 produce actual bars and final total14 in descriptions. | Unknown observed contributions and nonfinite totals fail; raw-row means are not substituted for displayed steps. |
| sparkline_grid | Actual child x/y values, shared horizontal/vertical limits, requested scales/limits and facet sharing are checked. | Ordinary numeric/temporal roles; explicit sharing flags work across actual full-workflow panels. Visible metric/unit labels remain present. |
| heatmap | Hand mean/median/sum/count cells, sparse masks and unknown sums match actual image arrays. | Actual observed categories, numeric values, unknown-versus-zero cells and shared static/HTML/description matrix. |
| table | Hand mean/median/sum/count values reach cells; unknown sums stay unavailable while observed zero stays0. | Duplicate raw cells fail, all-missing observed rows remain present, literal compiled text/percent/interval formatting and unsupported axes are tested separately. |

## Input and presentation contracts

Ordinary raw numeric plots require finite numeric measurements or missing values after author
filters and reshape. Invalid nonmissing strings/infinities fail clearly before drawing. Temporal
x uses the declared date pipeline; categorical identifiers retain lexical names. Mean/median
summaries retain the existing finite-value exclusion policy and disclose excluded counts/unit
sizes. They do not silently change the requested estimator. Six specialized estimators keep
their own stricter domain/availability contracts linked above; confusion counts retain their
integer-count contract. Numerical references use explicit finite domains rather than claiming
to validate every possible optional scale/transform combination.

Numeric roles use the parsed numeric series for sorting, aggregation and plotting, including
numbers stored as text in Parquet. Validation alone cannot prevent a plotting library from
interpreting the original strings as category labels. Raw typed filters still run first;
lexical identifiers are separate. Missing numeric extension values use a NumPy-missing view,
without needlessly converting exact integer sums to floating point. Eleven additional controls
in `test_numeric_measurement_views.py` check actual coordinates, string sums, nullable inputs,
identifier/filter behavior and a real Parquet strict workflow. They pass on both pandas versions.

A sum over observed-but-entirely-missing measurements is unknown, not0. Count retains its
meaning as the number of nonmissing measurements. Stacked mean/raw bars need known contributions
for each observed category and series; an absent mean cannot become a zero segment. Entirely
reserved category slots can remain empty. Sum/count stacks retain empty-cell additive/count
zero semantics, but an observed unknown sum is refused. Unused pandas categorical levels are
not observations: groupby/pivots explicitly use `observed=True`, independent of library defaults.
Explicit shared `category_order` slots are a separate presentation contract.

One waterfall estimate owns step sums, cumulative totals and descriptions. One heatmap matrix
owns static/HTML cells and descriptions. Sparkline child axes share the actual parent axes, so
scale/limit changes and requested facet sharing reach every cell; tickless presentation keeps
axis names/units visible. Dumbbell sorting follows the requested value/category order.

The [public sparkline example](sparkline-shared-scales.png) uses four synthetic observations
from committed `examples/references/sparklines.csv`/`.figure.json`. Its short and long segments
have identical unit slopes and use the same scale. The published image's data and source hashes
are checked. See [public fixture instructions](../examples/references/README.md) for all seven
reproducible reference illustrations. Existing 51 published PNGs retain identical decoded pixels
and dimensions after source/provenance refresh; the sparkline is an additional illustration.

## Reproduce the evidence

```sh
python -m pytest python/tests/test_core_plot_references.py -q
python -m pytest python/tests/test_survival_references.py python/tests/test_calibration_references.py python/tests/test_paired_references.py python/tests/test_qq_references.py python/tests/test_scaling_references.py python/tests/test_density_references.py -q
npm test
npm run test:python
```

CI runs the complete suites on Python 3.10/3.12 and installed-wheel smoke on Linux/macOS/Windows,
with external connections blocked after installation. Render CI requires real LaTeX cases and
actual browser checks. Passing source assertions or file existence alone is not the numerical
reference; the tests read values, artist coordinates, metadata, reports or compiled text.

The violin/raincloud oracle is [SciPy's independent Gaussian KDE](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.gaussian_kde.html),
using its explicit Scott factor and covariance scaling. This is distinct from the ridgeline's
robust bandwidth. Native component contracts are documented by [Matplotlib violinplot](https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.violinplot.html)
and [boxplot](https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.boxplot.html); fixed
hand quartiles/outliers and independent SciPy evaluation are asserted against the actual output.


## Cross-feature integration evidence

Current source adds a [34-case interaction matrix](interaction-validation.md) across
representative charts, named-unit aggregation/uncertainty, missingness, composition,
strict policies and actual PNG/SVG/PDF/HTML artifacts. These combined controls extend
the per-kind references; their explicit exclusions remain part of the contract.
