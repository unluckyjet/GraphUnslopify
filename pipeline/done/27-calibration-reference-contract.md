---
id: 27
slug: calibration-reference-contract
status: done
priority: P0
title: Validate probability domains and use binned calibration evidence consistently
source_idea: scientific reference matrix 24 exposes invalid calibration domains and raw-row claims
---

# Calibration reference contract

At bca31c0, probabilities [-0.1,1.4] and outcomes [0,1.5] draw outside the valid domain while
printing ECE 0.1. Descriptions summarize the raw probability distribution, not plotted calibration.
Raw-y claims can certify a comparison that is false on the displayed bin frequencies.

Use one binned calculation for actual points, occupied counts, empirical ECE, descriptions and
claim inputs. Enforce retained probabilities finite within [0,1], binary observed outcomes,
nonmissing model/panel labels and nonempty input. Author filters run first. Uniform bins use
right-closed interior boundaries with zero included; omit empty bins rather than fabricating rates.
State this convention and the intentional change from the old half-open interior assignment.

Descriptions and labels report non-rounded-to-zero ECE, observations, bin occupancy and plotted
ranges. Numeric predicates compare actual displayed bin frequencies, never raw outcomes; genuinely
unaligned probability means stay UNTESTED. Only within-bin differences of at most 1e-12 due to
floating summation are aligned, deterministically and without moving actual plotted points/ECE.
Undefined raw-y transformations and ambiguous claim field roles fail explicitly.

Verify independent hand answers, endpoints/boundaries, empty bins, row permutations, tiny nonzero
error, invalid data, filter/domain order, aligned/false/unknown and panel-scoped claims, actual
PNG/SVG provenance and installed-wheel execution from probability/outcome data without a y column.
Actual faceted legends must report each panel's own ECE; direct labels use derived endpoints/error
without a raw y column. Visual inspection exposed first-panel ECE being reused across the figure.
Record an independent scikit-learn probe; automated hand cases require no optional oracle. Tighten
existing survival artist comparisons to explicit absolute 1e-12 tolerance. Run required gates,
inspect actual figures and both CI workflows. Keep the complete all-kind matrix (24) open.


## Verification

Final local evidence: 31 calibration regressions; all seven required gates pass with 215 Node
and 209 Python tests, zero skips in the local environment. The 15 committed baseline programs
remain unchanged; 16 render cases, 25 recipes, seven compositions and strict gallery 15/15 pass.
Ruff passes. Independent boundary points match scikit-learn 1.9.1; ECE is checked by hand, not
claimed as a scikit-learn output. Grouped and two-panel PNGs were visually inspected, including
different per-panel ECE and nonoverlapping legends. A fresh macOS/Python 3.12.14 installed wheel
renders the four-record ECE=0.5 fixture without a raw y column or optional oracle, with external
connections blocked; its optional local agent session also passes. Existing survival numerical
comparisons now use explicit absolute 1e-12 tolerances. General and Figure CI results are checked
after the push and recorded in Obsidian/implementation progress.
