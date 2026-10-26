---
id: 35
slug: visible-table-context
status: done
priority: P0
title: Retain table title row heading metric and unit context in visible outputs
source_idea: matrix24 table probe loses declared title Dataset row heading and Latency ms in image
---

# Visible table context

Measured at2c5208a: a table declaring title Latency by dataset, x label Dataset and y label
Latency/unit ms produces image cells A/B/First/12.00/20.00. None of that declared context is
visible. Metadata contains a description, but a reader of the image cannot identify the
measurement or units. Markdown/LaTeX retain the row heading but also need truthful metric
context. Review requested percent formatting before adding a heading that changes how values
would be interpreted; preserve raw numeric estimates/highlighting and encode literal text safely.

Keep declared title, row-key heading and metric/unit context visible in supported table exports,
with consistent numeric display semantics across image/Markdown/LaTeX. Establish behavior for
grouped versus single-metric columns, percent display, intervals and missing cells. Preserve
literal author text and existing unknown-interval/highlight contracts. Do not invent context
or silently relabel fractions as percentages. If a table cannot fit its intended publication
context, fail the actual-export criterion rather than hiding labels or weakening inspection.

Verify actual rendered artists and exported/compiled text, independent numeric strings/units,
grouped/plain/missing/interval cases and meaningful failure controls. Run seven gates, strict
gallery and relevant installed artifact checks, update Obsidian, and inspect both workflows.
Actual exported-width contract34 and complete scientific matrix24 remain required.

## Verified implementation (2026-10-26)

Visible context is retained in image, Markdown and literal LaTeX: title, row heading,
metric/unit, requested interval meaning and bold-selection scope. Shared numeric formatting
scales percent cells and bounds consistently, without altering raw estimates or comparisons.
Confidence levels95.5%/99.9% retain their meaning rather than rounding to96%/100%.
Unsupported table axes/decorations fail semantic validation. Actual-export text inspection
continues to apply, including oversized-context strict failure with review files retained.

28 independent table artist/geometry/numeric/runtime/provenance controls and all four real
LaTeX compilation/extracted-text cases pass. Full local evidence:215 Node/558 Python,
seven gates, strict gallery15/15, Ruff and a clean offline installed wheel with agent.
The public table now has explicit-LF synthetic inputs, checked source/data fingerprints,
and reviewed visible context. Baseline and other published reference assets are unchanged.
Both GitHub workflows must pass after push before advancing; full matrix24 remains open.
