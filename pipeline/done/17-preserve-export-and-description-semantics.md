---
id: 17
slug: preserve-export-and-description-semantics
status: done
priority: P0
title: Equivalent supported HTML data and descriptions that match displayed quantities
source_idea: accepted trustworthy export and independent validation roadmap
---

# Preserve export and description semantics

Interactive line/scatter/bar/heatmap exports now share supported summaries,
intervals, declared units, ordering, orientations, category spacing, scales and
limits with the static analysis. Embed Plotly, descriptions and safely escaped
recoverable provenance instead of depending on a CDN. Unsupported analyses or
composition produce explicit errors and no misleading generic-scatter fallback.

Single-point lines get visible markers. Endpoint descriptions use one shared x
and disclose unavailable values; category endpoints follow plotted order. Heatmap
descriptions use aggregated cells. Series order does not silently discard
unlisted observations. No finite measurements make verification incomplete.

A numeric fixture exposed another description defect: precomputed confusion
counts were described as input-row counts. Static image and description now share
one count matrix, including sparse zeros and normalization. Explicit missing,
negative, nonfinite or fractional counts fail instead of becoming observations.

## Verification

Eight local gates pass: 212 Node / 105 Python, 15 matching scripts, 16 PNG/PDF
renders, 25 recipes, 7 composition cases and 15/15 strict gallery figures.
Sixteen numerical/export regressions cover actual Matplotlib/Plotly output,
expected means/bounds, both bar orientations, cell sums, log ranges, visible
single points, partial endpoints, retained series, untestable data, safe embedded
HTML, all three count normalizations, sparse cells and invalid counts.

An actual Chrome session loaded the exported file with HTTP requests blocked:
expected means [1.5,2.5] / [5.5,6.5], working hover and legend toggle, zero external
page requests and zero JavaScript errors. Screenshot inspected. The new serializer
escaped a </script> fixture correctly. Gallery RGBA pixels remain unchanged;
computed descriptions/provenance were refreshed. Ruff/diff checks pass.
GitHub CI is checked after pushing.
