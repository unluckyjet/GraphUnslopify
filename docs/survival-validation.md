# Right-censored survival: contract and reference evidence

`kaplan_meier` computes the product-limit estimate from `x.field` (numeric follow-up duration) and
`event` (1 for observed event, 0 for right-censored). Each retained row is one follow-up record.
The estimate assumes the study's records and censoring mechanism are appropriate for Kaplan–Meier;
the tool cannot establish independence or noninformative censoring from these columns. Left or
interval censoring and delayed entry are not represented by this schema. The curve is a point
estimate; this kind currently supplies no confidence intervals or log-rank comparison.

At each distinct time, all events use the risk set immediately before that time. Tied censors
leave afterwards. For durations `[1,1,2]`, with one event and one censor at time 1 and an event at
time 2, the estimate is `1 × (1−1/3) = 2/3` at time 1 and zero at time 2. Reordering those rows must
not change it. The curve begins at zero and extends through the last observed follow-up, including
censor-only tails. A marker at a tied event/censor time uses the post-event survival estimate.

Missing/nonfinite/negative duration, missing/nonbinary event indicators and missing cohort/panel
labels fail before plotting. Event values are not rounded or thresholded. A user-specified filter
runs first; the report retains the read/retained row counts. Empty retained datasets cannot become
verified empty curves.

`y.field` names the derived output for metadata and claims; it need not exist in the source file.
Descriptions report cohort observations/events/right-censors, estimated survival at the last
observed follow-up, and median survival when reached. Median means the first observed time at or below 50%, with
relative tolerance 1e-12 at that boundary to absorb floating-point roundoff. An unreached median
is explicitly unknown.
They do not substitute the mean of an event flag or a supplied placeholder y column.

Claims compare these right-continuous point estimates on the union of observed cohort times plus
zero. They are literal numeric predicates, not inferential superiority or equivalence tests and
not time-integrated areas. Beyond a cohort's own follow-up its estimate is unknown for comparisons;
required missing coverage gives UNTESTED rather than extrapolation. Raw-y transforms are not defined
for this estimator, and claim time/output/cohort roles must have distinct column names.

## Independent checks

`python/tests/test_survival_references.py` compares actual Matplotlib step values and every censor
mark with [SciPy's right-censored ECDF/SF](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ecdf.html).
It includes the hand-calculated tied example, repeated events/censors, event time zero, all-event
and all-censor cohorts, censor-only tails and the published SciPy fanbelt example. It also checks
all row permutations of the small tied cohort, input-domain failures, missing labels, filtered
inputs, raw-y false-claim controls, short-follow-up unknowns, panel-scoped claims, strict exits and
PNG/SVG provenance matching computed descriptions.

```sh
python -m pip install -e './python[dev,statistics]'
python -m pytest python/tests/test_survival_references.py -q
```

The statistics extra supplies SciPy 1.11+ for the independent oracle; the emitted Kaplan–Meier
implementation itself only needs the base NumPy/pandas/Matplotlib runtime. Both Python 3.10/3.12 CI
jobs install the oracle. This evidence covers this stated estimator/input contract; it does not
establish correct study design or validate every scientific chart kind.
