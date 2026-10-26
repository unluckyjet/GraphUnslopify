---
id: 30
slug: scaling-fit-reference-contract
status: done
priority: P0
title: Validate log-space fits and report identifiable parameters and honest intervals
source_idea: reference matrix 24 exposes dropped scaling rows empty-fit success and raw descriptions
---

# Scaling-fit reference contract

Measured at 87782be:

- x=[-1,1,2,4], y=[100,2,4,8] passes strict with four rows read but only three plotted;
  its description includes the omitted y=100 and raw mean 28.5 instead of the fitted exponent.
- x=[1,2], y=[3,6], show_points=false passes strict with no points and no fit line.
- A three-point log-space regression x_log=[0,1,2], y_log=[0,1,3] has slope 1.5 and
  SE .2886751346. The current unqualified 1.96*SE margin is .5658032638; the conditional
  two-sided 95% Student-t margin with one residual degree of freedom is 3.6679653624.

## Contract

Use one log-space least-squares estimator for actual fitted curves, numerical descriptions and
per-series/panel fit evidence. Retained x/y must be finite and strictly positive, with known
series/panel labels; explicit author filters run first. Never silently clip/drop invalid rows.
Validate after supported transforms too. Require at least two observations and nonzero log-x
spread to identify slope/intercept. Reject nonfinite derived values and unidentifiable fits.

Two distinct points can identify a point fit, but cannot estimate residual variance. Draw the
actual fitted curve instead of an empty success; keep SE/interval unknown when degrees of
freedom are zero. Default confidence is a conditional 95% Student-t slope interval with n-2
degrees of freedom, not an unlabeled 1.96*SE small-sample substitute. Record method, level,
df, sample count, slope/log-intercept, slope SE, residual SE and nullable bounds explicitly.

Add an explicit interval choice (t95 by default; none for a requested point-only fit). NumPy
provides the point fit and SE when identifiable; use the existing optional statistics/SciPy extra
for Student-t quantiles rather than introducing an unvalidated special-function implementation.
A requested interval that cannot be evaluated must make strict verification incomplete and give
an actionable reason. An explicitly unrequested interval is not fabricated or required. Core
offline point fitting remains available without SciPy. State the log-linear model and independent,
homoscedastic normal-residual assumptions for the conditional t interval; numerical agreement does not establish
these assumptions or nominal population coverage.

Descriptions report the fitted exponent, actual observations, fit/interval method and availability;
they do not substitute raw score means or claim that data prove a power law. Literal series claims
refer to visible observed points, not comparisons of slope parameters. Refuse those claims and
raw-point semantic annotations when points are hidden unless a distinct fit-target contract is
implemented. Direct series labels must attach to actual displayed curve endpoints. Honor valid
continuous overlays without inventing categorical/derived coordinate mappings.

## Evidence to close

Independent hand/SciPy slope/intercept/SE/Student-t cases; actual fit/data artists; row-order
invariance; invalid/empty/singleton/identical-x inputs; genuine two-point point-only and unknown-CI
cases; constant response and overflow; filters/transforms; scoped descriptions/evidence;
visible-point claim controls, labels and exported provenance. Verify actual missing-SciPy and
explicit interval-none behavior, plus fresh installed offline point fitting. Ensure CI render
dependencies include statistics when claiming full confidence-interval execution.

Run required gates, inspect actual exports, refresh affected public illustrations if needed,
update Obsidian and inspect both GitHub workflows after the small push. Matrix 24 remains open.

Primary regression/conditional t-interval reference:
https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.linregress.html


## Verification

Initial contract: 42 of 43 cases failed at 87782be. Final 51 scaling references pass, including
independent hand/Cauchy and SciPy slope/intercept/standard-error/t95 comparisons, actual data
and curve artists, exact row permutations, domains/labels/small samples/overflow/constant
responses, filter-first transforms, optional-dependency and explicit point-only behavior,
scoped descriptions/runtime records, true/false observation claims, named point-only curves,
per-facet fitted endpoint labels, continuous overlays and PNG/SVG provenance. A tiny nonzero
margin is displayed without rounding both confidence endpoints to the same value.

Two inspector regressions fix off-screen minor log ticks being mistaken for colliding text,
while retaining detection of genuinely colliding visible minor labels. The two-point curve,
grouped point-only lines, faceted direct labels and refreshed published illustration were visually
inspected. Public synthetic CSV/spec inputs and emitter/data fingerprints preserve reproducibility.
README historical inverse-normal wording was also corrected to the actual standard-library method.

All seven local gates: 215 Node/349 Python, zero local skips, 15 matching baseline programs,
16 render cases, 25 recipes/seven compositions. Ruff and strict gallery 15/15 pass. The fresh
Python 3.12.14 wheel with packaged Node 24.19 renders a two-point hidden-observations curve
without SciPy and explicitly returns strict incomplete for a requested three-point t95 interval.
External connections are blocked after installation; the optional agent smoke passes. CI render
installs statistics to exercise full conditional intervals. Both GitHub workflows are checked
after pushing; the complete scientific matrix 24 and final delivery scope remain open.

### Matplotlib compatibility follow-up

The first push b532a6e passes Figure CI 40254352440, but general CI 40254352436 exposes real
narrow-log tick collisions on Matplotlib 3.10/Python 3.10 (three tests and its installed-wheel
job fail). All other six jobs pass. This is separate from undrawn-tick phantom collisions.
Sub-decade non-percent scaling axes now use a few numeric major ticks, one fixed scientific
exponent where needed and unlabelled minor marks; data/curve coordinates and log scales are
unchanged. Four display-value references cover normal, boundary-crossing and very small ranges.
The inspector regression forces its drawn/undrawn labels explicitly instead of depending on a
version's default formatter, and the real visible-minor-collision control remains.

All seven local gates pass again: 215 Node/353 Python, zero skips, 15 matching baselines,
16 renders, 25 recipes/seven compositions; Ruff and strict gallery15/15 pass. All eight targeted
compatibility cases also pass locally with Python3.10.22/Matplotlib3.10.9/NumPy2.2.6/pandas2.3.3.
The refreshed published image's source/data fingerprints pass and actual plots were reviewed.
Fresh Python3.12 wheel/no-SciPy offline/agent smoke passes again. Local managed Python3.10
cannot create its ensurepip environment; clean Python3.10 installation remains a required
GitHub check rather than a claimed local result. Both workflows are checked after the fix push.
