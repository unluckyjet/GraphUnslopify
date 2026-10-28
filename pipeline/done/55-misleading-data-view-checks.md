---
id: 55
slug: misleading-data-view-checks
status: done
priority: P0
title: Report selected data and hidden coordinates in rendered views
source_idea: review2026-10-28 item4 deceptive scaling, selective omissions, annotations and exaggeration
---

# Data versus visible presentation

Inspect real selected/retained numeric observations against requested scales/limits, source filtering and annotations. Preserve deliberate filters but disclose exclusion scope and denominator; distinguish unavailable data from unseen/clipped data and flag invalid log domains. Detect independently measured misleading examples and retain legitimate controls. Do not infer intent or label all filtering deceptive. Extend current geometric inspector/contracts rather than add a second emitter. Specify exact policy/findings after source assessment, then verify seven gates/gallery, commit/push and check exact CI.


## Assessed acceptance (visibility milestone; annotations continue in58)

1. Rectilinear line/scatter/segment/polygon coordinates report finite/unavailable/outside-axis
counts and actual physical limits/scales. Count artist coordinates, not source sample sizes.
2. Nonpositive finite coordinates on log axes are errors, including uncertainty endpoints.
Masked/nonfinite rows do not become observed errors; symlog and positive domains remain valid.
3. Ordinary cropped anchors warn without inferring intent or absence of all visible ink.
Clip-disabled artists, blended reference transforms and intentional axis-break halves avoid
false clipping claims; unsupported/custom/inset scopes remain explicit.
4. Declared filters retain each step's before/after/removed counts and total selected source
rows in machine evidence and alt text. Explicit numeric view limits are disclosed in the
encoding/PNG/SVG/HTML narrative, without claiming underlying statistics use only visible data.
5. Real strict CLI rejects the previous passed negative-log case; cropped scatter remains a
review warning (optionally rejected by fail-on-warning). No-op/empty filters and masked/rotated
views have independent controls. Seven gates/gallery/bundle, fresh wheel and exact CI required.

Measured before: negative-log line passed/exit0; clipped scatter passed/exit0 with no warnings.
Atx100 annotation on x1..3 also passed; that separate58 contract remains open.


## Measured acceptance

Thirty new controls pass (71 with existing inspector controls): actual native artists,
masked/transparent points, unused polygon closing placeholders, line/point/band/stem
log domains, cropped/inverted/clip-disabled/split views, numeric-x zoom/calendar controls,
per-filter/no-op/empty/multi-panel counts, embedded descriptions and older-checker refusal.
Marker density no longer counts unavailable or off-view centers as visible ink.

All seven local gates pass:221 Node/1094 Python, zero local skips/warnings,15 baseline
matches/16 renders/25 recipes/7 composition cases. Ruff63 and gallery15/15 pass.
Seven owned reference fingerprints regenerated before final full Python verification;
all60 existing PNG dimensions/decoded pixels remain identical. Bundled compiler rebuilt.

Actual freshly installed source-wheel agent/PDF smoke passes offline. Four additional
installed probes: negative-log data rejected(exit2/failed), cropped coordinates warned,
three source rows excluded with1of4 selected disclosed, and numeric-x zoom warned.
No new PyPI publication is claimed. Annotation resolution remains open in58; review
item4 is partial until that separate contract is verified. Exact CI checked after push.
