---
id: 73
slug: frozen-benchmark-measurement
status: ready
priority: P1
title: Freeze external-reference measurements before evaluating plotting workflows
source_idea: review2026-10-28 item17 measured errors development time reproducibility figure quality with immutable prior rules
---

# Frozen benchmark measurement

1. Preserve corpus72's complete selection and externally certified answers. Freeze
   machine-readable case/arm/variant/repeat order, numerical tolerances, exact
   labels/export sizes and quality/reproduction/timing definitions before NIST
   product outputs are evaluated. Bind evaluator/source hashes, refusing changes.
2. Independently capture actual save-time point/interval artists, finite/missing
   evidence, drawn text and file identities. Decode real PNG/SVG/PDF and refuse
   absent/overwritten/repeated evidence. Measure numeric mean/endpoints/half-span
   against external decimal facts with printed/input-float/coordinate allowances.
3. Verify the evaluator with independent synthetic controls: wrong/missing/
   invisible/duplicate/clipped marks, large offsets, nonfinite measurements,
   corrupt/changed/missing outputs, physical font scaling, process failure and
   overwrite refusal. No NIST product evaluation before the commit is frozen.
4. Define honest development sessions: one unblinded coding assistant, append-only
   live clocks before arm-specific editing, all failed attempts retained, stop
   after nine clean tasks succeed; fixed arm order/shared costs disclosed. Human
   development time/usability remain unmeasured. Machine timings are separate.
5. Seven gates and exact main/Figure CI before workflow adapters/actual benchmark.
   Item17 remains open until execution/metrics/evidence are delivered;18 deferred.

## Prior checkpoint

856f057dcc8e51edae806157a8e16bc503507228 main40840310179 all9/Figure40840310204
passed. Both downloaded CI preparation records exactly match local source/CSV
hashes; an additional network-blocked all-nine preparation also matches.

## Implementation and focused evidence — 2026-10-29

Frozen v1 protocol binds source/evaluator/worker hashes and declares all nine
cases, two arms/two variants/two repetitions, exact labels/sizes, coordinate
allowances, quality proxies, timing and live development-session rules.
`measurement.py` captures actual save-time artists and drawn text; worker retains
script exits/errors and export identities. Decoded files must match their observed
save hashes; missing/damaged/overwritten files and absent repeats do not pass.

Sixteen synthetic controls pass, including actual subprocess exits0/5 and retained
measurement overwrite refusal. Additional independent manual primitive5 +/-2
produces measured mean5/low3/high7/half-span2 across all three exports. All quality
proxies pass (minimum text10.3239pt at target width, no overlap candidates); actual
PNG inspected. This is evaluator validation, not NIST product accuracy evidence.
All seven local gates pass:225 Node/1390 Python, zero skips/one upstream
MLflow/SQLAlchemy warning;15 baselines/16 renders/25 recipes/7 compositions.
Ruff check/format96 pass. No NIST plotting outputs have been evaluated. Exact
pushed main/Figure CI must pass before producer authoring/evaluation.
