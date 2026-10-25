---
id: 16
slug: honor-composition-contracts
status: done
priority: P0
title: Render declared grid, repeat and reshape semantics without ignored options
source_idea: accepted trustworthy-figure and integration roadmap
---

# Honor composition contracts

Nested facets now draw a row-major grid using both keys, preserve empty cells
as visible No data panels, and mark those cells incomplete. Point/unit counts
keep both keys separate. The declared column limit is checked against data.
Repeat uses its actual sharing flags. Wide measurements create the grouping
column used by drawing/statistics, while metadata preserves the original valid
reshape declaration for round trips. Raw/prepared field references are validated
at the appropriate stage. Layer filters use the current subset.

Unsupported table/cut/panel/metric combinations and incomplete bands/rules now
produce explicit errors. A requested x cut cannot silently become a y cut.
Missing plotting keys are counted and disclosed. No repair silently removes
meaningful composition or data.

## Verification

Seven runtime/semantic regressions exercise 2x2 grid geometry and values, separate
n, missing cells, sharing flags, two actual wide-derived series with known means
and held claims, round trips, sequential filters, and invalid field/composition
contracts. The existing nested smoke fixture actually has three column levels;
it now renders and checks its full 2x3 grid, including the missing val/Bimodal cell.
Eight gates pass: 211 Node / 89 Python, 15 matching scripts, 16 PNG/PDF renders,
25 recipes, 7 composition cases and 15 strict gallery figures. Gallery pixels
are unchanged. GitHub CI is checked after pushing.
