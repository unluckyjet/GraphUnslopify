---
id: 33
slug: category-overlay-coordinates
status: done
priority: P0
title: Align overlay marks with plotted categories and refuse undefined coordinate systems
source_idea: matrix24 actual-artist probe shows overlays shifted across custom category orders
---

# Category overlay coordinates

Measured at4c1a8df: a bar with input categories01/1/B, values1/2/3 and category_orderB/01/1
draws bars at0/1/2 with heights3/1/2. A line overlay with reference10/20/30 draws at0/1/2
instead of the corresponding1/2/0. Matplotlib independently installs a string-category
converter for the overlay while the base chart owns numeric positions. Rendering succeeds.

For supported vertical category axes (bar/box/violin/raincloud/slope), map raw overlay rows
to the base panel's actual category positions. Preserve lexical IDs, custom/encounter order,
filtered subsets, grouping, stable row alignment and facets. Line/scatter/rug/band marks
must land over the correct categories without mutating user data. Define raw-row semantics
explicitly; do not silently aggregate or discard unknown categories. Horizontal value axes,
derived comparison/matrix/inset coordinate systems and other undefined combinations must
fail explicitly until their meaning is supported. Rules retain their declared horizontal
numeric-y meaning on supported axes and need no raw x column.

Independent tests must inspect actual converted artists and known x/y associations, including
reordered01/1 names, filtered rug/point subsets, band bounds, grouped/faceted panels,
continuous-coordinate controls and unsupported combinations. Review actual exported examples.
Run required seven gates, strict gallery and installed-wheel proof; refresh only affected
artifacts/provenance, update Obsidian and inspect both GitHub workflows. Parent24 stays open.

## Verified implementation

Supported vertical categorical overlays now map through the base formatter, preserve stable
row/value associations after filters, and reject unknown/ambiguous categories. Shared categorical
overlay workflows establish one full-data order before panels and retain missing local positions;
hidden tick artists do not erase the mapping. Rules do not read an unused raw x field. A shared
capability boundary refuses undefined coordinates both semantically and in generated runtime.

44 independent artist/runtime/refusal tests pass, including actual main shared facets/repeats.
The corrected initial36 controls failed35/passed1 at4c1a8df (some test the new uniform refusal
code); the shifted bar values/positions were independently measured. An actual shared-panel
probe additionally failed after the first fix, exposing hidden tick labels and pruned levels.

All seven local gates215 Node/493 Python, zero skips;15 unchanged matching baselines,16 renders,
25 recipes/seven compositions; Ruff and strict gallery15/15 pass. Three synthetic exports were
visually reviewed. Final offline fresh wheel extracts real x=[0,0,1,1], y=[2,4,1,3], labels=[1,01],
with the optional agent passing and bundled source matching checkout. No tracked gallery/public
asset changes. Obsidian records the scope and limits; both GitHub workflows must pass after push.
Parent scientific reference matrix24 remains open.
