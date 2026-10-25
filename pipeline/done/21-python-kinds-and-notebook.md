---
id: 21
slug: python-kinds-and-notebook
status: done
priority: P1
title: All Python figure kinds and an executable packaged notebook
source_idea: accepted lightweight notebook and Python integration roadmap
---

# Python kinds and notebook integration

Expose all 21 canonical compiler kinds as named Figure constructors and a public Kind Literal.
Infer regular JSON/Parquet input formats from their suffixes. Exercise the adapter against every
canonical recipe and an actual JSON render; do not introduce another emitter.

Ship a cleared public notebook in the wheel. The notebook CLI copies it without overwriting files
and optionally executes it through the current Python environment, without changing user kernel
specifications. Preserve failed-cell evidence and return an actionable error. Notebook extras
supply JupyterLab/kernel/execution tooling; existing notebook editors can use the base package.

## Verification

A real kernel executes ten cells: 48 public synthetic observations, four declared seed units per
point, mean/interval PNG/SVG/PDF, an embedded image, correct sample counts, an interval-overlap
caveat, portable spec/program export and an expected false-claim rejection carrying its report.
The selected Python executable is checked; explicit local API selection works even with an
unreachable HTTP API configured. The image was visually inspected. Source/package copies match;
shared Ruff import classification keeps notebook formatting consistent.

All local gates pass: 214 Node (zero skipped), 134 Python, 15 baselines, 16 renders, 25 recipes,
seven compositions. Fresh offline wheel smoke also copies the packaged notebook. CI expands the
full Python suite to 3.10/3.12 with notebook dependencies. Figure CI's actual consumer now passes
its previous report as a baseline and checks changed claims with unchanged data/PNG pixels.
CI is checked after pushing; agent/local-editor integration and the remaining roadmap stay active.
