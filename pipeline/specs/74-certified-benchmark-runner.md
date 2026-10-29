---
id: 74
slug: certified-benchmark-runner
status: ready
priority: P1
title: Retain complete comparative runs and live producer-implementation clocks
source_idea: review2026-10-28 item17 complete benchmark error timing reproduction quality evidence and real development-task sessions
---

# Comparative runner and live implementation sessions

1. Execute every frozen dataset/arm/variant/repeat in alternating order. Validate
   original raw pins and every prepared CSV token/order against original sources,
   even if mutable prepared metadata has been rebound. Default runs stay offline.
2. Retain separate producer/execution logs, process timeout/nonzero status, actual
   save-time numeric/quality measurements, exact labels, file identities, native
   product reports and implementation/environment fingerprints. Continue ordinary
   failed cases; never count execution failure as detecting the missing-SD sentinel.
3. At study end recheck exports/input/producer identities. Missing or changed
   artifacts cannot pass reproduction. Detect duplicate/missing membership and
   second-repeat/status disagreements. Report measurement denominators and numeric
   deviations, with machine build/process/instrumented/save timings kept separate.
4. Begin live append-only task events before further producer-specific work, with
   absent producers and fixed Matplotlib-then-GraphUnslopify order. Preserve failed
   attempts; clocks cannot reset or finish on partial success. Stop only after all
   nine clean cases pass, retaining durable metadata reports and UTC/monotonic times.
5. Verify with synthetic orchestration/process/worker/session controls plus actual
   nine-source loading without plotting. Freeze/verify this runner before timed
   real producers or NIST plotting outputs. Human results remain unmeasured.
6. Seven gates and exact main/Figure CI; commit/push independently. Public0.8.0
   unchanged, benchmark17 not complete until actual adapters/runs/results exist.

## Prior checkpoint

Exact4b2ed97 main40844509236 all9/Figure40844509180 passed. Protocol/evaluator
hashes remain unchanged from73; no NIST plotting outputs evaluated yet.

## Implementation and focused evidence — 2026-10-29

`benchmarks/certified/runner.py` and `scripts/certified-benchmark.py` implement the
complete72-run plan, source/token integrity, process logs/timeouts, actual native
reports and external numeric/label/quality/reproduction evidence. Study-end
retention rechecks prevent deleted/changed outputs from counting as reproduced.
Source hashes, Git head/dirty state, dependency/platform context and shared/
producer/payload/generated-code sizes identify what ran and what is excluded.

Live append-only begin/attempt/end events require absent producers, fixed order
and complete nine-case success. Failed attempts preserve reports and keep their
original clock. Source-file names use build- prefixes to avoid Python library
shadowing. Sessions require one host/OS boot; UTC and monotonic evidence coexist.

Nine synthetic controls pass: full schedule, second-repeat failure/status
accounting, missing/duplicate membership/images, rebound CSV metadata, actual
process timeout/nonzero logs, timer order/reset/partial-success refusal, sentinel
execution-failure separation and real producer-to-worker/export capture. Deleting
its actual PNG invalidates retention and reproduction. An initial control assumed
the changed execution was the last summary pair; corrected it to select the
matching dataset/arm/variant, preserving publisher/arm ordering.

Actual all-nine raw/CSV token verification passes for8,574 observations. Current
editable-package/context fingerprints validate; real producers and live journal
are absent. CLI missing-producer refusal returns2 without creating output.
Frozen73 protocol/evaluator/worker bytes remain unchanged. All seven local gates pass:225 Node/1399 Python, zero skips/one upstream
MLflow/SQLAlchemy warning,15 baselines/16 renders/25 recipes/7 compositions.
Ruff check/format99 pass. No NIST plotting outputs or live producer-task timings
have been measured. Exact pushed main/Figure CI must pass before those tasks.
