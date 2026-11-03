# Compare local experiment histories

Current source reads CSV result directories and TensorBoard event logs directly.
Choose runs and a metric, review the proposed figure and exclusions, then render
through the existing strict native checks. Importing records does not establish
their scientific meaning or treat separate runs as independent sampling units.

This is the local-provider part of research-platform idea 1. Inbound MLflow and
Weights & Biases histories remain the next checkpoint. Existing
[MLflow evidence logging](../experiment-tracking.md) writes saved audit results;
it is a different operation. These new commands are absent from immutable PyPI 0.8.0.

## Install and use the editor

From a source checkout:

```sh
python -m pip install -e './python[experiments]'
graphunslopify preview
```

CSV support needs no tracker SDK. The optional `experiments` extra supplies
TensorBoard. Open **Import experiment runs** in the data panel. Enter a local
folder, list runs, check the runs to compare, and choose a metric. CSV files use
`step` by default; specify another step column when needed. Optional metric names
limit which columns or tags are considered.

**Review selected history** produces an unapplied proposal. Inspect its run IDs,
source snapshot, raw observation count and exclusions. Apply requires an explicit
review acknowledgement; excluded observations require a separate choice. The
editor then runs its usual checks and provides PNG, SVG, PDF and generated code.
The import proposal itself remains unverified evidence about its source.

**Undo experiment import** restores the previous dataset and figure and reruns
checks. Undo is disabled while later figure edits remain. Changing the source,
options, selected runs or figure context invalidates old proposals; a late reply
cannot overwrite a newer edit. A changed source requires listing and reviewing again.

## CLI

```sh
graphunslopify experiment-runs ./results
```

Read the returned run IDs and snapshot. Substitute the chosen values below:

```sh
graphunslopify experiment-compare ./results \
  --snapshot 'snapshot-from-catalog' \
  --runs 'chosen-run-id-a' 'chosen-run-id-b' \
  --metric loss --out-dir ./comparison
```

Add `--provider tensorboard` to both commands for event logs. Repeat the same
`--step-field` and `--metrics` options used for listing. Use `--kind scatter` when
steps repeat. `--accept-exclusions` is required when selected observations are
missing, nonnumeric or nonfinite. The output directory must be new and outside
the input folder. Verification failure returns a nonzero exit code and retains
the actual native report.

Outputs include `experiment-history.csv`, a portable `experiment.figure.json`,
native figure files, and `experiment-import.json` with source hashes, reader and
options, selected run IDs, exclusions and the actual native verdict. The editor
also adds import provenance to figure bundles. Raw CSV data remains excluded from
bundles until **Include source data in ZIP** is selected.

## Record semantics and limits

- Each CSV file is one run; each TensorBoard parent directory is one run. Stable
  source-qualified IDs distinguish runs, and labels include a short ID.
- Numeric scalar records retain step, value, available wall time, source file,
  record index, TensorBoard byte offset and restart session. No sampling,
  interpolation, averaging, confidence interval or experiment rerun is inferred.
  Integer literals and integer tensors retain signed64-bit values exactly;
  integers outside that range are excluded with an explicit reason. Decimal and
  exponent notation uses native float64 range and precision. Plot coordinates
  still have native precision limits; rescale large offsets explicitly when needed.
- Duplicate steps remain separate observations. A line is refused when selected
  steps repeat; raw scatter points preserve all observations.
- TensorBoard legacy scalars and scalar numeric tensors are supported. Other
  summaries are disclosed outside numeric candidates; selecting a metric with
  unsupported scalar representations is refused. Restart records are retained.
- Reads validate every TensorBoard TFRecord CRC and frame. Truncated, corrupt,
  oversized, escaped or changed inputs are refused instead of accepting a prefix.
  Use closed or copied event files while training continues elsewhere.
- Bounds are 256 files, 20MiB per file, 64MiB source bytes, 64MiB normalized CSV,
  200,000 candidate metric points, 100,000 CSV rows per file or 100,000 total
  TensorBoard event records. Directory inventory is bounded to 1024 directories,
  depth 8 and 4096 entries per directory. Directory symlinks are outside the
  regular-file inventory; eligible file symlinks are refused. POSIX reads open
  relative components without following symlinks. Other platforms use containment
  and change checks; those fallback paths have no platform acceptance claim here.
- Reports show the first 100 exclusion/unsupported reasons plus full counts and
  a truncation flag. They do not claim a complete observation-level lineage UI.

The reader never authenticates to a tracker, uploads source files, executes
training code or changes source records. Scientific assumptions and the meaning
of comparisons remain the author's responsibility.
