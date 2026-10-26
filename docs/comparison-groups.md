# Comparison groups and table cells

Declaring `group` means separate series. Box, violin, raincloud, ridgeline,
forest, heatmap, confusion matrix and waterfall currently do not draw separate
series for that field. They now return `unsupported_grouping`, including groups
created by `series_from_columns`. Their generated `main()` also refuses execution.
Use facets for separate comparisons. Explicitly leave grouping unset when pooling
observations is intended; removing a group declaration changes the analysis.

Line, scatter, bar, ECDF, slope, dumbbell, calibration, Q-Q, Kaplan–Meier,
scaling fits, sparkline grids and tables retain their existing grouped behavior.
Paired differences retain their earlier group refusal: their pair and condition
fields define the matching. This boundary does not add grouped forest/distribution
features or establish that experimental units are independent.

Grouped table cells must have unique row/group keys **after the requested
aggregation**. `aggregation: "none"` cannot average duplicate cells implicitly:
values1 and9 previously became5 despite that request. Duplicate cells now fail
with a clear runtime error suggesting explicit mean/median/sum/count aggregation
or a unique row key. The runtime-error exit code is1. Unique raw grouped cells
and ungrouped raw rows retain their exact values.

A forest probe previously drew only center2 while dropping the declared second
group's center12. The53 independent controls in `test_group_projection.py` cover
eight raw/wide group refusals, direct main execution, explicit pooling, twelve
supported grouped kinds, known table estimators and unique raw cells. The corrected
initial39 controls measured25 failures/14 passes before the fix. Installed offline
checks also require the grouped refusal and duplicate-table runtime failure.
The full21-kind numerical/domain reference matrix remains separate.

Raw tables describe rows as identified by the row field, without promising a unique row per identifier. Two additional description controls verify raw and aggregated wording.
