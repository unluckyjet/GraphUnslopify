# Calibration: contract and reference evidence

`calibration` treats `x.field` as the probability of the event represented by `outcome == 1`.
Retained probabilities must be finite within `[0,1]` and outcomes must be binary `0` or `1`.
Missing model/panel labels and empty input fail explicitly. Invalid rows are not clipped, rounded
or silently discarded. Intentional author filters run before these domain checks.

The plotted x coordinate is the mean predicted probability in each occupied bin; y is its observed
event frequency. Uniform bins use right-closed interior boundaries, with zero in the first bin and
one in the last. An exact interior-boundary probability belongs to the lower bin. Older builds put
such values in the upper bin; figures containing boundary values can therefore change. Empty bins
are omitted and their occupancy is disclosed, not represented as zero-frequency observations.

Empirical expected calibration error is `sum(n_b/N * abs(rate_b - mean_probability_b))`. It depends
on the chosen bins and sample, and is not a per-observation absolute error or an inferential claim
about the population. For `[.1,.2,.6,.9]` with outcomes `[0,1,1,0]` and three bins, plotted means are
`[.15,.6,.9]`, frequencies `[.5,1,0]`, counts `[2,1,1]` and ECE `0.5`. The same calculation owns the
marks, ECE, descriptions and claim inputs. Small positive ECE values retain significant digits
rather than displaying a misleading zero. Confidence intervals are not supplied by this kind.

`y.field` names the derived frequency output and need not exist in the source file. Descriptions
report sample observations, occupied/requested bins, ECE and the plotted probability/frequency
ranges. They do not substitute a raw probability median or a supplied placeholder y column.
Grouped facets have a separate legend per panel: an ECE from one panel must not label another.
Direct series labels use the derived curve endpoints and include that model's own ECE.

Claims remain literal comparisons of plotted frequencies, not tests of calibration quality or
statistical superiority. Being higher than another model's curve does not by itself mean closer to
the calibration diagonal. Different plotted mean-probability positions are not interpolated or
replaced with fixed bin centers. Within the same bin, differences of at most `1e-12` from floating
summation are aligned deterministically for comparisons; actual points and ECE stay unmodified.
Missing required coverage gives UNTESTED. Raw-y transforms and ambiguous probability/output/series
field roles are refused explicitly.

## Evidence

`python/tests/test_calibration_references.py` checks actual Matplotlib points, counts and ECE against
independent hand answers. It covers endpoints and exact boundaries, empty bins, row permutations,
tiny positive error, domain/label/empty guards, intentional filtering, absent/raw y columns,
positive/false/unknown/scoped comparisons, floating alignment and PNG/SVG metadata. The original
focused suite failed 22 of 23 cases under this contract. A roundoff control also exposed false
UNTESTED results for the same probabilities reordered within a bin; that has a regression case.
Actual figure/annotation checks cover panel-specific ECE legends and derived direct labels.

A separate measured probe compares boundary-case points with
[scikit-learn's uniform calibration curve](https://scikit-learn.org/stable/modules/generated/sklearn.calibration.calibration_curve.html):
inputs `[0,.25,.5,.75,1]` produce mean probabilities `[.125,.5,.75,1]` and frequencies `[.5,0,1,1]`.
The hand ECE is `0.3`. Automated hand cases require no scikit-learn dependency; the external probe
was recorded separately with scikit-learn 1.9.1. Base rendering uses NumPy/pandas/Matplotlib.

```sh
python -m pytest python/tests/test_calibration_references.py -q
```

These cases verify the stated empirical binning contract, not experimental design or the complete
scientific chart inventory. See [survival references](survival-validation.md) for a separately
validated derived estimator.
