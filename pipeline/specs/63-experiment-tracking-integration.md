---
id: 63
slug: experiment-tracking-integration
status: ready
priority: P1
title: Log verified figure audit evidence to explicit MLflow experiment runs
source_idea: review2026-10-28 item9 experiment tracking continuation after workspace62
---

# Explicit experiment tracking

1. Optional MLflow SDK/CLI integration connects current strict audit/workflow runs
   to an explicitly chosen experiment/store. Preserve existing client run context;
   do not silently select hosted services or change global tracking configuration.
2. Record actual statuses/acceptance, counts/fingerprints and selected verified
   figure/report/comparison artifacts. Failed scientific runs remain failed;
   successful logging is not scientific acceptance. Do not upload raw input CSVs,
   arbitrary caller directories, credentials or stale/tampered artifacts.
3. Actual local-store retrieval proves figure bytes, status/claim rejection,
   report recovery and context isolation offline. Optional dependency absence and
   transport errors stay actionable/nonzero; no mocked-only delivery claim.
4. Document notebooks, existing training loops and CLI alongside workspace62,
   run seven gates, fresh installed optional-extra checks and exact pushed CI,
   then reassess full item9 against all four requested research environments.

## Implementation checkpoint (2026-10-28)

Explicit log_mlflow/track-mlflow accepts saved audit or workflow evidence and
requires a caller-chosen URI plus existing experiment/new owned run or existing
running run. Source snapshots and hash-verified static exports are staged before
opening the destination; no raw inputs, sources, logs, credentials or arbitrary
folders are selected. Machine comparison evidence is copied from the saved audit;
unhashed interactive HTML is not selected. Per-attempt manifests preserve status,
acceptance and fingerprints, and source rejection remains exit2 after a successful
transfer. Existing fluent context/URI and caller run lifecycle are preserved.

Eighteen real SQLite/artifact controls pass: exact retrieval, two figure kinds,
failed claims/comparisons, preparation/pre-audit failures, explicit store distinct
from active training, damaged/explicit-root refusal, unavailable extra and injected
transport errors. Failure tags retain the current source acceptance and attempt
prefix. Fresh final wheel with agent/PDF/environment/comparison/workflow/tracking
passes outside the checkout with external runtime connections blocked. MLflow3.17.2;
one upstream SQLAlchemy noload deprecation warning is retained, not suppressed.
Final seven-gate run passes222 Node/1277 Python, zero skipped tests,15 baselines,
16 renders,25 recipes/seven compositions and Ruff78 lint/format. The single
upstream warning remains. Exact pushed CI is checked before closing this spec.
