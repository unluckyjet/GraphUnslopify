---
id: 26
slug: kaplan-meier-reference-contract
status: done
priority: P0
title: Correct tied risk sets censor tails and derived survival evidence
source_idea: independent reference matrix 24 exposes row-order-dependent Kaplan-Meier estimates
---

# Kaplan–Meier reference contract

At be3649d, durations [1,1,2] with event flags [0,1,1] plot survival 0.5 at time 1.
Swapping the tied rows to [1,0,1] changes it to 2/3. Hand risk-set arithmetic and independent
SciPy right-censored ECDF both give 2/3. Current censor-only tails can extend beyond their drawn
line, input domains are not validated, and generic descriptions/claims use a raw y field even
though survival is computed from duration/event data.

Use one product-limit estimator for drawing and derived descriptions/claim inputs. Apply tied
events to the entire risk set immediately before their time, then remove all tied observations.
Draw through all observed follow-up (including censor-only cohorts/tails), beginning at time zero,
and place censor markers on the post-event right-continuous estimate. Reject missing/nonfinite/
negative times and nonbinary event flags after intentional filtering; do not silently discard or
threshold them. Cohort/panel assignment must not silently omit unknown labels.

Descriptions report actual observations/events/censors, final observed survival and reached or
unreached median. Claims evaluate the plotted right-continuous estimates on a shared time grid,
without extrapolating short-follow-up cohorts or certifying raw event flags. Undefined transforms
and ambiguous field roles fail explicitly. These remain literal numeric predicates, not log-rank
or other inferential comparisons. State the right-censoring/independent-record assumptions and
absence of KM confidence intervals.

Verify actual artists against hand/SciPy references, all permutations of tied rows, censor marker
locations/tails, zero time, all-event/all-censor cohorts, invalid domains, grouped/faceted claims,
false and untested controls, actual export metadata and strict failure/no-artifact behavior. Install
the statistics oracle in both supported Python CI jobs. Pass existing gates and inspect real figures
and both CI workflows before the next milestone. Keep the full reference matrix (24) open.

## Measured result

One shared validated estimator now supplies marks, descriptions and literal claim frames. Time ties
are grouped before the risk set changes; right-censor tails and all-censored curves remain visible.
A fixed precision policy prevents floating roundoff at 50% from moving the first median crossing.
Cohort values beyond their own observed follow-up stay unknown to comparison predicates.

The initial focused suite recorded 20 failures/one pass against be3649d. The final 34 tests compare
actual artists/censor markers with independent hand/SciPy values, exercise every permutation of the
three-record tied cohort, domain/empty/label guards, explicit filtering, absent/raw y columns,
positive/false/untested and panel-scoped claims, metadata and median boundaries. Strict checks use
exit 2 for a failed/untested claim; input runtime failures use exit 1 with no artifacts. Both grouped
and faceted exports were visually reviewed. A separate even-sample probe found 49/100 medians one
record late before the rounding fix; the added 24-record and early-censor controls cover this case.

Seven gates pass: 215 Node (zero skips), 178 Python, 15 matching baseline programs, 16 renders,
25 recipes and seven compositions. Ruff and strict gallery 15/15 pass. Other kinds' baseline source
is unchanged. Fresh installed optional-agent wheel renders the three-record survival case from
raw time/event CSV without a y column, with external connections blocked. Both Python CI jobs now
install the optional SciPy oracle (1.11+) while base rendering still needs no SciPy. The broader
independent reference matrix (24), naming/versioned release and final audit remain open.
