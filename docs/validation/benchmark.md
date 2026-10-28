# Reproducible research-workflow pilot

This is a **project-authored synthetic comparison**, not an independent scientific
benchmark, external user study or proof of better research outcomes. The
[researcher protocol](researcher-pilot.md) defines the missing external evidence.
Volunteer sessions are deferred at the user's request. The next measured step
uses [published papers and public datasets](published-papers.md).

## Run it

From an installed development checkout:

```sh
python -m pip install ./python
python scripts/research-benchmark.py --out-dir /path/to/empty/pilot-output
```

The output directory must be empty. Each run keeps the exact specs/data, commands'
stdout/stderr, PNGs and GraphUnslopify reports. `benchmark.json` records source
hashes, environment, base revision, tracked diff hash, process exits, actual report
statuses (both attempts, with disagreements surfaced), elapsed seconds and decoded PNG hashes. It runs each arm twice in the
same environment. This tests pixel reproducibility, not equality across renderers
or operating systems. Commit hashes plus the individual source hashes identify
the tested harness, including files not yet committed during development. Installed
Python modules, bundled translator and schemas are fingerprinted separately; the
runner checks that these files remain unchanged during execution. It records whether
the imported package is this checkout, rather than inferring identity from a version.

## Comparators and truth labels

All three arms receive the same CSV, axis/group definitions and mean aggregation:

- **Matplotlib render-only:** a short conventional plotting script. It does not
  claim to verify scientific assertions; its successful render is a weak gate.
- **Matplotlib with assertions:** the same plot plus separately written checks
  for pointwise means, missing reference series and insufficient interval samples.
  This represents a stronger workflow that writes its own validation.
- **GraphUnslopify:** the real local CLI with default strict policy, declared
  claims/intervals and the built-in runtime inspection.

The baseline imports no GraphUnslopify code. Its assertions are project-authored,
not an independent external reference implementation. The baseline draws means;
it does not draw uncertainty bands, so this does not compare interval appearance.
Its assertion arm tests whether a requested interval has enough observations.

[cases.json](../../benchmarks/research/cases.json) freezes eight labelled cases:
two valid controls, one false pointwise comparison, two unavailable checks, one
missing-column execution error and two questions the supplied evidence cannot
answer (true units and causal interpretation). Mean answers are hand-checkable:
base `[1.5, 2.5]`, ours `[4.5, 5.5]`. The requested CI has two seeds per cell in
the regular input and one in the singleton variant.

`blocked` counts a case blocked in either attempt. Repeat disagreements are
reported explicitly and must be investigated. `confirmed_failed`/`incomplete`
count cases with those actual statuses in either attempt. `blocked` measures the process gate. `confirmed_failed` and `incomplete` preserve
the difference between rejecting a false claim and abstaining on unavailable
evidence. Execution errors are counted separately from scientific detections.
An out-of-scope case passing the pipeline does not validate its units or design.
No human effort, statistical power, visual quality or adoption effect is measured.

## Measured results

The first measured snapshot and its environment are in
[pilot-results.json](../../benchmarks/research/pilot-results.json). Treat this
small, deliberately selected suite as a reproducible starting point. Its
limitations and unexpected outcomes must remain visible when presenting results.

| Outcome (cases, both attempts agree) | Render-only | With assertions | GraphUnslopify |
| --- | --- | --- | --- |
| Clean controls accepted | 2/2 | 2/2 | 2/2 |
| False comparison rejected | 0/1 | 1/1 | 1/1 |
| Unavailable checks blocked with abstention | 0/2 | 2/2 | 2/2 |
| Missing-column execution error blocked | 1/1 | 1/1 | 1/1 |
| Outside-scope questions automatically resolved | 0/2 | 0/2 | 0/2 |
| Same-environment PNG pixel reproductions | 7/7 | 7/7 | 7/7 |

There were 48 executions (8 cases × 3 arms × 2 repeats). All outcome repeats
agreed. The absent column produces no PNG, so the pixel denominator is seven,
not eight. GraphUnslopify reports that runtime error as `failed`/exit1; it is not
counted as an additional scientific error detection. The result supports the
value of built-in checks over rendering alone on these cases, **not superiority
over a validated Matplotlib workflow**. No claims about human time saved follow.
