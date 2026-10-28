---
id: 54
slug: statistical-comparison-design
status: done
priority: P0
title: Validate independent and matched statistical comparison designs
source_idea: review2026-10-28 item2 statistical assumptions, independence and inappropriate comparisons
---

# Statistical comparison design

1. Preserve existing independent Welch/rank/permutation results. Add explicit paired design with lexical pair IDs, technical-repeat collapse and matched finite pairs for paired t and exact/seeded sign-flip tests. Report sample/matching exclusions and assumptions; never certify independence/normality from IDs.
2. Reject paired Mann-Whitney, missing/incompatible pairing units, mean-tests on nonmean presentations, grouped-category pooling, self/duplicate comparisons. Report the null actually tested and unit/row assumption.
3. Retain the declared multiple-testing family when some requested tests are unavailable; unavailable tests remain untested/strict-incomplete rather than shrinking correction or silently passing.
4. Independent hand-enumerated and SciPy numerical controls, actual artists/full strict CLI, missing/reordered/lexical IDs, repeated units, singleton/undefined and Monte Carlo controls prove behavior. Existing seven gates, baseline/gallery and refreshed bundle required.
5. Document source-only availability versus immutable PyPI0.8.0. Update roadmap/vault, commit/push this milestone separately and verify exact-commit CI before next implementation.

## Measured acceptance

All seven local gates pass:221 Node (zero skips),1056 Python,15 baseline matches,
16 renders,25 recipes and7 composition cases. Ruff61 and strict gallery15/15 pass.
All60 tracked PNG decoded pixels/dimensions remain identical after regenerating
current baseline/reference provenance. Translator bundle rebuilt from source.

Fourteen new Python controls include hand-enumerated sign flips, a hand-computed
paired t statistic/distribution tail, SciPy matching references, lexical01/1 IDs,
reordered/repeated units, missing/nonfinite pairs, unavailable family members,
Monte Carlo controls and strict real PNG/SVG renders in both orientations.
Four new Node cases cover design/estimator/cohort/family/column refusals. All prior
independent permutation/adjustment/unit tests still pass.

Actual synthetic paired t p=0.06093074307057996 (four units) versus independent
p=0.7508167144003332 with the expected possible-pairing warning. Full source wheel
build and fresh outside-checkout agent/PDF smoke pass offline; the installed wheel
also runs the new paired sign-flip fixture offline with4 matched units/p=0.125.
Source0.8 version labels do not imply publication of these additions: current docs
explicitly require source install; public0.8.0 files/tag remain unchanged.

Review found and corrected complete-case population disclosure and a test naming
mismatch before landing. Exact commit CI is verified after push before advancing.
