# Observation lineage foundation

The observation-level explorer is in development. Its first component is a local
Python ledger for recording which original records and calculations produced a
quantity. Generated figures do not yet populate this ledger automatically, and
the clickable explorer is still pending. The complete scope is tracked in
[spec98](../pipeline/specs/98-observation-provenance.md).

For example, subtracting a baseline depends on both the displayed measurement
and the observations used to estimate that baseline. Hiding the baseline series
does not remove those dependencies. Likewise, averaging technical repeats into
one declared unit does not make those repeats independent observations.

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
content stays exportable and inspectable at that boundary. The default limits are50,000 nodes,
200,000 edges and20MiB of serialized evidence. Budget failures leave the ledger
unchanged. Deserialization rejects unknown/forward/cyclic references,duplicate
nodes/JSON keys,modified node contents and nonfinite numbers. This module reads
no files,executes no programs and makes no network requests.

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
