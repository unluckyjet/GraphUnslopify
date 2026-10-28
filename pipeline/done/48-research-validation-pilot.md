---
id: 48
slug: research-validation-pilot
status: done
priority: P1
title: Establish reproducible comparison and prepare external researcher testing
source_idea: user 2026-10-28 adoption-focused review, follow-up items17/18
---

# Research validation: first milestone

This completes the local pilot and study preparation, **not** independent
scientific validation or external user testing.

The committed runner executes8 frozen cases in three arms twice (48 executions):
ordinary Matplotlib, independent-of-product-code application assertions, and the
actual strict CLI. It preserves actual evidence, fingerprints both harness and
installed implementation, rejects reused output folders, reports both attempts
and surfaces disagreements. Numeric answers are hand-checkable and truth labels
separate valid, invalid, unavailable, execution-error and outside-scope cases.

Measured: both assertion-enabled Matplotlib and GraphUnslopify reject1/1 false
comparison and abstain on2/2 unavailable checks; both clean controls pass. All
three arms block the missing-column execution error and reproduce7/7 comparable
PNG pixels. No outcome disagreements. Neither can establish true units or
causality from supplied evidence. No superiority over a validated Matplotlib
workflow or researcher time/quality improvement is claimed.

An external pilot protocol covers real participant projects, alternated workflow
order, independent task labelling, clean controls, failures/help, correct-export
time and anonymized observations. No participants enrolled or contacted, and no
feedback fabricated. Independent held-out benchmark and real sessions stay open.

The independent audit identified first-repeat-only accounting and incomplete
installed-code provenance. Both are repaired, with a mixed-repeat failure control.
The measured snapshot is benchmarks/research/pilot-results.json. Required seven
checks, Python lint/format and exact-push CI must pass before the next milestone.
