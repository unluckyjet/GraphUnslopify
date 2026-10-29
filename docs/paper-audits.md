# Audit a paper's figures

For a manuscript PDF without source figure specs/data, current development adds
[PDF visual review packets](pdf-review.md). These retain incomplete numerical
verification rather than treating extracted pictures as verified research.

A manifest connects figures to their source specs or generated programs, local data and explicit
claims. An audit regenerates every entry, runs strict runtime checks, verifies saved artifacts,
and writes one combined report. It continues after an individual failure.

For shared semantic settings, declared-input freshness and retained aggregate
history, current source adds [paper project management](project-management.md)
around this same manifest. `project-preview paper/ --open` brings definitions,
shared settings, audits and saved evidence into one local paper workspace.

From a source checkout:

```sh
graphunslopify audit examples/paper --out-dir .graphunslopify-audit
```

The repository example has public synthetic data, a training curve and an uncertainty table.
For an existing folder of figure JSON specs:

```sh
graphunslopify audit-init paper/
graphunslopify audit paper/ --out-dir audit-output
```

`audit-init` discovers JSON objects containing `kind` and writes `graphunslopify.json` without
replacing an existing manifest. Review its candidates before running them. It excludes the
usual dependency folders and default audit directory. For custom output directories, keep them
outside the source folder when using discovery. The audit also accepts a manifest filename.

## Manifest contract

```json
{
  "schema_version": 1,
  "figures": [
    {
      "id": "training",
      "spec": "figures/training.figure.json",
      "data": "results/training.csv",
      "claims": [{"kind": "beats_everywhere", "subject": "ours", "reference": "base"}],
      "artifacts": ["published/training.png"]
    },
    {
      "id": "ablation",
      "script": "scripts/ablation.py",
      "cwd": ".",
      "data": "results/ablation.csv"
    }
  ]
}
```

IDs are unique, stable names containing letters, digits, dots, underscores and hyphens (start
with a letter/digit; at most 64 characters). Each entry has exactly one `spec` or `script`.
The manifest is validated against [manifest.schema.json](manifest.schema.json).

- `spec` is a JSON filename or inline figure-spec object. File-based data/lock paths resolve
  beside that spec; inline paths resolve beside the manifest.
- Optional `data` on a spec entry overrides its dataset path, relative to the manifest.
- Optional `claims` **replaces** the spec's claims. They are evaluated separately in every
  facet/repeated metric using the same summaries and declared observation units as the plot.
- `script` executes a trusted generated Python program implementing the current `run_cli` and
  JSON-report contract. Its default input working directory is its source folder; `cwd`
  overrides that relative to the manifest. The worker resolves DATA_PATH/PALETTE_LOCK before
  moving to an isolated output directory, and preserves the original program's source hash.
  Source imports/top-level code still execute normally. Arbitrary legacy scripts without the
  report contract fail explicitly; they are not reported as verified.
- Optional `data` on a script entry asserts that its actual input bytes match the declared file;
  it does not rewrite the program's analysis. Claims belong in that program's source spec.
- Optional `artifacts` names existing PNG/SVG/PDF/HTML exports to check against regenerated
  spec/data evidence. Missing, legacy or stale provenance fails. Script entries also require
  matching source hashes. PNG pixels are compared with a freshly generated PNG when available;
  differences warn because changed source or rendering environment can both cause them.

Unknown manifest fields and ambiguous entries are errors. Current auditing requires local data;
there is no hosted rendering or automatic upload.

## Reports and changes

Each run gets a fresh `runs/<run-id>/figures/<id>/` directory. Previous evidence and original input
files are retained. Files include programs, logs, runtime reports and exported figures. The tool
does not copy input data files. Artifact byte hashes, size and embedded provenance must agree with
the runtime report. Missing requested formats are errors, including silently skipped animations.
The actual data file is hashed again to catch a changed/mismatched source during the audit.

The output root contains:

- `audit.report.json`: aggregate machine evidence, individual runtime reports and comparison.
- `audit.summary.md`: statuses, errors/warnings and the comparison for human review.

The aggregate contract is [audit-report.schema.json](audit-report.schema.json). Individual reports
use [runtime-report.schema.json](runtime-report.schema.json).

```sh
# Save the report before editing; retain its runs/ files for visual previews.
cp audit-output/audit.report.json before.json
# After changing results, specs or scripts:
graphunslopify audit paper/ --out-dir audit-output --baseline before.json
```

Comparisons match stable figure IDs and report additions/removals, input bytes, numeric input
representation, semantic spec, source, claims (including before/after verdicts), significance,
descriptions, findings, published artifacts and exported file hashes. Incidental data/lock path
rebasing is excluded from semantic spec comparison. Numeric fingerprints cover pandas-parsed
numeric columns, names/order, row order and integer-versus-float encoding. Floating values use
hexadecimal representations rather than rounded display values. Non-numeric columns are covered
by the full input-byte hash. Neither fingerprint proves experimental validity.

PNG pixel hashes exclude metadata and include dimensions/RGBA pixels. A metadata-only change can
therefore show `bytes_changed: true` with `pixels_changed: false`. Other formats report file-byte
changes; `pixels_changed: null` means no raster comparison was performed. Matching provenance is
not authentication. The auditor does not infer data, claims or arbitrary paper prose from an image,
reconstruct an unrelated PDF, certify tagged-PDF accessibility, or establish statistical equivalence.
Use a consistent renderer/font environment when interpreting visual changes.

## Failure policy

Audit execution is always strict: failed claims, required untested checks, unavailable inspection,
missing/corrupt outputs, malformed reports and per-figure runtime errors produce exit **2**.
Warnings are retained; `--fail-on-warning` rejects them. With `--baseline`, `--fail-on-change`
also rejects any recorded change, including metadata/file-byte changes, even if checks pass.
The report's check status and selected exit policy are distinct. Use the process exit code in CI.

`--timeout SECONDS` bounds each generated program (default 120); timed-out process groups are
terminated and the remaining entries still run. Translation also has its own local transport
limit. Invalid manifests/baselines return an error JSON and nonzero exit rather than a completed
audit; always inspect the current process result before relying on an older report in that folder.

## Visual before/after reports (source after0.8.0)

Baseline audits now also produce [portable visual comparison packets](figure-comparison.md):
verified saved PNG/SVG/PDF previews, native raster difference maps where comparable,
blend controls and before/after explanations. See `visual_comparison` in the returned
report or follow its Markdown link. Saved reports can also be reviewed with
`graphunslopify compare before.json after.json --out-dir comparison` without executing
programs or rereading datasets. Keep run images or supply moved archive roots;
missing or stale files remain unavailable. The lower-level byte/pixel comparison
above stays distinct from this selected-preview layer. Current source audits also
compare recorded environment changes and preserve their existing strict policy.
