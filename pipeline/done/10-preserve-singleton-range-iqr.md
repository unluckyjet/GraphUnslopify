---
id: 10
slug: preserve-singleton-range-iqr
status: done
priority: P0
title: Preserve absent singleton intervals for range and IQR
source_idea: range-and-iqr-still-fabricate-a-band.md
---

# Preserve absent singleton intervals for range and IQR

All five uncertainty kinds must retain NaN bounds for groups with fewer than two
observations. Range and quartiles currently return finite equal bounds for a
singleton, falsely implying zero spread and suppressing the missing-interval note.

Acceptance:

1. CI, SEM, std, range, and IQR each disclose five absent intervals out of ten on
   the existing single-seed fixture, exactly once per figure.
2. Both bounds are NaN for a singleton range/IQR; repeated values [2, 6] retain
   exact range [2, 6] or IQR [3, 5].
3. All seven checks pass, regenerated scripts match, and GitHub CI is green.

This milestone does not redefine the replicate unit; that is a separate part of
the observation-accounting workstream.

## Verification

149 Node tests passed with no skips; 60 Python tests passed. Typecheck, all
15 committed-script comparisons, 16 render cases, 25 recipes, and 7 composition
cases passed. Known-answer range/IQR bounds were measured by executing emitted
Python. The example PNGs were unchanged; timestamp/ID-only regenerated SVG/PDF
noise was discarded. GitHub CI is checked on the pushed commit.
