---
id: 12
slug: respect-declared-repeat-units
status: done
priority: P0
title: Honor declared replicate units instead of overweighting technical repeats
source_idea: runtime duplicate-seed probe and accepted statistical-safeguards roadmap
---

# Respect declared repeat units

A fixture with ten zeros from seed 0 and one value 10 from seed 1 currently
reports mean 10/11 despite uncertainty.over=seed. The contract must give the two
named units equal weight: mean 5. Independence remains an author assumption.

Acceptance:

- Collapse repeated measurements within each point/group/panel/unit using the
  requested mean or median before computing a center or interval.
- All five interval kinds match known two-unit bounds; repeated rows from only
  one unit retain missing bounds. Without over, rows retain their stated role.
- Counters use unit IDs when named, disclose missing IDs, and preserve panels.
- Non-finite numeric values do not contaminate summaries or sample counts.
- Reject an over key equal to a point/group/facet key and reject uncertainty on
  sum/count rather than silently giving those summaries inappropriate intervals.
- Existing fixture/renderer behavior remains verified through the seven gates;
  numerical reference tests execute the generated Python. Check GitHub CI after push.

## Verification

All five interval kinds match known two-unit bounds around mean 5 rather than
the old 10/11 row-weighted mean. Median-of-unit-medians is checked separately.
One-unit technical repeats retain NaN bounds; missing IDs are disclosed, and
absent/all-missing identifier columns fail clearly. A real rendered significance
fixture spies on its test inputs: two values per arm with means 5 and 5. Facet
IDs remain separate; non-finite values do not contaminate centers or counts.

Seven local gates passed (186 Node / 74 Python, 15 scripts, 16 PNG/PDF renders,
25 recipes, 7 composition cases). Gallery RGB pixels were unchanged; the named
unit metadata was refreshed. GitHub CI is checked after pushing.
