---
id: 34
slug: measure-exported-text-size
status: done
priority: P0
title: Evaluate manuscript text size using actual exported figure dimensions
source_idea: matrix24 negative control passes nominal inspection but tight export makes its text2.93pt
---

# Actual exported text size

Measured at2c5208a: a3.4in figure with a6pt external label passes inspect_figure(target_width_in=3.4)
with no findings. Its tight-bbox PNG is6.959424687559163in wide; fitting the whole file to3.4in
makes the label2.9312767816091947pt, below the internal5pt floor. The inspector uses nominal
figsize rather than the file a reader receives. Existing gallery widths differ too; measure
their actual fonts before declaring a failure. A wider file alone is not a font-floor failure.

Generated workflows must assess font size against actual written static dimensions, including
tight crop/padding/external artists, for supported PNG/SVG/PDF exports. Preserve numeric values,
layout intent, source text and recoverable provenance. Record the measured widths and scaling
basis in structured evidence; never substitute zero or silently claim final-width verification
when an export's dimensions cannot be established. Keep useful failed artifacts for review.
Retain a clearly described nominal-canvas API for callers that have no exported files.

Use independent fixed-size and expanded/cropped examples, positive/negative floor controls,
multiple backend dimensions, actual generated strict exits/reports and table rendering paths.
Do not make a false pass by omitting text or disabling inspection. Resolve any genuine owned
gallery regression without suppressing its checker. Refresh source/provenance artifacts after
review, run seven gates/strict gallery/relevant fresh wheel, update Obsidian and inspect both
workflows. Table visible context35 and complete scientific matrix24 remain separate targets.

## Verified implementation

Generated programs now save/record static files before inspection. Physical PNG/SVG/PDF readers
measure final widths, use the widest requested format for conservative manuscript scaling, and
record explicit basis/widths/scale in structured reports. Unknown/partial dimensions stay unknown
and fail, while old or nominal-only inspectors make required inspection incomplete. A nominal
API remains explicit for callers without exports. Font-floor comparison tolerates only floating
representation noise; a real below-floor value is not rounded into acceptance.

37 independent API/runtime controls pass; the original26 failed before the feature. Full seven
gates pass215 Node/530 Python, zero skips;15 matching refreshed baselines,16 renders,25 recipes/
seven compositions; Ruff and strict gallery15/15 pass. All19 baseline/public PNGs have identical
RGBA/dimensions with refreshed source/provenance. Final fresh offline wheel verifies actual
measurements plus an oversized-title strict failure with retained files and the optional agent;
inspector/helper/emitter bytes match checkout. Obsidian records the scope and limits. Both
GitHub workflows must pass after push. Table context35 and complete matrix24 remain open.
