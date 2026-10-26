---
id: 41
slug: shared-series-identity
status: done
priority: P0
title: Keep series appearance and legend identity stable across sparse panels
source_idea: matrix24 same series1 changes blue solid to orange dashed when01 appears in later facet and common legend omits01
---

# Shared series identity

Measured at58e018f: a line's first facet contains only1, the next01/1. Series1 changes from
blue solid to orange dashed; the first/common legend lists only1. The inspector correctly
rejects colour drift, but supported sparse panels should render consistently and all actual
series need an identifiable legend. Declared series order does not fix local style indices.
Dumbbell labels only the first category, so a group appearing later can also lose its legend.

Establish one per-figure series style mapping before panel/repeat drawing, preserving
explicit order and observed unlisted IDs. Stable colours/secondary channels must follow names,
not local subset position/count. Collect an ordinary shared legend from actual drawn handles
across panels, preserving order/extra overlay labels; keep value-specific/direct legends
scoped to their own panels. Fix manual colour paths/late dumbbell labels where necessary.
Do not invent observations or change quantitative values. Recompute shared state on reuse.

Verify full actual artists/labels across grouped kinds, sparse/ordered panels and repeated
metrics, direct labels, later-only groups, existing palette locks and strict exports.
Run seven gates/gallery/fresh installed proof, refresh only affected provenance/assets,
update Obsidian and inspect both workflows. Complete scientific matrix24 remains open.

## Verified implementation (2026-10-26)

Shared style order is computed from the full prepared figure before drawing, preserving
explicit/observed unlisted names. Local missing groups cannot change a series' colour/channel.
Ordinary shared legends collect actual handles across panels, keep ordered names and overlay
labels. Calibration value legends remain local; direct labels now follow every panel/metric.
Manual dumbbell/sparkline colours use series styles, and later-only dumbbell groups get ordered
handles. Channel constants needed by these helper paths are emitted. Per-figure state resets;
palette_lock remains the cross-figure persistence mechanism.

32 actual-workflow controls pass across11 grouped kinds; initial28 all failed. Locked secondary
channels, direct labels, module reuse, sparse/late groups, overlay labels and strict PNG/SVG are
verified. Seven gates215 Node/796 Python, zero local skips/warnings, gallery15/15, Ruff and fresh
offline wheel/agent pass. Installed actual styles/values/shared legend are independently checked.
A brittle Node assertion about legend_added was replaced by actual-artist coverage. The corrected
probe was visually reviewed; baseline scripts/assets and51 published PNG blobs are unchanged.
Both workflows require verification after push; complete matrix24 remains open.
