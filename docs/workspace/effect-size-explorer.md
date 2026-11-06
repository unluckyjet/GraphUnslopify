# Compare observed effects and confidence intervals

Install the source package with the `statistics` extra. Open **Effect size
explorer** in either local workspace and choose a UTF-8 CSV. Select one
numeric outcome, a group column, and the study design. Add one or more
contrasts and choose the left and right group for each. Each estimate is
left minus right.

For paired data, select a stable unit column. The explorer uses complete
matched pairs and preserves distinct identifiers such as `01` and `1`.
For independent groups, select a unit column or explicitly declare that
each row is an independent unit. Choose a within-unit mean only when
several valid measurements represent the same unit and group.

The results compare effects on one scale at a time. **Mean difference**
uses outcome units. **Standardized mean difference** uses the SD of
within-pair differences, a pooled SD for the common-variance design, or
the root mean of the two variances for Welch. The display gives each
estimate and interval numerically and on a common axis with a zero line.

Student t intervals and noncentral t inversion apply under the declared
normal models for paired and pooled designs. The Welch intervals use
estimated degrees of freedom and are approximate. In small unequal groups,
the standardized interval can have coverage below its nominal level.
The displayed intervals are per contrast. [Effect size reference](https://easystats.github.io/effectsize/reference/cohens_d.html)
· [Cumming and Finch on noncentral intervals](https://doi.org/10.1177/0013164401614002)

Expand **Contributing and excluded CSV records** to trace each included
unit and exclusion. The source SHA-256 binds the selected CSV bytes. The
record numbers are one-based data ordinals after the header, with empty
lines ignored and quoted multiline records counted once. Blank group or
unit labels, missing or nonfinite measurements, and unmatched pairs are
reported by reason. The explorer reads the selected file locally and
leaves figure definitions and scientific verdicts intact.

```sh
graphunslopify effects observations.csv --design paired --group condition \
  --outcome response --unit participant --contrast treatment control \
  --confidence 0.95 --confirm-assumptions
```

Repeat `--contrast LEFT RIGHT` for up to twelve comparisons. Use
`--rows-are-units` for independent rows or `--reduction mean` with a unit
column after reviewing repeat measurements. The JSON reports intervals,
assumptions, methods, units and lineage. An unavailable estimate or
interval returns a partial report with exit 2.
