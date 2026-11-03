# Reproducibility scorecard

The paper workspace shows what evidence is available for each figure: data,
source definitions, execution programs, environment context, recorded checks,
exports and run history. Each component says **Available**, **Partial** or
**Missing**, explains why, and exposes its evidence details.

This is a current-source feature after the published 0.8.0 release. Use a local
checkout installation to try it. It uses the existing project and scientific
review; it does not create another copy of your dataset or run the figures.
An unavailable original fingerprint stays unknown when a file is later restored;
it cannot establish either matching or different bytes.

## Use it

Open a paper project and expand **Scientific figure review**. Choose current
inputs or a saved run, then a figure. Its **Reproduction** card contains the
scorecard. Historical selection stays explicit; current file availability can
differ from the selected run's recorded fingerprints.

```sh
graphunslopify project-scorecard paper/
```

Add `--event RUN_ID` to inspect a selected completed audit or PDF inspection.
The command prints JSON. A successful query exits zero even when it reports
missing evidence or failed science; read the component states and scientific
outcomes separately.

```python
from graphunslopify.project_scorecard import project_scorecard

report = project_scorecard("paper/")
for figure in report["figures"]:
    print(figure["id"], figure["scientific_status"])
    for component in figure["components"]:
        print(component["label"], component["state"], component["summary"])
```

The authorized local project server exposes `GET /api/scorecard`, with optional
`event` and `expected_revision` query parameters. It uses the same access boundary
as scientific review. `expected_revision` is the previous scorecard's
`evidence_revision`; a changed collection is refused. The same component records
are included in `/api/review`, so the UI reads one bound evidence collection.
The [version 1 JSON schema](../scorecard.schema.json) describes the report.

## What the components mean

| Component | Evidence and limits |
| --- | --- |
| Declared data | Current declared files must be readable. Their bytes and locations are compared separately with the selected run. Identical bytes at a different declared location remain Partial for binding review. Missing files cannot become available just because a hash exists. Changed data or incomplete authored-script coverage is Partial. |
| Source definitions | Current file/inline definitions and preserved historical source are distinguished. Readable source does not establish a valid or scientifically appropriate analysis. |
| Execution programs | Actual saved `figure.py` or `source.py` bytes must match the selected execution's recorded SHA. A program hash without readable matching bytes is insufficient. Top-level receipt membership alone is not used to infer missing code. |
| Environment | Recorded runtime and dependency versions remain useful context, but are Partial without a complete environment lock. Version matching does not reverify all dependency bytes, fonts or external tools. |
| Recorded checks | An executed report is evidence that checks were recorded. Its actual passed, failed, incomplete or untested outcome remains visible. **Available checks can contain failed science.** |
| Figure exports | Saved export hashes must verify. Missing, changed and unverified exports remain explicit. |
| Run history | Intact selected history and execution/reuse ancestry remain distinct from a new execution or reproduction. Damaged latest history does not silently fall back to an older passing run. |

The scorecard has no scientific certification percentage. It does not establish
experimental independence, recover undeclared Python inputs, rerun an analysis,
or demonstrate reproduction on another machine. A failed paper audit stays failed
even if its data and programs are available.

For imported PDFs, original plotting data, definitions and programs are Missing.
Recorded inspection context and visual measurements do not establish the original
creation environment or numerical verification. PDF scientific outcomes remain
Untested.

## Saved review packets

**Download review packet** includes `reports/scorecard.json` and a readable
component summary in its HTML report. `availability_scope` describes the local
project at collection time. `packet_inclusion` separately records the packet's
contents: raw datasets, source programs and original PDFs remain excluded by the
existing export policy. Inspect the packet's asset inventory for included exports.

Program observations are rechecked before completing the query. Project inputs,
history, receipts and evidence revisions retain their existing guards. A file
changing during collection or evidence changing before export requires a refresh.
No current definition or historical evidence is repaired by reading the scorecard.

See [paper review export](../paper-review-export.md),
[project management](../project-management.md) and the
[complete research workspace roadmap](../../pipeline/research-platform-roadmap.md).
