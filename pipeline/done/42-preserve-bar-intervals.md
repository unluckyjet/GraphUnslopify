---
id: 42
slug: preserve-bar-intervals
status: done
priority: P0
title: Prevent reflected ignored or invisibly clipped bar uncertainty bounds
source_idea: matrix24 IQR bounds0and0 become0to40 from abs widths and clipped CI1to9 in view0to5 passes strict
---

# Actual bar interval bounds

Measured at04d04d3: mean20 with IQR0/0 from0/0/0/0/100 draws a stem0..40, reflecting a bound
through the estimate via absolute widths. A median bootstrap interval1..9 viewed through0..5
returns strict passed/no errors while its upper cap is hidden. Stacked+uncertainty is accepted
although the stacked drawing path omits its bounds entirely.

Do not change requested interval endpoints to make centered errorbar widths nonnegative.
Refuse data-dependent bounds that exclude the estimate in this bar representation, with clear
alternatives; allow only machine-rounding tolerance, independent of measurement units.
Preserve unknown bounds. Detect axes clipping of standard bar interval stems, independently
of body visibility/orientation/sign. Explicitly refuse unsupported stacked uncertainty rather
than silently omit it. Keep valid mean/median intervals, known missingness and stacked bars
without requested intervals working.

Verify independent actual endpoints, tiny/scaled/negative/outside cases, unchanged valid
quantities, explicit clipping controls and strict reports/artifacts. Run seven gates/gallery,
fresh installed positive/failure evidence, provenance refresh if needed, Obsidian and both
workflows. Complete scientific matrix24 remains open.

## Verified implementation (2026-10-26)

Finite detached bounds fail with a clear representation error instead of absolute-width
reflection. Only16 machine-epsilon relative rounding tolerance is allowed; missing bounds
stay unknown. Semantic/direct stacked uncertainty is refused without changing ordinary stacks.
Inspection checks actual transformed interval stems in either orientation and on either side,
including inverted axes, while preserving clip-disabled behavior and review artifacts.

41 focused references pass. Initial37 measured26 failures/11 passes; four extra positive/
inverted/clip-disabled controls pass. Seven gates pass:215 Node and833 full-suite Python plus
those four additional controls, zero skips/warnings. Gallery15/15, Ruff, clean offline wheel/
agent and byte-identical installed translator pass. Actual installed1..9 endpoints, clipped
failure and detached/stacked refusal are independently measured. All baseline source/assets
and51 published PNG blobs remain unchanged. Obsidian links96 notes/0 unresolved. Both CI
workflows require verification after push; full quantity/domain matrix24 remains open.

CI follow-up: a714c03 passed Figure CI and all four installed platform jobs; both
Python jobs stopped at Ruff formatting of one long inspector line. Wrapped that line,
then reran all seven gates:215 Node/837 Python, zero skips/warnings, and both full
Ruff checks (52 files) pass. No behavior/source bundle or artifact content changes.
