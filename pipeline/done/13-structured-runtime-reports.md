---
id: 13
slug: structured-runtime-reports
status: done
priority: P0
title: Structured runtime evidence and enforceable failure policies
source_idea: accepted Figure CI and paper-wide auditing roadmap
---

# Structured runtime reports

A generated figure used to print errors and failed/untested claims while exiting
zero. Table rendering bypassed inspection and claims. Automation could mistake a
successful Python process for a verified figure.

The generated program now writes a versioned JSON sidecar with the spec/hash,
data hash/counts, static and inspection findings, panel/metric claim verdicts,
raw/adjusted significance results, skipped checks/outputs, descriptions, and
SHA-256/size evidence for each file actually written. `--json` keeps stdout machine
readable. The Python CLI forwards the policy; the builder returns the report and
attaches it to runtime SpecError exceptions.

`--strict` exits 2 for failed/incomplete checks, including unavailable inspection,
missing uncertainty, skipped significance or requested outputs, and untested
claims. Warning rejection is optional. Runtime/report-write failures exit 1;
default rendering retains the legacy zero exit after successful drawing.
The report records its actual status separately from the selected exit policy.

Claims run per facet/repeated metric instead of on pooled means. Incomplete x
coverage, ambiguous raw duplicates, non-finite comparisons and one-point trends
are untested. Table rendering now runs the same inspector and claim evaluator.
Repeat descriptions use metric names rather than claiming all metrics share the
base y unit. Ungrouped aggregate descriptions describe the plotted summaries.

## Verification

Seven gates passed: 203 Node / 77 Python tests, 15 matching gallery scripts,
16 PNG/PDF renders, 25 recipes, and 7 composition cases. Added 17 runtime tests,
including controlled missing/error/warning inspectors, actual CLI/builder strict
execution, partial coverage, facet/repeat counterexamples, corrected p values,
output byte hashes and failed rendering. Three real generated reports validate
against the public JSON schema (passed, incomplete, failed). Ruff checks pass.

Gallery RGB pixel changes: zero. Corrected descriptions: latency-ranking summary
and faceted benchmarks. Reports correctly flag existing legend/tick layout
errors in 06/10; presentation cleanup remains a separate milestone.
GitHub CI is checked after pushing.
