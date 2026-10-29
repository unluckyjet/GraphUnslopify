"""Real MLflow SQLite retrieval, active training context and rejected evidence."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from graphunslopify.audit import audit
from graphunslopify.cli import main
from graphunslopify.tracking import TrackingError, log_mlflow
from graphunslopify.workflow import initialize_workflow, run_workflow

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def evidence(tmp_path_factory):
    root = tmp_path_factory.mktemp("tracking-evidence")
    paper = root / "paper ü with spaces"
    shutil.copytree(ROOT / "examples/paper", paper)
    passed = root / "passed"
    before = audit(paper, output=passed)
    assert before["exit_code"] == 0
    source = paper / "training.figure.json"
    spec = json.loads(source.read_text())
    spec["claims"][0].update(subject="base", reference="ours")
    source.write_text(json.dumps(spec))
    failed = root / "failed"
    after = audit(paper, output=failed, baseline=passed / "audit.report.json")
    assert after["status"] == "failed" and after["exit_code"] == 2
    return passed, failed


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("MLFLOW_DISABLE_AGENT_HINT", "1")
    mlflow = pytest.importorskip("mlflow")
    uri = "sqlite:///" + (tmp_path / "tracking.db").as_posix()
    client = mlflow.MlflowClient(tracking_uri=uri, registry_uri=uri)
    experiment = client.create_experiment(
        "paper", artifact_location=(tmp_path / "artifacts").as_uri()
    )
    return uri, client, experiment


def retrieve(receipt, client, root):
    folder = Path(client.download_artifacts(receipt["run_id"], receipt["artifact_path"], str(root)))
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    assert actual == {x["path"] for x in receipt["files"]}
    for item in receipt["files"]:
        raw = (folder / item["path"]).read_bytes()
        assert len(raw) == item["bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"]
    return folder


def test_real_store_recovers_exact_exports_reports_fingerprints_and_only_selected_files(
    evidence, store, tmp_path
):
    passed, _ = evidence
    uri, client, experiment = store
    original = {str(p): p.read_bytes() for p in passed.rglob("*") if p.is_file()}
    receipt = log_mlflow(passed / "audit.report.json", tracking_uri=uri, experiment_id=experiment)
    assert receipt["status"] == "logged" and receipt["exit_code"] == 0
    assert receipt["source_accepted"] and receipt["audit_status"] == "passed"
    assert client.get_run(receipt["run_id"]).info.status == "FINISHED"
    recovered = retrieve(receipt, client, tmp_path)
    assert (recovered / "audit.report.json").read_bytes() == (
        passed / "audit.report.json"
    ).read_bytes()
    assert {Path(x["path"]).suffix for x in receipt["files"]} == {".png", ".svg", ".pdf", ".json"}
    report = json.loads((recovered / "audit.report.json").read_text())
    assert len(report["figures"]) == 2 and all(f["data"]["sha256"] for f in report["figures"])
    assert original == {str(p): p.read_bytes() for p in passed.rglob("*") if p.is_file()}


def test_rejected_science_and_real_comparison_remain_rejected_in_store_and_cli(
    evidence, store, tmp_path, capsys
):
    _, failed = evidence
    uri, client, experiment = store
    code = main(
        [
            "track-mlflow",
            str(failed / "audit.report.json"),
            "--tracking-uri",
            uri,
            "--experiment-id",
            experiment,
        ]
    )
    receipt = json.loads(capsys.readouterr().out)
    assert code == receipt["exit_code"] == 2 and receipt["status"] == "logged"
    assert receipt["audit_status"] == "failed" and not receipt["source_accepted"]
    run = client.get_run(receipt["run_id"])
    assert run.info.status == "FAILED" and run.data.metrics["graphunslopify.figures_failed"] == 1
    recovered = retrieve(receipt, client, tmp_path)
    assert json.loads((recovered / "comparison.json").read_text())["changed"]
    assert (
        json.loads((recovered / "audit.report.json").read_text())["figures"][0]["status"]
        == "failed"
    )


def test_fluent_active_run_and_tracking_uri_survive_new_run_and_rejected_attachment(
    evidence, store, tmp_path
):
    import mlflow

    passed, failed = evidence
    uri, client, experiment = store
    other_uri = "sqlite:///" + (tmp_path / "other.db").as_posix()
    other = mlflow.MlflowClient(tracking_uri=other_uri, registry_uri=other_uri)
    other_experiment = other.create_experiment(
        "separate", artifact_location=(tmp_path / "other-artifacts").as_uri()
    )
    previous = mlflow.get_tracking_uri()
    try:
        mlflow.set_tracking_uri(uri)
        with mlflow.start_run(experiment_id=experiment) as training:
            current = mlflow.active_run()
            created = log_mlflow(
                passed / "audit.report.json", tracking_uri=other_uri, experiment_id=other_experiment
            )
            attached = log_mlflow(
                failed / "audit.report.json", tracking_uri=uri, run_id=training.info.run_id
            )
            assert created["run_id"] != training.info.run_id
            assert len(other.search_runs([other_experiment])) == 1
            assert len(client.search_runs([experiment])) == 1
            assert attached["status"] == "logged" and attached["exit_code"] == 2
            assert mlflow.active_run() is current and mlflow.get_tracking_uri() == uri
            assert client.get_run(training.info.run_id).info.status == "RUNNING"
            assert (
                client.get_run(training.info.run_id).data.tags[
                    "graphunslopify.last_source_accepted"
                ]
                == "false"
            )
    finally:
        mlflow.set_tracking_uri(previous)


@pytest.mark.parametrize("before_audit", [False, True])
def test_real_workflow_preparation_or_input_failure_is_not_promoted_by_passed_audit(
    store, tmp_path, before_audit
):
    uri, client, experiment = store
    paper = tmp_path / "paper"
    shutil.copytree(ROOT / "examples/paper", paper)
    created = initialize_workflow(paper)
    config = Path(created["config"])
    if before_audit:
        (paper / "graphunslopify.json").unlink()
    else:
        path = paper / "training.figure.json"
        spec = json.loads(path.read_text())
        spec["output"]["formats"] = ["svg"]
        path.write_text(json.dumps(spec))
    result = run_workflow(config, latex=True)
    assert result["exit_code"] == 2
    assert result["audit_status"] == ("not_run" if before_audit else "passed")
    receipt = log_mlflow(
        config.parent / "workflow.report.json", tracking_uri=uri, experiment_id=experiment
    )
    assert receipt["status"] == "logged" and receipt["exit_code"] == 2
    assert receipt["audit_status"] == result["audit_status"]
    assert client.get_run(receipt["run_id"]).info.status == "FAILED"
    folder = retrieve(receipt, client, tmp_path)
    assert json.loads((folder / "workflow.report.json").read_text())["latex"]["compiled"] is False


@pytest.mark.parametrize("problem", ["tampered", "missing", "wrong-root", "escape", "inconsistent"])
def test_damaged_or_inconsistent_saved_evidence_refuses_before_creating_run(
    evidence, store, tmp_path, problem
):
    uri, client, experiment = store
    copied = tmp_path / "copied"
    shutil.copytree(evidence[0], copied)
    path = copied / "audit.report.json"
    report = json.loads(path.read_text())
    item = report["figures"][0]["outputs"][0]
    artifact = copied / item["path"]
    root = copied
    if problem == "tampered":
        artifact.write_bytes(b"changed after audit")
    elif problem == "missing":
        artifact.unlink()
    elif problem == "wrong-root":
        root = tmp_path / "empty"
        root.mkdir()
    elif problem == "escape":
        item["path"] = "../private.csv"
    else:
        report["counts"]["failed"] += 1
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        log_mlflow(path, tracking_uri=uri, experiment_id=experiment, artifact_root=root)
    assert not client.search_runs([experiment])


@pytest.mark.parametrize("attach", [False, True])
def test_transport_failure_does_not_echo_credentials_or_finish_owned_run_successfully(
    evidence, store, monkeypatch, attach
):
    from mlflow.tracking import MlflowClient

    uri, client, experiment = store

    def broken(*args, **kwargs):
        raise RuntimeError("https://username:private-password@example.invalid/upload")

    monkeypatch.setattr(MlflowClient, "log_artifact", broken)
    chosen = (
        {"run_id": client.create_run(experiment).info.run_id}
        if attach
        else {"experiment_id": experiment}
    )
    receipt = log_mlflow(evidence[0] / "audit.report.json", tracking_uri=uri, **chosen)
    assert (
        receipt["status"] == "failed" and receipt["exit_code"] == 2 and receipt["source_accepted"]
    )
    assert "private-password" not in json.dumps(receipt)
    run = client.get_run(receipt["run_id"])
    assert run.info.status == ("RUNNING" if attach else "FAILED")
    assert run.data.tags["graphunslopify.last_logging_status"] == "failed"
    assert run.data.tags["graphunslopify.last_source_accepted"] == "true"
    assert run.data.tags["graphunslopify.last_artifact_path"] == receipt["artifact_path"]


def test_completed_external_run_is_not_reopened_or_retagged(evidence, store):
    uri, client, experiment = store
    run = client.create_run(experiment)
    client.set_terminated(run.info.run_id, "FINISHED")
    original = client.get_run(run.info.run_id).data.tags
    receipt = log_mlflow(
        evidence[0] / "audit.report.json", tracking_uri=uri, run_id=run.info.run_id
    )
    assert receipt["status"] == "failed" and receipt["exit_code"] == 2
    assert client.get_run(run.info.run_id).info.status == "FINISHED"
    assert client.get_run(run.info.run_id).data.tags == original


def test_missing_optional_dependency_has_actionable_install_error(evidence, monkeypatch):
    monkeypatch.setitem(sys.modules, "mlflow.tracking", None)
    with pytest.raises(TrackingError, match=r"graphunslopify\[tracking\]"):
        log_mlflow(
            evidence[0] / "audit.report.json", tracking_uri="sqlite:///unused.db", experiment_id="1"
        )


@pytest.mark.parametrize(
    "kwargs", [{}, {"experiment_id": "1", "run_id": "id"}, {"experiment_id": ""}]
)
def test_destination_choice_is_explicit_before_reading_sources(kwargs):
    with pytest.raises(TrackingError):
        log_mlflow("not-read.json", tracking_uri="sqlite:///unused.db", **kwargs)


def test_missing_uri_never_uses_global_tracking_store():
    with pytest.raises(TrackingError, match="explicitly"):
        log_mlflow("not-read.json", tracking_uri="", experiment_id="1")
