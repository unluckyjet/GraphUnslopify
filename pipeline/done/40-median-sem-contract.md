---
id: 40
slug: median-sem-contract
status: done
priority: P0
title: Refuse mean-standard-error widths around median summaries
source_idea: matrix24 line bar forest table accept median2 with mean SEM sqrt19over3 for observations1 2 9
---

# Median and SEM

Measured atf456547: line/bar/forest/table all accept aggregation median plus uncertainty sem.
For1/2/9, each draws median2 with width2.51661147842358, the sample standard error of the mean
sqrt(19/3). That formula does not estimate the standard error of a sample median. No warning
or refusal identifies the estimator mismatch. SEM is explicitly defined for the mean in the
primary SciPy stats.sem reference. Refuse median+SEM semantically and in generated summary
execution; do not silently substitute a different center or uncertainty method.

Keep mean SEM and the existing percentile-bootstrap median CI working, including declared
independent units/technical repeats. Verify independent hand known answers, raw/named-unit
cases, direct summary refusal and strict generated execution. Recommend an explicit bootstrap
CI for median uncertainty, distinguish IQR as observational spread, and ensure missing-
aggregation guidance does not recommend an unsupported median+SEM combination.
Run seven gates, gallery, fresh installed proof, Obsidian and both workflows. Full matrix24
remains open.

## Verified implementation (2026-10-26)

Median+SEM is an explicit median_sem_unsupported error on line/bar/forest/table. Generated
summaries raise rather than attach a mean's SE to a median. Missing-aggregation SEM guidance
only recommends a mean. Existing mean SEM and requested median bootstrap CI remain unchanged,
including named units/technical repeats.33 controls pass; initial32 measured16 failures/
16 existing positive passes. Known1/2/9 unit values retain mean4±sqrt(19/3), or median2 with
seeded95% bootstrap endpoints1/9. No interval/center is silently substituted.

Seven gates215 Node/764 Python, zero local skips/warnings, gallery15/15, Ruff and fresh
external-network-blocked wheel/agent pass. Installed source independently verifies both
valid estimators and semantic/direct summary refusal. All baseline scripts/assets and51
published docs/baseline PNGs remain byte-identical. The direct literal verify-code count
is80. Both workflows require verification after push; complete matrix24 remains open.
