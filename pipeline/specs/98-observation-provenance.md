---
id: 98
slug: observation-provenance
status: in_progress
priority: P1
title: Trace displayed quantities through actual calculations to original observations
source_idea: 2026-11-02 research-platform idea17
---

# 98 — Observation provenance explorer

Starts after full97/0c7e141 exact14/all3 acceptance2026-11-05T04:02:03UTC.
The [full thirty-idea roadmap](../research-platform-roadmap.md) remains active.
Original requirement: click a displayed quantity or confidence interval and see
the contributing/excluded observations, filters, transformations, estimator and
generated code. Existing file hashes, row counts and context targets are foundations.

## Required behavior

1. Identify logical parsed records by the actual full byte-snapshot hash and
   reader/worksheet configuration. Preserve duplicates and identifier spelling;
   distinguish parsed ordinals from physical file lines/cells and declared units
   from established experimental independence. Keep original observations intact.
2. Capture actual filtering, missing/numeric conversions, wide reshape, sorting,
   baseline, cumulative and normalization dependencies. Baseline rows removed
   from display can still contribute. Preserve technical repeats, missing unit
   exclusions and exact finite/paired membership; never infer lineage from a
   final DataFrame index or equal plotted values.
3. Bind every displayed numerical quantity, center/bound and derived statistic
   to the actual estimator/settings and computation inputs. Cover all21 native
   kinds: line,scatter,bar,forest,slope,dumbbell,box,violin,raincloud,ridgeline,
   ecdf,paired_difference,calibration,qq,kaplan_meier,scaling_fit,confusion_matrix,
   waterfall,sparkline_grid,heatmap,table. Include supported smoothing/raw-summary,
   trendline/frontier,secondary-axis,significance and scientific-annotation paths,
   facets,repeats,layers,insets and animation-frame ownership. Do not substitute
   a mean-only proof for the complete calculation/plot inventory.
4. Carry exact quantity IDs into actual renderer-owned final geometry; clicking
   a mark/interval identifies its computation rather than an entire collection's
   shared setting. Preserve current text/diagnostic/inspector controls. Bind map,
   source,program,runtime,spec,run and final export; refuse stale/foreign/late maps.
5. Supply a usable local explorer and graph: select a quantity, inspect its
   contributors and scoped exclusions, follow transformation/estimator edges,
   view the generated code and download bounded evidence. Explain unavailable
   ancestry explicitly. Raw local lineage must not silently enter model payloads.
6. Preserve native/generated-code/standalone behavior, supported exported formats
   and useful numerical caching. Trace actual cache hits as well as cold work;
   do not rely on hidden side effects inside cached numerical functions or disable
   reuse to avoid tracing. Metadata/hash consistency does not certify science.
7. Independently recompute actual memberships and quantities, including duplicate,
   quoted CSV/Excel records,wide/faceted/repeated data,baseline dependencies,
   technical units,nonfinite/unmatched exclusions and specialized estimates.
   Exercise real current/minimum/installed native and browser paths,source/export
   mutation,stale ownership and bounded failure handling. Preserve all original
   graphics and the frozen research study without rewriting archived results.
8. Run all required local checks,make coherent meaningful commits/pushes and
   verify exact14/all3 CI plus relevant actual artifacts for each milestone.
   Keep the full thirty-idea goal active;no new release/tag is authorized.

## Coherent checkpoints

98a: shared bounded local lineage ledger with stable record identities,ordered
calculation dependencies,scoped exclusions,owned export/import and refusal tests.
This supplies the data model; it does not yet instrument a generated program,
attach an actual plotted quantity or deliver the clickable explorer.

98b: actual reader/prepare/summary and specialized calculation tracing,including
independent public/synthetic membership/value references and useful cache hits.
The reader/filter checkpoint adds opt-in local SDK and CLI capture for actual CSV,
JSON, Parquet and Excel readers. It records temporal ordering, exact filter masks,
and exclusions before reshape. The bounded sidecar is referenced by the render
report and tied to its input snapshot, specification, program, runtime and run.
The reader/filter checkpoint and demo compatibility repair at `4a3e5c2` passed
all fourteen exact checks and all three workflows. Preparation adds a second
root for the actual prepared rows, source cells, conversions, cumulative
prefixes, normalization ranges and matched baseline dependencies. The
preparation checkpoint at `01e8634` passed all fourteen checks and all three
workflows. Ordinary summaries add a separate root for measured line, bar,
forest and table estimates, declared-unit collapse and requested intervals.
Positional grouping follows the actual reductions and survives numerical
cache reuse, with current-run calculation ownership. The ordinary summary
checkpoint at `b165188` passed all fourteen exact checks and all three
workflows. Heatmap and confusion-matrix cells now record actual aggregates,
measurements, exclusions and annotations. Normalized confusion shares link to
their own count and the actual row or column denominator. Native matrix image
arrays retain ordered cell IDs. This calculation checkpoint passed all fourteen
checks and three workflows at `1e6de8e`. Other specialized estimators remain
part of 98b.

98c: renderer quantity geometry,local API/CLI and real workspace explorer/code/
download lifecycle,then a full requirement-by-requirement acceptance audit.
Split further meaningful milestones where needed without shrinking any requirement.

The matrix PNG path captures the final tight-cropped draw for traced heatmaps
and confusion matrices. It records the image artist's transformed cell edges
and actual rectangular clip, then binds the grid to the ordered matrix cell
calculations and to the saved image. The opt-in PNG carries a unique run stamp.
The local lookup checks the report, generated program and PNG before reading
the saved graph. It refuses altered exports, overlapping cells with different
calculations and unsupported placement. The returned graph points to separate
filter and preparation roots.

```sh
graphunslopify render figure.json --trace-observations --out-dir render
graphunslopify explain-cell render/figure.report.json 240 160
```

Use the export's own pixel coordinates measured from the upper-left corner.
In the local editor, **Trace observations** opts into the same matrix evidence.
A cell can be selected by PNG position or panel, row, and column. The explorer
pages contributors and exclusions, links calculation inputs and the filter
and preparation roots, shows the generated Python and offers an explicit graph
download. Editor generation, render attempt, runtime and file checks protect
against stale or altered evidence. Line, nonstacked bar, and forest summaries
carry interval IDs through the actual sort, series selection, and category
reindexing into the visible stems and caps. Empty categories have no stroke. The final draw records their cropped PNG geometry. The
SDK, `explain-interval` CLI, and local editor select those interval nodes.
A singleton has no hit geometry, and the reader rejects overlapping distinct
intervals. Monotone filled bands bind the visible strips in the final PNG to
the two calculated endpoints that draw them. A click between measurements
opens those calculations. Gaps in the actual band have no selectable span.
Nonmonotone bands, estimates and the remaining renderer and quantity
inventory remain part of the full scope.

Nonstacked summary bars and forest center dots carry estimate IDs separately
from their intervals. The editor can switch between the two on the same PNG
and offers indexed selection for each. The local `explain-estimate` command
checks the saved evidence before resolving the pixel. A singleton forest dot
retains its estimate when no interval is available. Stacked contributions and
the remaining quantity inventory remain part of the full scope.

Unsmoothed primary summary lines bind visible point markers and vertices to
their estimates. A supported solid stroke links its two calculated endpoints.
Missing values break the path. The line, its point estimates, and its uncertainty
strokes or band are picked against the same final PNG. Dashed and simplified
connections show an explicit coverage gap while retaining visible point markers.
The smoothing, secondary-axis and remaining line paths stay in the full scope.

## Measured references and current limits

Before implementation,the actual public-penguin final PNG has two uncertainty
collections with three segments each but no per-quantity/observation IDs. Its
344 parsed records contain333 sex-filtered observations;an independent reference
records all six groups' original ordinals and mean/sample SD. The intervals are
descriptive SD,not confidence intervals.

Six unchanged actual generated-program cases per retained Python3.10.22 and
3.12.14 match hand-computed no-transform,delta,percent-baseline,normalization,
cumulative and technical-repeat results. A quoted CSV newline gives8 logical
records across10 physical lines. These independent reference fixtures predate
the generated capture and remain unchanged.
Durable script/receipts: Documents/Project Evidence/GraphUnslopify/
research-platform-98/measure-dataflow-reference.py and dataflow-reference-*.json.

Full original idea17 remains in progress until every requirement above is proved.

98a initial candidate passed all ten gates with2553 Python tests,then a deeper
metadata control reproduced accepted evidence that could not export/explain.
The candidate was superseded before publication. Five of eight new controls
fail on its bytes; the first repair still rejected a valid nested reader owner.
The repaired ledger copies already validated trees and validates expected reader
ownership at the same input boundary. All38 targeted tests pass current3.12.14,
minimum3.10.22 and cleanly reinstalled package. All108 package files match and
parent107 files are unchanged. Both profiles export/reload a6001-node graph with
identical bytes. Automatic quantity and UI tracing remain part of full 98.

The observation ledger passed all ten local gates. The suite covered 235 Node tests, 2,561 Python tests, and 15 gallery figures. All 38 targeted tests passed on each Python profile and the reinstalled package. The wheel and installed runtime match the 108 source files.

Commit `afb87e7` passed all fourteen checks and all three workflows, including
four verified distributions. The remaining checkpoints connect the actual
computations to plot marks and the explorer.
