# Observation provenance

A local Python ledger records which original records and calculations produced a
quantity. Opt-in renders record reading, filtering, preparation, ordinary summaries
and matrix cells. The local editor can pick cells in heatmaps and confusion matrices.
Other marks and specialized calculations are tracked in
[spec98](../pipeline/specs/98-observation-provenance.md).

For example, subtracting a baseline depends on both the displayed measurement
and the observations used to estimate that baseline. Hiding the baseline series
does not remove those dependencies. Likewise, averaging technical repeats into
one declared unit does not make those repeats independent observations.

## Inspect a matrix in the local editor

1. Open the editor with `graphunslopify preview --open` and choose data for a
   heatmap or confusion matrix with a PNG export.
2. Choose **Trace observations**. Once the final PNG appears, click a cell or
   choose its panel, row, and column.
3. Follow calculation inputs or scoped exclusions to inspect their records. Use
   **Figure filters** and **Data preparation** for the broader selection.
   The editor numbers parsed records from 1. Quoted CSV lines and worksheet
   rows can use different file positions.
4. Choose **View generated code** to see the Python used for this render. Use
   **Download observation graph** to save the complete local graph.

The trace is tied to the actual PNG, specification, source snapshot and render
attempt. Edits clear it. Changed evidence is refused. The explicit graph
download may contain derived values and labels from the input. The editor keeps
it separate from standard exports and model-review requests.

## Trace a generated render

Run `graphunslopify render figure.json --trace-observations --json` or
`Figure.render(trace_observations=True)` with the local translator. The
`observation_selection` report entry points to the bounded JSON sidecar and
binds it to this input snapshot, specification, program, runtime and run.
Use `node_id` to explain the original filter selection. When preparation
completes, `preparation_node_id` explains its ordered rows and scoped exclusions.
The filter graph is still available if a later preparation step fails.

Wide reshape nodes identify the source column and original record. Numeric
conversions identify their input and output dtypes. A prepared row with changed
measurements lists the fields in `measurement_fields`. Its first input is the
row, and the remaining inputs are the corresponding field values. Transforms
record their actual derived values and inputs, including baseline means, ordered
cumulative prefixes and normalization ranges. Decimal values retain their
exact spelling as strings. Exclusions retain their own stage, so a baseline
can be hidden from the prepared rows while contributing
to the calculated values.

For aggregated line, bar, forest and table figures, `summary_node_id` points
to the calculated summaries for each panel and metric. Each point records its
grouping keys, estimate, contributing measurements or declared units, and
interval when requested. The trace follows technical repeats through their
actual mean or median and records which measurements and unit identifiers
were unavailable. A singleton retains its estimate and an explicit unavailable
interval. Bootstrap evidence records the draws, seed and level used.

Use `explain()` on the point's estimate or interval node for its scoped
contributors and exclusions. Use the original filter root for the figure-wide
selection. The numerical cache can reuse results and positional membership
while the ledger binds calculations to each current render.

For heatmaps and confusion matrices, `matrix_node_id` points to each rendered
panel and its cells in image-array order. Each cell carries its axis labels,
aggregate, displayed numeric value and printed annotation when present. The
trace distinguishes an unobserved cell, an all-missing measurement group and
a measured zero. In a normalized confusion matrix, a cell links separately
to its count and the actual row or column total. A zero total is recorded
explicitly alongside the renderer's zero placeholder.

## Local ledger API

Import `ObservationLedger` from `graphunslopify.observation_provenance`.
`from_snapshot` takes the exact reader bytes, reader configuration, logical
record count and actual run/spec/program context. It hashes the bytes without
retaining a copy of the dataset. Context requires `run_id`, `spec_sha256` and
`program_sha256`; hashes use their full lowercase SHA256. An actual
`runtime_source_sha256` can also be supplied.

- `observation(record_ordinal)` identifies one parsed record, starting at zero.
  Identical rows at different ordinals remain distinct. Identity depends on
  the snapshot and reader configuration, including an Excel worksheet; it does
  not depend on the file's location or on a later DataFrame index.
- `calculate(operation, inputs, value=..., metadata=..., excluded=...)` records
  a computation's ordered inputs and actual result. Repeated input references
  retain their multiplicity. Record estimator/field/unit choices in metadata.
- `exclude(reason, inputs, stage=...)` records a scoped reason. A record excluded
  from display can still contribute to a calculation. Exclusion nodes are kept
  separate from numerical inputs; an unrelated exclusion does not affect every
  quantity in the graph.
- `explain(node_id)` returns the complete recorded dependency subgraph, original
  contributing/excluded record ordinals and their stage/reason nodes. It never
  silently truncates a trace or converts a missing observation into a zero.
- `to_json()` returns canonical UTF8 bytes. `from_json(..., expected_context=...,
  expected_source=...)` checks shape,content identities,references,budgets and
  the caller's current ownership before accepting saved local evidence.

`as_dict()` and explanations return copies. Nesting limits apply to each input
metadata/value tree or reader configuration before the graph wraps it; accepted
content stays exportable and inspectable at that boundary. The default limits are 50,000 nodes,
200,000 edges and20MiB of serialized evidence. Budget failures leave the ledger
unchanged. Deserialization rejects unknown/forward/cyclic references,duplicate
nodes/JSON keys,modified node contents and nonfinite numbers. The ledger API
operates on supplied bytes and values. The generated render handles local
artifact I/O separately.

## Meaning of the evidence

The ledger records what its caller supplies. Hashes and graph validation establish
identity and internal consistency; they do not authenticate the source or prove
that a particular estimator actually used those inputs. Renderer and dataflow
instrumentation must provide that connection before the explorer is complete.
Keep full local lineage separate from model-review packets; this foundation does
not add observations to provider disclosures or requests.

The first tests check parsed-record identity,hand-computed baseline and technical-
repeat dependencies,ordered cumulative inputs,stage-scoped exclusions,stale
owners,serialization and atomic budget failures. Future milestones must exercise
actual generated/native quantities and every supported plot/calculation path.
