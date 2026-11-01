# Public-workspace comparison implementation

This is an implementation checkpoint, **not a completed comparison**. The original
[v1 protocol snapshot](README.md), all 37 frozen assets and numerical cases remain
unchanged. Formal timing still requires both complete producers, controllers and
evaluator, untimed parity and a separate public Git/CI implementation seal.

## Implemented baseline producer

`matplotlib_producer.py` independently selects finite CSV observations, calculates
descriptive means/sample SD with Python statistics, evaluates the declared claims,
and draws the four preregistered bar/scatter tasks. It writes the requested
PNG/SVG/PDF files, actual labels/units, scientific and publication-legibility
findings, input/spec/program/export hashes, environment metadata and run history.
Only the legibility inspector is shared with GraphUnslopify. The older papers
reference supplies actual artist measurement functions; its numerical/drawing
functions are not used by this producer.

Warm sessions reuse content-keyed calculations; every request evaluates claims,
draws, inspects and writes new current evidence. Executed producer/measurement
sources are owned copies. Current acceptance is checked against separate run
receipts and current data, reports, specs, exports and producer bytes. These are
local trusted benchmark fixtures, not a signed artifact format or malicious-owner
authentication. Safe paper-level render reuse is still to be implemented.

```sh
python scripts/check-workspace-matplotlib.py --out /tmp/my-new-baseline-check
```

This untimed check performs 37 frozen numerical/export cases plus one clean
owned fixture for four integrity controls (38 native producer executions). It
checks actual saved artists and counts, units, PNG DPI, PNG/SVG/PDF widths, cache
reuse without acceptance reuse, and rejection of changed PNG/report/input/program
bytes. It does not fill any formal comparison/reliability/reproduction/GUI
denominator. Separate negative tests reject a real omitted scatter point, a real
mean-only image for an SD task, a probe missing a required measurement, and a client-mutated returned report
trying to change the separately stored expected PNG checksum.

An earlier untimed attempt found four narrow-bar layout collisions. They were
fixed by reserving figure-level legend space and rotating category labels, with
the same inspection thresholds. Its original sources, outputs and failures are
retained in the project evidence vault. These are implementation corrections
before the formal implementation seal, not post-result tuning.

## Prospective policy clarification

[The v2 policy clarification](policy-clarification-v2.json) preserves v1 and changes
only how its paper execution/reuse expectations apply. Those counts describe
GraphUnslopify's known policy; they must not force unnecessary Matplotlib renders.
Both arms must audit all current paper members and establish current evidence.
The baseline may safely reuse a render/calculation while validating its current
acceptance. Actual executed/reused counts are outcomes, reported for each arm.
Old acceptance cannot be copied as a calculation cache hit.

Task membership, input bytes, order, denominators, numerical/physical/legibility
thresholds and retention rules are unchanged. This clarification was prepared
before formal paired timing. Its code and both producers
must be included in the eventual complete implementation seal.

## Still required

The Graph capture adapter and common independent final task evaluator; complete
paired/paper/reliability/local/native reproduction controllers; 14 real GUI runs;
actual formal measurements and analysis; candidate UI/docs polish; and the full
78–89 delivery audit. Outside researchers, blind visual ratings, real model quality
and general human productivity remain unmeasured/user-deferred. No new release or
tag is authorized; public PyPI 0.8.0 remains separate from current source.
