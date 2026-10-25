---
id: 14
slug: clean-gallery-layout
status: done
priority: P0
title: Readable gallery with a strict rendered regression gate
source_idea: external review's acknowledged gallery defects
---

# Clean gallery layout

The scatter legend covered two observations; all three benchmark panels had
colliding category names. Move the scatter legend below the data. For ordinary
categorical layouts, measure actual tick boxes and rotate crowded names while
preserving complete text, font sizes, and numerical values. Never suppress the
inspector to make an example pass. Outside legends retain their existing layout.

Add `npm run gallery-check` to regenerate every published example in a fresh
artifact directory, execute `--strict`, require completed inspection and a passed
report, and reject missing evidence. GitHub CI runs the gate and uploads the
plots/programs/reports for review (including failed runs).

## Verification

The gate's negative control detected exactly the original legend/tick errors and
failed at 13/15. With fixes it passes 15/15. Visual inspection caught an anchor
problem missed by overlap checks; the final regression explicitly checks every
name, original font size, unchanged bar heights, and tick boxes below the data.
Both resulting PNGs were visually inspected after correcting the anchor.

Seven existing gates plus the gallery gate pass: 204 Node / 77 Python tests,
15 matching scripts, 16 PNG/PDF renders, 25 recipes and 7 composition cases.
Only gallery 06/10 changed pixels. Their PNG/SVG/PDF artifacts were refreshed;
unrelated vector timestamp/ID churn was restored. GitHub CI is checked after push.
