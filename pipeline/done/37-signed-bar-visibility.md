---
id: 37
slug: signed-bar-visibility
status: done
priority: P0
title: Preserve signed bar magnitudes and detect clipped value extents
source_idea: matrix24 repeated negative bars -30 -20 -10.5 clip near0 yet strict report passes ate13f864
---

# Signed bar visibility

Observed in36's repeat-sort exported artifact: negative values-30/-20/-10.5 appear as equal
bars clipped at-0.05. A fresh direct strict run returns passed/inspection.checked=true/no
errors. Zero-baseline decoration forces the lower numeric bound to0 even for negative values;
inspection guesses bar orientation from rectangle aspect/sign and tests only positive baseline
cuts. Preserve signed magnitudes with a zero-inclusive automatic range. Use actual bar-container
orientation and detect clipped value extents, including explicit limits, without applying a
common-zero rule to legitimate floating bars. Keep review artifacts when strict mode fails.
Verify actual visible endpoints, signed/fractional/grouped/orientation cases, baseline controls,
explicit clipped limits, legitimate floating marks and unchanged non-bars. Check sign-aware
value-label placement and truthful percent display. Run seven gates, gallery, installed proof,
Obsidian and both workflows. Full matrix24 remains open.

## Verified implementation (2026-10-26)

Zero-inclusive automatic bounds preserve complete signed magnitudes in both orientations.
Actual BarContainer orientation replaces aspect/sign guesses. Transformed body extents detect
clipped values/origins, while genuine floating origins avoid a false zero requirement.
Signed labels sit outward and percentage labels agree with percentage axes. Two old Node
assertions requiring a forced lower0 were removed;44 independent actual-artist/inspector/
strict-export controls now verify the stronger behavior. Initial37 controls measured26
failures/11 passes. Existing repeat-sort negative warnings are resolved.

Seven gates pass215 Node/653 Python, zero skips/warnings; gallery15/15, Ruff and fresh offline
installed wheel/agent pass. Installed actual heights[-.02,.08], labels[-2%,8%], inclusive
limits and deliberately clipped strict failure are independently checked. All20 tracked
baseline/public PNG pixels/dimensions matche13f864; three bar source/provenance assets refresh.
The formerly clipped repeat-sort export was visually reviewed with full signed lengths.
Both workflows require verification after push; full matrix24 remains open.
