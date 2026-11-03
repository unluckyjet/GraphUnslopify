# Compare experiment histories

Current source reads CSV directories, TensorBoard logs, MLflow stores/servers,
and Weights & Biases projects.
Choose runs and a metric, review the proposed figure and exclusions, then render
through the existing strict native checks. Importing records does not establish
their scientific meaning or treat separate runs as independent sampling units.

This is inbound history collection. Existing [MLflow evidence logging](../experiment-tracking.md)
writes saved audit results. These source commands are absent from immutable PyPI 0.8.0.

## Install and use the editor

From a source checkout:

```sh
python -m pip install -e './python[experiments]'
graphunslopify preview
```

CSV support needs no tracker SDK. The optional `experiments` extra supplies the
tracker SDKs and bounded process monitoring. Open **Import experiment runs** in the data panel. Enter a local
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

Local CSV/TensorBoard reads need no account. Tracker access is explicit;the
importer does not start training,log experiment results or upload local source data.
Scientific assumptions and the meaning of comparisons remain the author's responsibility.

## MLflow and W&B access

Choose the provider in the same data panel. Tracker queries cover completed runs;
running or scheduled runs are outside this checkpoint. A run label is a display
name; provider-qualified IDs keep same-named runs distinct.

| Source | Required settings | Read boundary |
| --- | --- | --- |
| MLflow SQLite file | Existing file and explicit experiment IDs | Copies database plus present WAL/rollback-journal bytes, checks hashes, and opens only the owned copy through SQLite/SDK. Never initializes the original store. |
| MLflow HTTP(S) server | URL, experiment IDs, optional access token, network consent | Uses paged run/history read endpoints; redirects are refused. HTTP is limited to loopback, HTTPS required remotely. |
| W&B project | entity/project, endpoint, API key, network consent | Uses actual SDK run selection and unsampled HistoryScan with caching disabled. No interactive login or inherited account/service discovery. |

The W&B endpoint defaults to the inspected 0.31 SDK setting,
`https://api.forge.coreweave.com`; review it against your own provider deployment.
Only enter a key for the endpoint you intend to query. The key is retained in local
session/request memory, not reports, bundles or project files. SDK errors are redacted.
Changing provider settings clears an old review. Local store changes or changed
remote histories require a fresh catalog/review rather than borrowing old approval.

```sh
graphunslopify experiment-runs /path/to/tracking.sqlite \
  --provider mlflow --experiments 1 2

graphunslopify experiment-runs https://tracking.example \
  --provider mlflow --experiments 1 --api-key-env MLFLOW_TRACKING_TOKEN --allow-remote

graphunslopify experiment-runs entity/project \
  --provider wandb --tracker-endpoint https://api.forge.coreweave.com \
  --api-key-env WANDB_API_KEY --allow-remote
```

Provide credentials through the named environment variable yourself; the command
does not accept a key value on the command line. Repeat the same provider/settings
with `experiment-compare`, plus the returned snapshot, run IDs, metric and output folder.
Use scatter when duplicate steps remain. No confidence interval or independent
sampling unit is inferred from separate run IDs.

MLflow timestamps remain milliseconds, W&B timestamps seconds; the reader metadata
records that unit. Plots use the actual step axis. Histories are not inner-joined
across metric keys. Explicit missing/invalid values require the same exclusion
review as local files. W&B's page size is a step window, not a total row limit.

Tracker bounds are 256 runs, 128 selected metrics, 100,000 history records,
200,000 points, 64MiB normalized worker output, 90 seconds and 1GiB total worker-tree
memory. HTTP responses are bounded to 8MiB and paged explicitly. Quota overflow,
repeated pagination tokens, source races and unsupported data refuse the import.
SQLite copies retain the existing 20MiB-per-file/64MiB-source budgets. The SDK
can initialize/migrate only its private copy. These checks do not assert atomic
snapshots against arbitrary adversarial concurrent writers.

The integration tests distinguish actual owned MLflow SQLite/API/native rendering,
real loopback HTTP protocol/auth, actual W&B 0.31 HistoryScan with controlled protobuf
IPC, and an actual SDK process facing a controlled authorization refusal. Separate
owned offline service tests establish cleanup boundaries. No successful real
cloud-account query or external researcher feedback is inferred from those fixtures.
