---
id: 78
slug: dataset-profile-foundation
status: done
priority: P1
title: Expose safe dataset profiles and clean up failed editor uploads
source_idea: User visual-workspace advice following the completed twenty-item review
---

# 78 — Dataset profile foundation

Status: implemented and verified b95f833. Exact main40895079839 all9 and Figure40895079807 pass.
Parent: [visual workspace](../visual-workspace-roadmap.md).

The editor previously returned columns/row counts but omitted the profiler's
broader context. Infinity could break role inference or produce nonstandard JSON;
Parquet dates were not JSON-safe, wide tables caused an unbounded column-pair
repeat scan, and unsuccessful uploads left temporary input folders behind.

## Change

- Return the full profile beside the compatible existing upload fields, using a
  relative session-owned data name instead of exposing the temporary input path.
- Add non-missing, finite and nonfinite counts and clearly finite-only numeric
  summaries. Preserve the actual uploaded bytes, including invalid observations.
  No finite observations means no invented numeric summary or measure suggestion.
- Mark role/suggestion inference as heuristic. Observation counts do not establish
  independent experimental sample sizes or appropriate uncertainty.
- Encode date categories as ISO text and other non-JSON scalar categories as text
  representations. Reject complex-valued measures until their interpretation is
  explicit. Validate strict JSON before publishing an upload identity.
- Bound duplicate-pair exploration to 16 candidates per dimension and return
  truncation metadata. It is exploratory context, not a complete independence test.
- Remove failed upload files before returning the error, for data and palette
  inputs alike.

## Acceptance evidence

Focused real-file/API controls cover mixed missing/infinite values, all-nonfinite
inputs, large finite values, Parquet date categories, wide-table scan limits,
source-byte preservation, canonical `/api/suggest`, and failed data/palette cleanup.
Both edited test modules pass (22 tests), including subnormal means without a
zero-tolerant comparison. Final seven local gates pass:225 Node/1429 Python, zero skips, one existing
upstream MLflow/SQLAlchemy warning;15 baselines,16 renders,25 recipes and7
compositions pass. Changed-file Ruff passes. Exact pushed main/Figure CI must
pass before advancing. This milestone does not add Excel, a new
layout, or a performance improvement claim.
