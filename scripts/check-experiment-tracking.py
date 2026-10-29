"""Retrieve real installed-package evidence from an explicit local MLflow store."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    where = (
        args.work_dir or Path(tempfile.mkdtemp(prefix="gu-tracking-check-"))
    ).resolve()
    if where.exists() and any(where.iterdir()):
        parser.error("choose a new/empty directory; existing evidence is preserved")
    where.mkdir(parents=True, exist_ok=True)
    os.environ["MLFLOW_DISABLE_AGENT_HINT"] = "1"
    import mlflow
    from graphunslopify.tracking import log_mlflow

    env = {
        **os.environ,
        "GRAPHUNSLOPIFY_API": "local",
        "PYTHONIOENCODING": "utf-8",
        "MPLBACKEND": "Agg",
    }
    exits = []

    def command(*words, expected=0):
        done = subprocess.run(
            [sys.executable, "-m", "graphunslopify.cli", *map(str, words)],
            cwd=where,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf8",
            timeout=120,
            check=False,
        )
        exits.append(done.returncode)
        if done.returncode != expected:
            raise RuntimeError(
                f"{words}: expected {expected}, got {done.returncode}\n{done.stdout}\n{done.stderr}"
            )
        return json.loads(done.stdout)

    project = where / "paper with spaces"
    command("demo", project, "--json")
    command("audit-init", project)
    folder = Path(command("workflow-init", project)["config"]).parent
    command("workflow-run", folder)
    original_spec = (project / "figure.json").read_bytes()
    original_data = (project / "results.csv").read_bytes()
    source = folder / "workflow.report.json"
    original_report = source.read_bytes()
    uri = "sqlite:///" + (where / "tracking.db").as_posix()
    client = mlflow.MlflowClient(tracking_uri=uri, registry_uri=uri)
    experiment = client.create_experiment(
        "paper", artifact_location=(where / "artifacts").as_uri()
    )
    fluent_uri = mlflow.get_tracking_uri()
    receipt = command(
        "track-mlflow", source, "--tracking-uri", uri, "--experiment-id", experiment
    )
    assert receipt["status"] == "logged" and receipt["source_accepted"]
    assert client.get_run(receipt["run_id"]).info.status == "FINISHED"
    restored = Path(
        client.download_artifacts(
            receipt["run_id"], receipt["artifact_path"], str(where)
        )
    )
    assert (
        (restored / "workflow.report.json").read_bytes()
        == original_report
        == source.read_bytes()
    )
    names = {
        p.relative_to(restored).as_posix() for p in restored.rglob("*") if p.is_file()
    }
    assert names == {x["path"] for x in receipt["files"]}
    for item in receipt["files"]:
        data = (restored / item["path"]).read_bytes()
        assert (
            len(data) == item["bytes"]
            and hashlib.sha256(data).hexdigest() == item["sha256"]
        )
    assert all(Path(name).suffix in (".json", ".png", ".svg", ".pdf") for name in names)
    spec = json.loads(original_spec)
    spec["claims"][0].update(subject="base", reference="ours")
    (project / "figure.json").write_text(json.dumps(spec), encoding="utf8")
    command(
        "workflow-run",
        folder,
        "--baseline",
        folder / "audit/audit.report.json",
        expected=2,
    )
    training = client.create_run(experiment)
    failed = command(
        "track-mlflow",
        source,
        "--tracking-uri",
        uri,
        "--run-id",
        training.info.run_id,
        expected=2,
    )
    assert (
        failed["status"] == "logged"
        and failed["audit_status"] == "failed"
        and not failed["source_accepted"]
    )
    assert client.get_run(training.info.run_id).info.status == "RUNNING"
    recovered_delta = Path(
        client.download_artifacts(
            training.info.run_id,
            failed["artifact_path"] + "/comparison.json",
            str(where),
        )
    )
    assert json.loads(recovered_delta.read_text())["changed"]
    copied = where / "damaged archive"
    shutil.copytree(folder / "audit", copied)
    report = json.loads((copied / "audit.report.json").read_text())
    (copied / report["figures"][0]["outputs"][0]["path"]).write_bytes(b"tampered")
    before = len(client.search_runs([experiment]))
    try:
        log_mlflow(
            copied / "audit.report.json",
            tracking_uri=uri,
            experiment_id=experiment,
            artifact_root=copied,
        )
    except ValueError as problem:
        assert "changed" in str(problem)
    else:
        raise AssertionError("tampered export was accepted")
    assert len(client.search_runs([experiment])) == before
    assert mlflow.get_tracking_uri() == fluent_uri and mlflow.active_run() is None
    assert (project / "results.csv").read_bytes() == original_data
    (project / "figure.json").write_bytes(original_spec)
    print(
        json.dumps(
            {
                "status": "passed",
                "mlflow": mlflow.__version__,
                "work_dir": str(where),
                "exit_codes": exits,
                "retrieved_files": len(names),
                "owned_run": "FINISHED",
                "attached_rejected_run": "RUNNING; caller-owned",
                "tampered_export": "refused before creating run",
                "raw_inputs_uploaded": False,
                "global_context_unchanged": True,
            }
        )
    )


if __name__ == "__main__":
    main()
