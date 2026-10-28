---
id: 57
slug: comparison-numerical-stability
status: done
priority: P0
title: Keep comparison statistics stable under large shared offsets
source_idea: measured paired comparison shifted p1 versus centered p0.5 after statistical-design milestone54
---

# Stable comparison statistics

A real generated paired sign-flip test on left1e16 and right[1e16+2,1e16+2,1e16,1e16]
returns1 while the equivalent centered problem returns0.5. Subtracting separate means
lost a representable within-pair difference. Fix this before moving to the next review item.

1. Use matched differences for paired statistics, stable common centering for independent
mean statistics and a bounded working scale. Keep observations/artists unchanged; rank
comparisons keep original values. Unrepresentable differences abstain rather than invent p.
2. Hand-enumerated exact tests and independent SciPy/hand t references show translation/
positive-scale invariance, zero-gap behavior, Monte Carlo nonzero tails and explicit extreme
refusals. Preserve ordinary independent answers and multiple-test correction.
3. Run seven local gates, Ruff/gallery, rebuild bundle, verify actual installed behavior;
commit/push this fix separately and check exact CI. Record prior failed/corrected outputs.

## Verified correction

Before: actual emitted paired p1 versus centered p0.5. After: both0.5; independent
shifted/centered both30/70. Fresh outside-checkout source-wheel emitters reproduce
both corrected answers with external runtime networking blocked. Fresh agent/PDF
smoke also passes. Ordinary input answers, null cases and Monte Carlo nonzero tails
remain covered by the previous tests.

Eight new parameterized controls supplement the14 design tests: paired/independent,
t/permutation, large common offset, large/small positive power-of-two scale, and
finite inputs whose subtraction is unrepresentable. Such differences return
unavailable instead of a fabricated p-value. Rank tests retain original observations.

All seven local gates pass:221 Node/1064 Python, zero local skips/warnings;15 baseline
scripts match,16 renders/25recipes/7 composition cases and strict gallery15 pass.
Ruff61 check/format and current doc links pass. Rebuilt bundled translator; no
legacy artifact regeneration needed because all committed baseline scripts still
match the emitter. Public0.8.0 remains unchanged. Exact CI checked after push.
