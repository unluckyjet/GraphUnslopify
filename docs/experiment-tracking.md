# Figure evidence in MLflow

Current source after 0.8.0 can attach a saved paper audit or research-workflow
report to an explicitly chosen MLflow experiment/run. This helps connect a model
training result to the exact figures, data fingerprints, claims and checks used
in a paper. Logging success and scientific acceptance are recorded separately.

Install from the checkout in the Python environment used by your CLI or kernel:

```sh
python -m pip install "./python[tracking]"
```

The optional extra supplies the MLflow client and SQLite backend dependencies.
The immutable public 0.8.0 release does not have this extra or command. It does
not install an MLflow UI/server or start one. An existing MLflow installation
can supply its own UI/server. The base package still works without MLflow.

## Complete local example

First create a demo paper and manifest:

```sh
graphunslopify demo paper --json
graphunslopify audit-init paper
```

Then run this Python code from the same directory. It creates a local SQLite
experiment with an explicit artifact directory, audits the paper, uploads only
selected evidence, and retrieves the saved audit:

```python
from pathlib import Path
from mlflow import MlflowClient
from graphunslopify.audit import audit
from graphunslopify.tracking import log_mlflow

root = Path.cwd()
tracking_uri = "sqlite:///" + (root / "research.db").as_posix()
client = MlflowClient(tracking_uri=tracking_uri, registry_uri=tracking_uri)
experiment_id = client.create_experiment(
    "paper-figures", artifact_location=(root / "tracked-artifacts").as_uri()
)
result = audit("paper", output="audit")
receipt = log_mlflow(
    "audit/audit.report.json",
    tracking_uri=tracking_uri,
    experiment_id=experiment_id,
)
print(receipt["audit_status"], receipt["source_accepted"], receipt["status"])
saved = client.download_artifacts(
    receipt["run_id"], receipt["artifact_path"] + "/audit.report.json"
)
print("Saved evidence:", saved)
if receipt["exit_code"]:
    raise RuntimeError("Figure acceptance or tracking failed; inspect the receipt/report")
```

Create the experiment once; reuse its ID for later audits. The integration does
not create/select an experiment implicitly. A new run is `FINISHED` only when
logging succeeds and the source was accepted; otherwise an owned run is marked
`FAILED` when the store remains reachable.

## CLI and moved archives

Use the explicit URI and experiment ID from your own setup:

```sh
graphunslopify track-mlflow audit/audit.report.json \
  --tracking-uri "sqlite:////absolute/path/research.db" --experiment-id 1
```

Use `--run-id YOUR_RUNNING_RUN_ID` instead of `--experiment-id` to attach to an
existing active run. Exactly one is required. For a moved audit archive, use
`--artifact-root /new/path/to/audit`; that override is exclusive and cannot fall
back to old files. The source report and exported bytes must match.

Failed audits can be logged too: call tracking after reading their nonzero exit,
so a shell's stop-on-error policy does not skip the evidence. A successfully
logged rejected audit returns 2. A missing extra, damaged export, invalid
destination or transport failure also produces a nonzero result. Partial uploads
are retained under the returned `artifact_path`; they are not acceptance.

## Notebooks, training loops and research workspaces

For [research workspaces](research-workflows.md), pass the saved
`graphunslopify-workflow/workflow.report.json`. This includes overall workflow
acceptance separately from `audit_status`. For example, a passed scientific
audit with failed manuscript preparation stays rejected in MLflow.

```python
from pathlib import Path
from graphunslopify.workflow import run_workflow
from graphunslopify.tracking import log_mlflow

config = Path("paper/graphunslopify-workflow/workflow.json")
result = run_workflow(config, latex=True)
receipt = log_mlflow(
    config.with_name("workflow.report.json"),
    tracking_uri=tracking_uri,
    experiment_id=experiment_id,
)
```

Inside an existing configured MLflow training run, replace `experiment_id` with
`run_id=mlflow.active_run().info.run_id` and supply that run's explicit tracking
URI. The caller keeps ownership of its lifecycle, including how figure rejection
affects training success. Logging uses `MlflowClient` operations and does not
change the fluent tracking URI, active run or global experiment. Attached runs
remain running even when a figure is rejected or uploading fails. Completed
external runs are refused rather than reopened.

## What is stored

Each call uses a fresh `graphunslopify/<attempt-id>/` artifact path containing:

- The saved audit report, plus the workflow report when selected. These preserve
  actual claims, statuses, policies, environment and input/source fingerprints.
- Hash/size-verified PNG, SVG and PDF exports from that audit's owned figure runs.
- `comparison.json` when present: the saved machine change evidence. Interactive
  comparison HTML/previews are not uploaded by this command.
- `tracking.manifest.json`: source report SHA256, acceptance/status, counts and
  the selected file hashes/sizes. The receipt also fingerprints this manifest.

Files are frozen before opening the destination; raw CSVs, scripts, logs, editor
settings, tracking credentials and arbitrary neighbouring directories are not
selected. HTML exports are listed as skipped. The report and each static export
have a 20 MiB bound. Reports and figure annotations still contain research content;
the caller chooses where to send them. Hashes establish snapshot integrity, not
authentication of edited reports or scientific certification.

Run tags `graphunslopify.last_*` describe the latest logging attempt, and metrics
record figure passed/failed/incomplete counts. Individual saved manifests preserve
each call's status even when several audits attach to one training run. Logging
does not rerun source programs, modify inputs or overwrite source evidence.

## Verification

`python/tests/test_tracking.py` uses real SQLite stores, artifact retrieval and
active fluent runs. It checks rejected claims/comparisons, failed manuscript and
pre-audit workflows, moved/damaged archives, caller lifecycle/context, unavailable
dependencies and injected upload failures. `scripts/check-experiment-tracking.py`
checks a fresh installed wheel outside the checkout; installed-wheel `--tracking`
runs it with external runtime connections blocked on the supported CI platforms.
Remote provider authentication and service-specific behavior remain with MLflow;
the measured integration target is its explicit local SQLite/artifact store.

MLflow references: [client operations](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.client.html),
[backend stores](https://mlflow.org/docs/latest/self-hosting/architecture/backend-store/) and
[client package](https://pypi.org/project/mlflow-skinny/).
