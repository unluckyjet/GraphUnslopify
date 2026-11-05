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
All later preparation, estimator, caching, and displayed-quantity tracing remain
part of 98b and 98c.

98c: renderer quantity geometry,local API/CLI and real workspace explorer/code/
download lifecycle,then a full requirement-by-requirement acceptance audit.
Split further meaningful milestones where needed without shrinking any requirement.

## Measured references and current limits

Before implementation,the actual public-penguin final PNG has two uncertainty
collections with three segments each but no per-quantity/observation IDs. Its
344 parsed records contain333 sex-filtered observations;an independent reference
records all six groups' original ordinals and mean/sample SD. The intervals are
descriptive SD,not confidence intervals.

Six unchanged actual generated-program cases per retained Python3.10.22 and
3.12.14 match hand-computed no-transform,delta,percent-baseline,normalization,
cumulative and technical-repeat results. A quoted CSV newline gives8 logical
records across10 physical lines. Dependencies and exclusions are reference
expectations;current generated programs do not emit their observation graph.
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
