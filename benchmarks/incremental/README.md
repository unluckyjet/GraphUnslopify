# Numerical reuse and verified rendering

This source milestone adds bounded numerical reuse to the local editor. It keeps
current input loading/counts, claims, inspection, reports, maps and requested
exports on every render. A cache hit does not carry earlier scientific acceptance.
Staged/unverified preview is a separate unfinished85b milestone. Public PyPI0.8.0
predates this source feature; no release is published here.

## Prospective comparison

[Protocol numerical-cache-v1](protocol.json) was frozen after accepted179784f and
35 uncached edit preflights, before implementation/formal timing. It retains the
five exact v4 datasets and original strict negatives.35 frozen intents preserve
complete long wording and vary titles, DPI and a non-removing filter. This is
developer-selected engineering measurement, not held-out or human evaluation.

Both arms reuse the actual compiler/native workers; numerical caching is explicit
off/on. Rotate arms by case with independent initially fresh fonts. Per arm/case:
one cold original, seven cycles of seven edits and one separate instrumented
original.510 formal records preserve408 clean0/102 original false-claim2; smoke
is90 records (72/18). Keep original16-job native and64-job translator recycling,
including actual restart/cache-reset costs. Report per-edit medians/p90 rather
than pooling changed outputs. No timing or hit-rate threshold.

```sh
python scripts/benchmark-statistics-cache.py --out-dir /absolute/new-directory
python scripts/benchmark-statistics-cache.py --smoke --out-dir /absolute/another-new-directory
```

Use the scientific interpreter/working Git explicitly; --installed rejects source
imports and requires13 actual package assets to match. The primary clock wraps
actual PreviewState.render, including current prepare/conversion, key/lookup/
copy/miss work, native startup/recycling and all strict artifact/map binding.
Constructor/upload, first fonts and instrumentation are separate. Browser/app
startup and artifact hashing are excluded; OS caches are uncontrolled. Inclusive
phase times overlap. Preserve every failed, negative and partial attempt.

## Ownership and correctness

The private worker owns at most64 entries/32MiB serialized values,8MiB per entry
or argument. These are serialized-byte limits, not total process RSS. Values are
copy isolated; only bytes made in that process are deserialized. Keys include
full original input SHA256, typed arguments/attributes, numerical intent/dynamic
settings, helper definitions, canonical source and relevant actual versions.
Presentation exclusions retain units, groups, transformations and intervals.
Trivial identity functions are skipped; other calculations remain fresh.

Only known summary_input/bootstrap_interval/summarise helpers are eligible.
Current effectful readers/preparation/counts, missing-interval bookkeeping,
claims, verification and exports remain outside reuse. Damaged/unsupported/large
entries recompute; real calculation errors never reuse a previous success.
Per-call actual cache counters/PID/source/budgets accompany the native result.
Cache mode/version is part of readiness;16-job native recycling clears values.

## Measured local comparison

Final [510-record vector](results/numerical-cache-v1/formal-comparison.json)
passes408 clean/102 original strict-negative outcomes, with all current source
assets/evaluators and matching script/data/science/PNG/table/maps. Actual host:
macOS27 arm64, Python3.12.14, NumPy2.5.4, Pandas3.1.0, Matplotlib3.11.2,
SciPy1.18.1. Each arm/case uses four actual native epochs under the unchanged
16-job limit. First-font calls are6.892–7.774s and are separate from warm repeats.

For the second title edit, seven ordinary-repetition medians in seconds:

| Original case | Numerical cache off | On |
| --- | ---: | ---: |
| demo-bootstrap | 0.227091 | 0.224250 |
| long-sparkline | 0.286603 | 0.286105 |
| long-grouped-table | 0.148469 | 0.148056 |
| dense-median-bootstrap | 1.078802 | 0.338521 |
| false-comparison | 0.227279 | 0.224020 |

All seven dense-case edits follow, including costs of native recycling and
configuration misses. Repeated identical filter configurations may legitimately
reuse their own prior calculation; first changed configurations miss.

| Edit | Off median | On median | Off p90 | On p90 |
| --- | ---: | ---: | ---: | ---: |
| original | 1.074165 | 0.336917 | 1.090669 | 0.340187 |
| title-a | 1.087519 | 0.338992 | 1.219100 | 0.626675 |
| title-b | 1.078802 | 0.338521 | 1.097373 | 0.341172 |
| dpi | 0.957113 | 0.213422 | 1.094932 | 0.494339 |
| numeric-filter-config | 0.966604 | 0.227181 | 0.976165 | 0.601776 |
| title-after-filter | 0.964922 | 0.222271 | 1.104915 | 0.504562 |
| return-to-original-calculation | 1.083437 | 0.338813 | 1.095130 | 0.508413 |

This records a useful dense-bootstrap gain; small cases mostly change by
milliseconds, with both faster and slower edits in the raw vector. Sparkline and
table have no eligible nontrivial reuse. No universal benefit is established.
The complete per-edit vectors include all ordinary p90s, first-font calls,
instrumented phases, counters and retained strict failures.

The initial90 included table identity helpers, subsequently excluded. The first
510 used a pre-format profiler; its exact source and result remain in history/
and initial-formal-comparison.json. A full CI Ruff target list caught a wrapping
line; final formatting was followed by a complete510 replay and restarted stable
gates. These old vectors are historical evidence for their own recorded bytes.

## Current acceptance

Source54 focused controls and minimum/fresh86 controls pass. Source/fresh editor
runs each pass101 workflows,21 control kinds,91 actual responses per worker,
zero external requests/JavaScript errors. Each reply requires actual cache PID,
source, mode and byte/count limits. Installed HTTP repeats reuse four numerical
results with zero misses and close both workers. All39 Python/bundle files plus
diagnostics JSON/license (41 files total) match current source after testing.

Source/minimum/fresh each pass30 actual-kind comparisons/60 native renders across
all21 kinds, animation/table and CSV→JSON→Parquet, including strict-negative→
clean recovery. Minimum/fresh installed90-record smoke comparisons pass72 clean
and18 original strict-negative outcomes, with13 actual package assets each.
The kind runner consumes accepted84's unchanged generated recipe fixtures
(translator775390f1); the current seven checks independently rerun all recipes.

All seven stable checks pass232 Node/1887 Python/zero skips/one upstream warning, Ruff149,361 unchanged files. Pushed bbcef49; exact main41169738321 all-nine/Figure41169738378 passed05:10UTC. The final acceptance and both actual Python90/45 result vectors are retained alongside these local records.
85b's provisional/final UI and all86–89 scope remain open.
