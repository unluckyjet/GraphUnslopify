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
