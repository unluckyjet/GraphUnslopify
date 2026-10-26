---
id: 38
slug: preserve-comparison-groups
status: done
priority: P0
title: Refuse unused comparison groups and implicit averaging in unaggregated table cells
source_idea: matrix24 forest draws center2 and drops12 for declared groups while table none averages1and9to5
---

# Preserve declared comparison groups

Measured atdba728a: a forest declaring method groups first/second with centers2/12 draws only2.
The generic group field is unused by several drawing paths. Another probe requests table
aggregation none for duplicate category/method cells1/9 and receives5 from pivot_table's mean.
Do not certify omitted or silently pooled comparisons. Explicitly refuse group declarations
(including virtual groups from wide reshaping) on kinds whose drawing does not separate them.
Keep supported grouped kinds working. Direct generated main must not quietly run a refused
projection. Grouped table cells must be unique after the requested aggregation; explain how
to choose aggregation or a unique row key rather than inventing an implicit mean.

Verify raw/wide semantic refusals, direct execution, known grouped table aggregations and
unique raw cells. Preserve explicit pooling through requested aggregation or an unset group.
Run seven gates, gallery, installed proof, refresh affected public provenance, Obsidian and
both workflows. Complete per-kind scientific matrix24 remains open.

## Verified implementation (2026-10-26)

A shared capability refuses unused grouping on eight kinds, including effective wide-derived
groups, with semantic unsupported_grouping and a direct-main hard refusal. Twelve implemented
grouped kinds remain accepted; paired differences retain their prior separate refusal.
Grouped tables check post-aggregation cell uniqueness rather than silently averaging raw
cell duplicates. Mean/median/sum/count and unique grouped/ungrouped raw cells have independent
known-answer controls.53 cases pass; corrected initial39 measured25 failures/14 passes.

Seven gates215 Node/706 Python, zero skips/warnings, gallery15/15, Ruff and a fresh offline
installed wheel/agent pass. The installed raw-table negative control fails with runtime_error,
status failed/exit1; exit2 is reserved for policy rejection. Installed grouped forest conversion
and direct main also refuse the unused projection. An older unsupported-output Node fixture
now explicitly leaves group unset so it still tests the independent HTML-skip behavior.
The public table's source/provenance is refreshed from committed LF inputs; all20 tracked
baseline/public PNG pixels/dimensions remain identical and all baseline assets are unchanged.
Both workflows require verification after push; complete matrix24 remains open.

Raw tables describe rows as identified by the row field, without promising a unique row per identifier. Two additional description controls verify raw and aggregated wording.
