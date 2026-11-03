---
id: 93
slug: local-experiment-histories
status: in_progress
priority: P1
title: Select local experiment runs and create verified comparative figures
source_idea: 2026-11-02 research-platform idea1 local-provider checkpoint
---

# 93 — Local experiment histories

Starts after full92/0f967bc exact14 acceptance2026-11-03T17:33:48UTC.
The [complete roadmap](../research-platform-roadmap.md) remains active. This is
the CSV-directory/TensorBoard checkpoint of idea1;inbound MLflow and W&B remain
required in the following provider checkpoint. Existing outbound MLflow logging
does not satisfy those requirements.

## Acceptance

1. Read real local CSV result folders and TensorBoard event files through bounded,
   read-only source adapters. Expose run identities,metric names,reader/version,
   complete source hashes,step/time ancestry,missing/nonfinite exclusions and
   restart/duplicate policies. Never silently sample,merge same-name runs or
   aggregate duplicate steps. Refuse corrupt,truncated,escaped,oversized or
   changed sources and unsupported scalar representations explicitly.
2. Provide Python/CLI and authenticated local-editor catalog/run/metric selection.
   Review counts,source identity,exclusions and the proposed figure before apply.
   Requests changing data/provider/intent or source fingerprints cannot apply
   old replies. Retain source files and offer an owned import undo.
3. Reuse owned dataset upload,the canonical Figure compiler/native renderer and
   existing strict result/export lifecycle. Comparative line/scatter figures
   preserve selected real values and run IDs. No automatic estimator,independence,
   confidence interval,claim certification or acceptance follows from import.
   Duplicate-step line choices need explicit supported handling;keep raw records.
4. Record import provenance with saved comparison output/bundles. Local files
   stay local;no external account,cloud upload or automatic tracking writes.
   TensorBoard is an optional extra with clear unavailable-dependency guidance.
5. Verify actual CSV/TensorBoard histories,original bytes/record identities,
   native numeric values,corruption/change/duplicate/restart/missingness refusals,
   browser review/apply/undo/staleness,minimum Python and fresh installed flows.
   Run required contribution checks,push a meaningful checkpoint and accept
   exact14 CI before advancing. Preserve all52 README placements/37 study assets.

## Existing measured groundwork

Obsidian Experiment History Imports records actual TensorBoard2.21 current/minimum
stream reads:13 values/restart from two unchanged files,legacy7simple+6tensor vs
compat13tensor. Reservoir and purge semantics differ. RawEventFileLoader swallows
DataLossError;an importer must detect truncated/corrupt evidence rather than label
its prefix complete. Real local MLflow3.17.2 and controlled W&B0.31 probes remain
provider groundwork,not delivered inbound Graph connectors.

## Implemented boundary and targeted evidence

The local reader,CLI and authenticated preview routes share a source-bound
catalog/comparison. `web/experiment-imports.js` lists actual runs,requires review
and separate exclusion consent,and uses existing native rendering with guarded
undo. Native outputs/bundles retain import provenance;raw CSV is excluded from
editor ZIPs by default. See [the guide](../../docs/workspace/experiment-histories.md).

34 backend controls pass on Python3.12.14/3.10.22,including actual TensorBoard
event writers,CRC/truncation/shape/byte/point bounds,source changes,POSIX file/parent
symlink swaps,actual native numeric artists,HTTP ownership,and exact signed64
integer records above the float mantissa. The integer regression was found in a
final actual probe;earlier32-case/private-package evidence is superseded.

Ten browser controls pass oncurrent/minimum/fresh installed package:real CSV and
TensorBoard comparisons,exclusions,duplicate/restart retention,source mutation,
invalid JSON/late reply fences,prior-dataset undo/later-edit protection and mobile
layout. No browser page errors/external requests. The corrected private wheel has
87 source-matching package files,553984 bytes,SHA256
`a2ebdcfae2fb1af02e301fc9052e136f3994034134346a0e591f0c632908d7fa`.
Actual installed CLI cases return0/passed and2/failed with native reports retained.

Gate trial1 was superseded after the integer fix changed its imported package:
its source-identity guards correctly refused stale execution. Gate trial2 runs
against the corrected frozen candidate. All10 required local checks now pass on
965 unchanged protected paths:2265 Python tests,one upstream SQLAlchemy warning,
and15/15 strict gallery figures.52 README placements/all51 referenced local assets
match the parent;all949 prior protected paths outside the ten intended source/
package/README/config modifications are unchanged. Push and exact14 CI must pass
before this checkpoint is accepted. No release/PyPI publication follows.
