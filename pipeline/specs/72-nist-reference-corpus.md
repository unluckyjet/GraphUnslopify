---
id: 72
slug: nist-reference-corpus
status: ready
priority: P1
title: Freeze a complete external certified-reference corpus before benchmark evaluation
source_idea: review2026-10-28 item17 independent reference answers realistic research data comparison timing reproducibility quality
---

# Freeze a complete external certified-reference corpus before benchmark evaluation

1. Pin all nine NIST StRD univariate sources, publisher order/strata, byte hashes,
   counts and independent certified decimal values before evaluating tool outputs.
   Distinguish laboratory data, general-interest data and generated challenges.
2. Ship an explicit-download/default-offline preparer with bounded retrieval,
   original hash/header/denominator checks, deterministic token-preserving CSVs,
   complete-corpus validation and refusal to overwrite changed source/old evidence.
3. Keep source/observation files local with clear publisher attribution/rights;
   do not silently apply the project's MIT license to external data. Retain only
   preparation metadata in CI artifacts. Test real publisher inputs online/offline
   and meaningful transport/semantic corruption/refusal cases.
4. Document the remaining measurement contract and limits. Preparation is not a
   product accuracy/timing/quality result, independent evaluation or human user study.
   Broader item17 stays open; volunteer18 stays user-deferred.
5. Prior71 exact e8c6f7d main40835074311 all9/Figure40835074261 verified before72.
   Run seven gates, commit/push this coherent checkpoint, verify exact main/Figure
   CI, then implement/freeze the actual benchmark before evaluating product outputs.

## Implementation and measured evidence — 2026-10-29

Implemented `benchmarks/certified/{sources.json,corpus.py,NOTICE.md}`,
`scripts/prepare-certified-data.py`, explicit online/default-offline CI preparation
and metadata-only artifacts. Nine original publisher inputs fetched successfully
with the documented research-client identity; online/offline metadata and CSV
bytes agree. Independently compared every derived value string, order and row ID
against all8,574 original observations; all nine source/CSV hashes pass.
Durable ignored local cache is `benchmarks/certified/.cache/`; inputs are excluded
from Git and CI artifacts. No product evaluation was conducted.

Eleven controls cover transport/semantic corruption, denominator/reference/identity
mismatches, decimal/order preservation, offline/no-refetch behavior, changed-cache
and evidence overwrite refusals, and complete-corpus membership. Seven local gates
pass:225 Node/1374 Python, zero skips/one upstream MLflow/SQLAlchemy warning,
15 baseline/16 render/25 recipe/7 composition cases. Ruff check/format93 pass.
Exact pushed main/Figure CI remains to be verified before benchmarking.
