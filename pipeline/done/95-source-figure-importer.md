---
id: 95
slug: source-figure-importer
status: done
priority: P1
title: Import supported Matplotlib and Seaborn source into reviewed editable figures
source_idea: 2026-11-02 research-platform idea2
---

# 95 — Supported source importer

Starts after94/a9981c9 exact14 acceptance2026-11-03T22:11:13UTC.
The [full thirty-idea roadmap](../research-platform-roadmap.md) remains active.

## Required behavior

1. Parse bounded Python source without executing,importing or evaluating user
   code. Use an owned worker with deadline/memory/output limits;AST parsing alone
   is not resource isolation. Preserve original UTF8 bytes/name/SHA separately.
2. Convert an explicit supported subset of single-axis Matplotlib/Seaborn plots
   into the existing canonical spec/compiler. Start with raw line/scatter/bar,
   literal vectors or explicit columns in an author-mapped local dataset,and
   supported labels/title/scales/dimensions. No second chart emitter.
3. Report unsupported syntax/calls/dynamic behavior at source locations. Preserve
   originals even when conversion refuses. Do not claim arbitrary Python or
   pixel equivalence. Unknown mutations must not silently produce a faithful
   conversion claim;partial extraction needs explicit author review.
4. Preserve actual values/group/ordering semantics or refuse unsupported choices.
   Never silently add/remove estimators,intervals,observations or encoded data.
   Seaborn defaults and numeric hue are scientific/visual semantics,not decoration.
   Explicit dataset binding does not prove the original runtime's data identity.
5. Expose shared module/CLI and actual editor upload/review/apply/native/undo flow.
   Bind source/data/context/review;late or stale proposals cannot replace newer
   edits. Original source and import report stay local;bundle inclusion is explicit.
6. Test actual trusted original Matplotlib/Seaborn fixture artists against converted
   native values,supported/unsupported/dynamic cases,no side effects,quotas and
   source/context/undo fences. Current/minimum Python,real browser and installed
   wheel controls must pass. Preserve all graphics/frozen research evidence.
7. Run all required local gates,push a coherent checkpoint,and verify exact14 CI
   before advancing. No new release or scientific/adoption certification.

## Read-only groundwork

Official Python3.10 AST docs plus actual3.12.14/3.10.22 probes show parsing does
not execute calls but does not establish full scoping validity;columns are UTF8
bytes. Both parse/literal evaluation need resource bounds. Seaborn0.13.2 lineplot
defaults include mean/95% CI/1000 bootstrap/sort=True. No importer was delivered
by those probes. Durable plan/probe:
`/Users/shooter/Documents/Project Evidence/GraphUnslopify/research-platform-94/next-importer-plan.json`
and `probe-ast-boundaries.py`. Obsidian owns the linked source/measurement notes.

## Final acceptance

Accepted a94446f after all14 exactCI/three workflows2026-11-04T02:24:30UTC.
All10 local gates235 Node/2327 Python/one warning/g15;986 final Git/95 installed
package bindings match. ActualCI importer11 controls/original bytes/native
exports/all95 runtime files and three screenshots verify. CI3.10:2322pass5skip
28warnings2457.50s;3.12:2322pass5skip1warning2442.97s. Skip reasons unprinted.
Full idea2 supported scope complete;full30 stays active. No release/PyPI.

The candidate section below records the earlier pre-push state.

## Historical candidate and local verification

2026-11-03: shared bounded reader, static parser/worker, public module/CLI and
actual editor review/apply/strict-native/undo are implemented. Original source
and located unsupported findings remain available after refusal. Native exports
and bundles carry conversion provenance; original Python stays separate.

All ten local gates pass on981 unchanged protected paths:235 Node tests,
2327 Python tests (one upstream SQLAlchemy warning,zero skips),gallery15/15.
Current/minimum browser controls each pass11,including late review/acceptance,
explicit CSV mapping,partial review,exact original/report downloads and undo.
Minimum62 targeted tests and fresh71 tests/one warning plus11 browser controls
pass. Actual original Matplotlib/Seaborn artists match extracted/native values;
inferred Seaborn axis/legend labels are also checked. All95 installed package
files match source. Private wheel581096 bytes/SHA
`7b6a411e3565a757508426fb106b5e45611cd4c429b8824ad8a53c6e457d7331`.
All52 README graphic placements/51 asset bytes and frozen study files remain.

The first freeze/initial wheel was superseded before publication to preserve
Seaborn column labels;its partial evidence remains historical. The same private
95 environment was reused. Normal push and exact14/actual CI artifact acceptance
are still required before this milestone is complete. No release/PyPI publication,
arbitrary Python compatibility,scientific certification or adoption is claimed.
Raw evidence lives outside the repo/vault in research-platform-95/.
