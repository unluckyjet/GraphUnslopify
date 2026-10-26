# Match uncertainty to its estimator

`aggregation: "median"` with `uncertainty.kind: "sem"` is explicitly unsupported.
This tool's SEM calculation is sample standard deviation divided by the square
root of the observation count: a standard error of the **mean**, as defined by
[SciPy's SEM reference](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.sem.html).
Attaching it to a median does not estimate that median's standard error.

For observations1/2/9, the mean is4, the median2 and the mean's SEM is
`sqrt(19/3)`, approximately2.5166114784. Previously all four summary kinds
(line/bar/forest/table) placed that width around2 without an estimator warning.
They now return `median_sem_unsupported`; their generated summary also raises
if a caller bypasses translation findings. No center or interval method is
silently substituted. Missing-aggregation SEM guidance recommends a mean.

Mean summaries retain their SEM behavior. Choose an explicit percentile-bootstrap
CI for median uncertainty, or IQR to describe observational spread. IQR, standard
deviation and full range are not automatically confidence intervals. Bootstrap
coverage depends on the sampling design and method; selecting `over` identifies
the resampled units without proving they are independent.

The33 controls in `python/tests/test_sem_estimator.py` cover all four kinds,
raw/named-unit refusals, direct summaries/strict scripts, hand-known mean SEM,
median bootstrap endpoints and guidance. The initial32 controls measured16 failures/
16 existing positive passes. For three empirical unit values1/2/9, the tested
seeded95% bootstrap median interval retains endpoints1/9 and center2. The fresh
offline wheel checks both valid estimators and direct refusal of the mismatch.
Full21-kind numerical/domain reference coverage remains a separate matrix.
