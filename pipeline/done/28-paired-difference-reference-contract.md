---
id: 28
slug: paired-difference-reference-contract
status: done
priority: P0
title: Describe and account for the matched units actually used in paired differences
source_idea: independent reference matrix 24 exposes raw-score descriptions and silent pair exclusions
---

# Paired-difference reference contract

At 6626fb3 an eight-row fixture plots differences [4,6] but describes raw scores 5..1000
with mean 148. Missing pair IDs disappear in pivoting; unmatched units lack explicit accounting.
Numeric condition 0 cannot match the declared baseline "0".

Use one paired estimator for marks, intervals, descriptions and pair-specific runtime evidence.
Each unit/condition cell averages its finite technical measurements; units then have equal
weight in condition-minus-baseline differences. Disclose this collapse and every unmatched unit.
Validate pair/condition/panel identifiers before grouping. Missing measurements may omit a unit
from a particular comparison, with explicit counts; invalid nonmissing/nonfinite values fail.
Filters run first. No baseline, no alternative or no complete pair must not verify an empty plot.

Expose total units, matched pairs, baseline-only/candidate-only/neither units and collapsed repeats
per comparison and panel. Each displayed comparison shows its n; singleton intervals remain
unknown and make strict verification incomplete. Descriptions summarize actual differences and
the existing fixed-seed 2,000-resample 95% percentile mean interval. They must not summarize raw
score distributions. Unsupported groups, raw-y transformations, overlays and literal series
claims fail explicitly instead of running on a different quantity. Numeric baseline labels may
match their unique string representation; ambiguous representations fail rather than merge.

Verify independent hand answers and actual artists, correct unit pairing under permutation,
technical repeats, missing/unmatched measurements, invalid identifiers/data, singleton/empty
controls, numeric/ambiguous baseline identity, faceted evidence and exported provenance. Keep
the global CSV leading-zero/category/filter contract in matrix 24 open. Run required gates,
review actual exports, update Obsidian and check both CI workflows after the small push.


## Verification

The initial 27-case contract failed all 27 at 6626fb3. Final 39 cases pass: independent hand
values, actual points/centers/intervals/tick counts, all 24 four-row permutations, unit-weighted
technical repeats, missing/unmatched data, identifiers, empty/singleton/comparison controls,
numeric/ambiguous baseline representation, no author-row mutation, overflow, filtering,
facets, static refusals and PNG/SVG provenance. A skewed five-unit actual interval also matches
SciPy 1.18.1 percentile bootstrap under the declared seed/resample count (mean 6.2, bounds 2..11.6).
Source percent units are described as percentage points; log y is refused so zero and negative
differences are not silently hidden. Reports retain interval method/level/resample count/seed.

All seven local gates pass: 215 Node/248 Python, zero local skips, 15 unchanged baseline
programs, 16 render cases, 25 recipes/seven compositions. Ruff and strict gallery 15/15 pass.
Four actual single/faceted/singleton/empty-comparison PNGs were visually inspected. A fresh
macOS/Python 3.12.14 wheel renders the six-row hand fixture offline, with mean 5/n=2 and both
unmatched units disclosed; the optional local agent session also passes with external
connections blocked after installation. Both GitHub workflows are checked after the push.
The complete independent matrix (24), including global CSV identities, remains open.
