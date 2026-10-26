---
id: 31
slug: category-identity-contract
status: ready
priority: P0
title: Preserve identifier spelling and align categorical roles without changing raw filters
source_idea: independent reference matrix 24 confirms CSV identity loss and empty explicit category orders
---

# Category and identifier identity contract

Measured at b532a6e using actual emitted programs and artists:

- CSV group values `01` and `1` are both inferred as integer 1. Four observations intended
  for two series draw one line with x `[1,1,2,2]` and y `[10,20,12,22]`.
- Numeric groups 1/2 ignore explicit string series order `["2","1"]`; a valid claim with
  subject `"2"`, reference `"1"` is UNTESTED because the named columns do not match.
- A bar with numeric category values 1/2 and explicit category order `["2","1"]` has no
  categories and draws no bars. Treating a rendered empty frame as success is insufficient.
- Existing raw numeric filter `model eq 1` selects all four inferred rows in the `01`/`1`
  example. Preserve raw author-filter semantics rather than globally changing CSV dtype.

## Contract

Preserve lexical CSV identifiers for declared semantic identity roles: series, facets, paired
units, repeat units and categorical axes/row keys. Distinct identifiers such as `01` and `1`
must not merge. Align actual names with string-valued ordering, emphasis, palette locks,
baselines, claims, annotations, tables and label/report evidence. Apply an explicit consistent
identity representation for supported typed JSON/Parquet and direct DataFrame inputs too;
keep missing identifiers missing rather than turning them into a plausible `nan` series.

Filters run on the original typed input before identity adaptation. Numeric measurements,
continuous/temporal coordinates and their filter semantics must retain their meanings. Record
and test which representation is filtered; do not use global dtype=str or silently coerce
measurement roles. Wide reshaping, sorting/filtering, facets and unit grouping must retain
row-to-identifier correspondence. If a column has incompatible semantic roles, preserve
separate meanings when supported or refuse the combination explicitly before drawing.

Use a shared boundary adapter rather than unrelated string casts in every mark emitter.
Different identifiers must remain distinct in the actual marks, pairing/unit counts, series
order, comparisons, descriptions and exported evidence. Unsupported/empty selections must
not masquerade as a verified meaningful plot.

## Acceptance evidence

Independent synthetic actual-artist and runtime controls cover leading-zero categories,
groups/facets, paired/repeated units, numeric series/category order, emphasis/claims/baselines,
heatmap/confusion/table labels, wide reshaping and representative typed inputs. Assert
precise values and counts, not just source strings or nonempty output files. Include numeric
range/membership/equality and string filter preservation, missing/invalid identifiers,
temporal/continuous measurement preservation and conflicting-role controls.

Refresh affected baselines/public image fingerprints only with verified intended changes.
Run the seven required gates, gallery checks and fresh offline wheel smoke; visually inspect
representative outputs, update Obsidian and inspect both GitHub workflows after the small push.
The broader per-kind/domain/overlay/final-export-width reference matrix 24 remains open.
