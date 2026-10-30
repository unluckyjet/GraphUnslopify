# Keep fitting axis wording within its available margins

Heading checkpointc02c43f passed its local gates but failed the published-paper
CI job. The frozen NIST comparison reported12 unexpected outcomes: Lew, Mavro
and Michelso in the GraphUnslopify arm, both variants and repetitions. All six
clean affected cases retained numerical and physical quality acceptance, but
exact visible-label checks failed because three publisher labels acquired
unnecessary line breaks. Missing-interval cases remained deliberate sentinels.
[The original failed CI evidence](heading-margin-regression/ci-failure.json)
preserves that outcome.

The data rectangle is smaller than the space an axis label can safely occupy.
The fitter now measures the label's actual center against its subplot's vertical
cell boundaries, including free figure margins. Labels that already fit keep
their literal wording and native presentation. Longer headings still wrap, with
complete words, units, original data and source identities preserved.

The frozen protocol, evaluator and producer files are unchanged. Replaying all72
runs passes with the original e310662a protocol hash: each arm accepts18 clean
runs and rejects18 missing-interval controls, with zero execution failures.
These runs represent9 datasets with repeated variants/exports, not72 independent
datasets or a new authoring-time study. Historical published results and clocks
are unchanged. [Current regression replay](heading-margin-regression/certified-replay.json).

Three new native controls retain the exact publisher-style labels. Existing
long/nested, single-column, metric, horizontal, math, unit and strict-negative
cases continue to run. The seed-spread gallery graphic regains its original
12763f8 pixels; this removes its unnecessary unit line break.

Run the complete offline comparison with verified local cached inputs:

```sh
PYTHONPATH=python /path/to/python scripts/certified-benchmark.py \
  --source-dir benchmarks/certified/.cache/sources \
  --prepared-dir benchmarks/certified/.cache/prepared \
  --out-dir /path/to/new-output
```

Use the documented [input preparation](../validation/certified-reference.md) if
those original pinned public inputs are absent. This macOS host requires the
Command Line Tools git directory first in this command's PATH because the system
git launcher exits69; do not change benchmark sources to bypass that environment
problem.

This is a correction to83e2's CI regression. Literal/math context, outside
legends, table context, full83 acceptance and84–89 remain open.

## Local checkpoint verification

All seven gates pass on stable source/test files:234 Node/1659 Python tests,
zero skips/one existing upstream warning.13 focused native cases pass on current,
minimum and fresh installed Python;51 heading/export controls pass on current/
minimum. Source/fresh offline editors pass90 workflows/21 kinds/6 headings/
18 diagnostics, with zero JavaScript errors/external browser requests. Minimum
Python also passes6 heading and18 diagnostic browser cases;19 assets match.

All15 baselines and7 references were genuinely regenerated; gallery passes15/15.
84 of85 stored PNGs keep identical pixels/dimensions. The seed-spread image is
restored to its pre-heading12763f8 pixels. [Verification](heading-margin-regression/verification.json)
and adjacent image/browser/installation JSON preserve the evidence. Exact
new-commit CI remains required before the next implementation.
