# Plan power for a mean difference

Install the source package with the `statistics` extra. Open **Statistical
power assistant** in either local workspace. Choose a study design, planned
unit counts, significance level and direction. Then calculate power for a
signed difference or find the smallest difference that reaches a target
power in the chosen direction. For a two-sided test the detectable difference
is returned as a positive magnitude.

| Design | What to supply |
| --- | --- |
| One sample | Independent unit count and, for outcome units, a planning outcome SD |
| Matched pairs | Count of independent complete pairs and, for outcome units, the SD of the within-pair differences |
| Independent groups, common variance | The two independent unit counts and, for outcome units, a common planning SD |
| Independent groups, Welch | The two independent unit counts and both planning SDs in the same outcome units |

Choose the order of subtraction before specifying a direction. Enter a
standardized difference in SD units or enter an outcome-unit difference with
the appropriate SD. Welch uses outcome units so each group retains its own
variance. Alpha and target power are fractions such as 0.05 and 0.8.

```sh
graphunslopify power --design paired --n 24 --alternative greater \
  --alpha 0.05 --sd 0.25 --effect 0.08 --confirm-assumptions

graphunslopify power --design welch --n 8 --n-other 16 --alternative two_sided \
  --alpha 0.05 --sd 0.3333333333333333 --sd-other 1 \
  --target-power 0.8 --confirm-assumptions
```

The CLI returns the supplied inputs, method, result and assumptions as JSON.
The same calculation is available as
`graphunslopify.statistical_power.plan_power(payload)`. For the payload use
`calculation: "power"` with `effect`, or `calculation: "detectable_effect"`
with `target_power`. Set `assumptions_confirmed: true` after choosing the
design. Other field names match the CLI with underscores.

This is prospective planning for one fixed-sample test under the stated normal
model. The assistant uses the values you supply and does not read the paper's
data, figure settings, observed p-values, or test results. Counts refer to
planned independent units or complete pairs, as appropriate. Clustered,
sequential, equivalence and multiple-testing designs need separate models.

One-sample, matched-pair and pooled-variance power use noncentral t
rejection probabilities. The two-sided calculation counts both tails.
Welch uses the beta-mixture calculation of the test's rejection probability
under two independent normal groups. It reports the model's rejection
probability at zero effect alongside nominal alpha. If consecutive integration
grids fail the numerical agreement check, the assistant reports that it
could not calculate the result. [SciPy noncentral t reference](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.nct.html)
· [Jan and Shieh, 2011](https://doi.org/10.3758/s13428-011-0095-7)
· [Published R power examples](https://stat.ethz.ch/CRAN/web/packages/pwr/vignettes/pwr-vignette.html)
