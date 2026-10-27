---
id: 44
slug: apply-numeric-measurement-views
status: done
priority: P0
title: Apply parsed numeric measurements before sorting aggregation and plotting
source_idea: release preflight Parquet x strings1/2/10 become category positions0/1/2 ordered1/10/2 and strict passes
---

# Apply numeric measurement roles

Measured real Parquet inputs at3c8f35a: numeric strings1/2/10 become Matplotlib categorical
positions0/1/2 in lexical order1/10/2. The actual strict CLI reports passed/checked with no
errors or untested checks. The numeric-domain validator parses a numeric series but discards
it; callers continue to aggregate/sort/plot the original strings. String sums can concatenate.

After raw typed filters and lexical identifier normalization, use parsed numeric views for
numeric roles. Preserve label/unit/group/category spelling and existing mean/median finite
cleanup policy. Avoid unnecessary integer precision loss; missing extension values must remain
real missing measurements rather than plotting categories or invalid scalar objects.

Measure actual plots/aggregates for numeric strings, nonuniform/reordered x, typed filters,
lexical IDs, missing numeric extension values and real Parquet strict execution. Run all seven
checks/gallery/fresh installed proof, update only affected source/provenance, refresh Obsidian
and check both workflows before the versioned release.

## Verified implementation (2026-10-26)

Parsed numeric series now feed numeric fields after raw typed filters/identifier normalization.
Nullable extension missing values use actual NaN objects for native plotting; original exact
integer aggregation is preserved. Existing mean/median finite cleanup and lexical IDs remain.

11 independent controls all failed before; all now pass on pandas3.1/2.3.3: actual line/scatter/
sparkline nonuniform coordinates, bar/table integer sums beyond2**53, waterfall/heatmap sums,
raw string filters/lexical01 IDs, nullable strings and real Parquet load/strict export. Corrected
actual coordinates are1/2/10 in numeric order with true spacing; strict reports passed/checked.

Seven gates215 Node/956 Python, zero local skips/warnings; Ruff54/gallery15/15 and clean offline
wheel/agent pass. Installed actual coordinates, numeric string sums and lexical IDs are checked
independently. Bundle matches source. All52 published PNG pixels/dimensions are unchanged after
baseline and affected reference provenance refresh. Corrected probe visually reviewed, canonical
Obsidian notes updated,98 notes/0 unresolved links. Both workflows require verification after
push. Versioned/tagged release and final requirement audit remain active.
