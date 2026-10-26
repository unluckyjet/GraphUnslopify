---
id: 29
slug: qq-reference-contract
status: done
priority: P0
title: Use accurate Q-Q quantiles and distribution quartiles with explicit sample evidence
source_idea: reference matrix 24 exposes inaccurate normal tails and empty singleton success
---

# Q-Q reference contract

At 6ca5e26 the normal approximation has max absolute theoretical-coordinate error
0.0072563687 against SciPy at 10,000 Blom positions despite a claimed ~0.002 bound.
A singleton produces no marks but strict exit 0/status passed. The reference line also uses
quartiles of the finite theoretical grid instead of the reference distribution's quartiles.

Use accurate standard-library normal inverse probabilities, retain the declared Blom positions,
and fit sample linear quartiles to population reference quartiles at probabilities .25/.75.
Use one estimator for marks, line, descriptions, literal claim inputs and derived labels.
Allow missing measurements only with explicit accounting and at least two finite observations
per plotted series/panel; reject invalid nonmissing values and missing labels before grouping.
Explicit author filters run first. Constant samples remain visible with an honest shape warning.

Claims compare actual sample quantiles at identical theoretical coordinates; they are not
normality/equivalence tests. Different grids are untestable, not silently interpolated. Direct
labels and semantic annotations attach to derived coordinates without a raw x column. Preserve
meaningful per-series normalization, disclose it as unitless, and explicitly refuse raw-x
transforms/overlays or ambiguous claim roles. Respect valid axis scales without hiding invalid
log-domain values; use enough reference vertices when a non-linear scale changes its geometry.

Verify hand uniform/quartile answers, independent SciPy normal values and actual artists,
tail precision, permutations, missing/invalid/degenerate samples, filters/normalization,
true/false/unknown/panel-scoped claims, labels/annotations, exports and installed offline use.
Run the required gates, inspect real plots, update Obsidian and check both CI workflows after
the small push. Keep the complete 21-kind reference matrix 24 open.


## Verification

The initial 37-case contract failed all cases at 6ca5e26. The final 48 cases pass: hand uniform
positions/population-quartile line, independent normal quantiles/line, n=2..10,000 actual artists,
extreme probabilities, 24 row permutations, empty/singleton/invalid/missing/constant samples,
filtering/normalization/units, true/false/unknown/panel-scoped claims, direct labels on every facet,
derived/crossover annotations and unavailable coverage, log-domain/reference geometry,
overflow and PNG/SVG provenance. The measured 10,000-point max absolute normal-coordinate
error fell from 0.0072563687 to 1.7763568394e-15 against SciPy 1.18.1.

The README Q-Q PNG is refreshed from a committed 160-observation synthetic fixture/spec.
Its data and emitted-source fingerprints are regression checked. Six synthetic variants plus
the published illustration were rendered and visually inspected. A benign pandas downcast
warning in the prior paired numeric-ID fixture was removed by constructing numeric IDs explicitly.

All seven local gates pass: 215 Node/296 Python, zero local skips; 15 baseline programs unchanged,
16 render cases, 25 recipes/seven compositions. Ruff and strict gallery 15/15 pass. Fresh
macOS/Python 3.12.14 wheel renders Q-Q observations without a raw x column or optional SciPy,
with external connections blocked after installation; the optional agent check passes too.
Both GitHub workflows are checked after the small push. Scientific matrix 24 remains open.
