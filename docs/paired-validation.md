# Paired differences: units, exclusions and reference evidence

`paired_difference` uses `pair` to identify the same unit under each condition in `x.field`.
For every alternative condition it subtracts the named baseline's `y.field` measurement within
that unit. Repeated finite measurements in one unit/condition are averaged first, so a unit with
more technical repeats does not receive extra weight in the mean difference or its interval.
The author remains responsible for choosing independent units and a meaningful comparison.
Use `y.label` for the source quantity (for example `Accuracy`); the rendered axis adds `Change in`
and converts a percent source unit to percentage points.

Unit, condition and panel identifiers must be present and nonmissing; blank strings and nonfinite
numeric identifiers fail. Explicit filters run first. Genuinely missing measurements are retained
for exclusion accounting. Nonmissing measurements must be numeric/finite, and overflow in derived
means, differences or intervals fails explicitly. Missing baseline, missing alternatives and no
complete pairs cannot produce a successfully verified empty figure.

Each comparison reports the panel's total observed units, matched pairs, baseline-only,
candidate-only and neither-condition units. The latter counts units present in the panel with no
finite measurement in either compared condition, including units measured only in another
condition. It also reports missing measurement rows and extra finite technical repeat rows for
the two relevant conditions. These are separate counts: a missing row and an excluded unit are
different things. The runtime JSON stores them under `data.counts.pairing`, with panel/metric,
condition/baseline, mean, interval and its method/level/resampling seed.

Every unit difference is plotted, alongside its mean and a 95% percentile bootstrap mean interval
using 2,000 resamples and the fixed seed 20260903. Tick labels display the number of matched pairs.
A singleton draws its difference with `n=1; CI unavailable`; interval bounds are unknown, not zero.
A comparison with no complete pairs remains visible with `n=0` when other comparisons have data.
Both make strict verification incomplete. Exclusions and averaged repeats produce warnings;
`--fail-on-warning` rejects those too. Bootstrap intervals do not prove normality, equivalence,
significance or correct experimental design, especially with very few independent units.

Descriptions use these same paired quantities and disclose exclusions. For units A=(10,14) and
B=(20,26), the differences are `[4,6]`, mean `5` and the seeded percentile interval `[4,6]`.
An extra baseline-only score 100 and candidate-only score 1000 do not change that result; both
excluded units are disclosed. Describing the mean of all raw scores would be misleading.

Numeric condition labels can match a baseline by their unique string representation (integer 0
matches baseline `"0"`). Ambiguous representations such as distinct integer 0 and string `"0"`
in a JSON table fail instead of merging. Estimation leaves the author's rows unchanged. Global
CSV type inference can still lose leading-zero identifiers; preserving those identities is a
separate open reference-matrix requirement. Do not assume this focused work resolves it.

Raw series grouping/claims, raw-y transforms and overlays are refused explicitly for this kind.
They would otherwise describe or test source scores while the base marks show differences.
Log y is also refused because it cannot represent zero/negative differences; use linear or symlog.
There is no automatic paired significance test or multiplicity correction on these intervals.

`python/tests/test_paired_references.py` checks independent hand differences/interval endpoints,
actual Matplotlib points/centers/tick counts, permutations, repeats, missing/unmatched units,
invalid inputs, overflow, singleton/empty comparisons, filter order, baseline identity,
panel-scoped runtime reports and PNG/SVG provenance. The initial focused contract failed all
27 cases on the preceding implementation. Run it with:

```sh
python -m pytest python/tests/test_paired_references.py -q
```

A skewed five-unit fixture with differences `[1,2,4,8,16]` also compares actual interval artists
against [SciPy's percentile bootstrap](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html)
using the same declared seed/resample count. With the measured SciPy 1.18.1 stack it gives mean
`6.2` and bounds `[2.0,11.6]`. This optional oracle needs `[statistics]`; hand cases and base
rendering do not require SciPy. Matching this method is not a claim of nominal population coverage.

Fresh-wheel installation checks also render the six-row example offline from the installed CLI.
This verifies the stated matched-unit contract, not the complete scientific chart inventory.
