---
id: 20
slug: reusable-figure-ci
status: done
priority: P1
title: Consumable Figure CI with strict policy and review artifacts
source_idea: accepted reusable researcher CI roadmap
---

# Reusable Figure CI

Ship a composite GitHub Action that installs its own packaged local compiler, runs a caller's
paper manifest, writes a job summary and uploads current-run evidence even when checks fail.
Expose baseline, warning/change policy, timeouts, Python/extras and artifact settings. Outputs
include status, selected exit code, change state, aggregate report path and artifact download URL.

Treat caller inputs as environment data and subprocess arguments, never executable shell text.
Stage only the owned current run plus canonical report/summary/command files; do not upload a
caller's whole workspace, unrelated old output files or input CSVs. Invalid input produces a
current command error and no fabricated aggregate report. Pin first-party actions to verified
Node-24-compatible v7 commits.

## Verification

Three local wrapper tests verify passing/failed-claim/invalid-input outcomes, source/figure/report
staging, omitted CSV/unrelated files, GitHub outputs and job summary. Full local gates pass:
214 Node (zero skipped), 130 Python, 15 baselines, 16 renders, 25 recipes and seven compositions.
Ruff/typecheck/diff checks pass. JSON schema resources match their documented source.

The GitHub consumer workflow checks the tool out separately from the sample paper, runs the real
action, verifies two passing figures, reverses a claim, and requires action failure plus uploaded
review evidence. Its actual GitHub result/artifacts are checked after pushing before marking the
researcher-CI delivery requirement complete.
