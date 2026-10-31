"""Real saved science, current inputs, historical failures and read-only queries."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from graphunslopify import Figure
from graphunslopify import project as model
from graphunslopify import project_review as review
from graphunslopify.cli import main

ROOT = Path(__file__).resolve().parents[2]


def bytes_at(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.fixture(scope="module")
def checked(tmp_path_factory):
    paper = tmp_path_factory.mktemp("review-original") / "paper ü with spaces"
    shutil.copytree(ROOT / "examples/paper", paper)
    config = Path(model.initialize_project(paper)["config"])
    result = model.run_project(config)
    assert result["exit_code"] == 0, result
    return paper


@pytest.fixture
def paper(checked, tmp_path):
    target = tmp_path / "moved paper"
    shutil.copytree(checked, target)
    return target


def test_no_audit_keeps_every_scientific_group_unavailable(tmp_path):
    paper = tmp_path / "new"
    shutil.copytree(ROOT / "examples/paper", paper)
    model.initialize_project(paper)
    before = bytes_at(paper)
    result = review.project_review(paper)
    assert result["query_status"] == "ok" and result["selection"]["state"] == "not_run"
    assert all(row["evidence_state"] == "not_run" for row in result["figures"])
    assert all(
        group["state"] == "unavailable"
        for row in result["figures"]
        for group in row["groups"].values()
    )
    assert not any(row["matches_latest_accepted_inputs"] for row in result["figures"])
    assert before == bytes_at(paper)


def test_actual_claim_uncertainty_inspection_and_source_without_execution(paper, monkeypatch):
    def execute(*args, **kwargs):
        raise AssertionError("A review query must not execute an audit")

    monkeypatch.setattr(model, "audit", execute)
    before = bytes_at(paper)
    result = review.project_review(paper)
    row = next(r for r in result["figures"] if r["id"] == "training")
    assert row["evidence_state"] == "current_inputs"
    assert row["matches_latest_accepted_inputs"] and not row["rerun_recommended"]
    groups = row["groups"]
    assert groups["claims"]["items"][0]["verdict"] == "holds"
    assert groups["uncertainty"]["settings"]["kind"] == "ci"
    assert groups["uncertainty"]["settings"]["over"] == "seed"
    assert groups["uncertainty"]["sample_evidence"]["read"] > 0
    assert groups["legibility"]["inspection"]["available"]
    assert groups["reproduction"]["runtime"]["matches_current_source"]
    assert groups["reproduction"]["environment"]["versions_match"]
    assert groups["reproduction"]["saved_exports_verified"]
    assert before == bytes_at(paper)


def test_changed_original_data_cannot_borrow_a_saved_pass(paper):
    history = paper / "graphunslopify-project/history"
    before = bytes_at(history)
    data = paper / "results.csv"
    data.write_bytes(data.read_bytes() + b"\n")
    result = review.project_review(paper)
    assert result["current_input_status"] == "needs_audit"
    assert not result["selection"]["matches_current_revision"]
    assert all(row["rerun_recommended"] for row in result["figures"])
    assert not any(row["matches_latest_accepted_inputs"] for row in result["figures"])
    assert (
        next(r for r in result["figures"] if r["id"] == "training")["groups"]["claims"]["items"][0][
            "verdict"
        ]
        == "holds"
    )
    assert before == bytes_at(history)


def test_real_failed_claim_and_explicit_history_remain_distinct(paper, capsys):
    old = model.project_history(paper)["events"][0]["id"]
    path = paper / "training.figure.json"
    spec = json.loads(path.read_text())
    spec["claims"][0].update(subject="base", reference="ours")
    path.write_text(json.dumps(spec))
    failed = model.run_project(paper)
    assert failed["exit_code"] == 2
    assert main(["project-review", str(paper)]) == 0  # successful read, failed science retained
    result = json.loads(capsys.readouterr().out)
    row = next(r for r in result["figures"] if r["id"] == "training")
    assert row["execution_status"] == "failed" and row["rerun_recommended"]
    assert row["groups"]["claims"]["items"][0]["verdict"] == "fails"
    historical = review.project_review(paper, event_id=old)
    old_row = next(r for r in historical["figures"] if r["id"] == "training")
    assert historical["selection"]["explicit_history_selection"]
    assert old_row["groups"]["claims"]["items"][0]["verdict"] == "holds"
    assert not old_row["matches_latest_accepted_inputs"]
    assert old_row["groups"]["reproduction"]["saved_exports_verified"]


def test_newer_incomplete_history_blocks_automatic_fallback(paper):
    old = model.project_history(paper)["events"][0]["id"]
    model._event(paper / "graphunslopify-project", "run")
    result = review.project_review(paper)
    assert result["selection"]["state"] == "unavailable"
    assert all(row["groups"]["claims"]["state"] == "unavailable" for row in result["figures"])
    explicit = review.project_review(paper, event_id=old)
    assert explicit["history_integrity"] == "partial"
    assert not any(row["matches_latest_accepted_inputs"] for row in explicit["figures"])


def test_changed_saved_export_is_not_read_as_intact_science(paper):
    png = next((paper / "graphunslopify-project/history").rglob("*.png"))
    png.write_bytes(b"changed bytes")
    result = review.project_review(paper)
    # The receipt covers source/results; selected exports require their own byte check.
    assert result["history_integrity"] == "verified"
    affected = [
        row
        for row in result["figures"]
        if not row["groups"]["reproduction"]["saved_exports_verified"]
    ]
    assert len(affected) == 1 and affected[0]["rerun_recommended"]
    assert not affected[0]["matches_latest_accepted_inputs"]
    assert any("export changed" in message for message in affected[0]["errors"])


def test_historical_export_bytes_are_checked_separately_from_the_latest_run(paper):
    old = model.project_history(paper)["events"][0]
    old_png = next((paper / "graphunslopify-project/history" / old["id"]).rglob("*.png"))
    assert model.run_project(paper)["exit_code"] == 0
    old_png.write_bytes(b"historical bytes changed")
    latest = review.project_review(paper)
    assert all(r["groups"]["reproduction"]["saved_exports_verified"] for r in latest["figures"])
    historical = review.project_review(paper, event_id=old["id"])
    assert any(
        not r["groups"]["reproduction"]["saved_exports_verified"] for r in historical["figures"]
    )
    assert not any(r["matches_latest_accepted_inputs"] for r in historical["figures"])


def test_authored_script_declared_data_does_not_establish_all_its_inputs(paper):
    spec = json.loads((paper / "training.figure.json").read_text())
    spec["data"]["path"] = str(paper / "results.csv")
    (paper / "training.py").write_text(Figure(spec).translate(api="local")["code"])
    path = paper / "graphunslopify.json"
    manifest = json.loads(path.read_text())
    manifest["figures"][0] = {"id": "training", "script": "training.py", "data": "results.csv"}
    path.write_text(json.dumps(manifest))
    assert model.run_project(paper)["exit_code"] == 0
    row = next(r for r in review.project_review(paper)["figures"] if r["id"] == "training")
    assert row["groups"]["reproduction"]["declared_input_coverage"] == "declared"
    assert row["groups"]["reproduction"]["source_input_scope"] == "declared_script_inputs_only"
    assert row["rerun_recommended"]


def test_changed_audit_compiler_sources_remain_explicit(paper, monkeypatch):
    actual = review._execution_source()
    monkeypatch.setattr(review, "_execution_source", lambda: {**actual, "sha256": "changed"})
    result = review.project_review(paper)
    assert all(
        r["groups"]["reproduction"]["audit_compiler_source"]["state"] == "changed"
        for r in result["figures"]
    )
    assert all(r["rerun_recommended"] for r in result["figures"])


def test_historical_coverage_comes_from_its_saved_binding(paper):
    spec = json.loads((paper / "training.figure.json").read_text())
    spec["data"]["path"] = str(paper / "results.csv")
    (paper / "training.py").write_text(Figure(spec).translate(api="local")["code"])
    path = paper / "graphunslopify.json"
    original = json.loads(path.read_text())
    manifest = json.loads(path.read_text())
    manifest["figures"][0] = {"id": "training", "script": "training.py"}
    path.write_text(json.dumps(manifest))
    result = model.run_project(paper)
    assert result["exit_code"] == 0
    event = model.project_history(paper)["events"][0]["id"]
    path.write_text(json.dumps(original))
    row = next(
        r for r in review.project_review(paper, event_id=event)["figures"] if r["id"] == "training"
    )
    reproduction = row["groups"]["reproduction"]
    assert reproduction["declared_input_coverage"] == "unknown_script_inputs"
    assert reproduction["current_declared_input_coverage"] == "declared"
    assert reproduction["source_input_scope"] == "declared_script_inputs_only"
    assert not row["matches_latest_accepted_inputs"]


def test_actual_audit_is_rejected_if_its_sources_change_mid_run(paper, monkeypatch):
    actual = model._execution_source()
    calls = 0

    def signature():
        nonlocal calls
        calls += 1
        return actual if calls == 1 else {**actual, "sha256": "changed"}

    monkeypatch.setattr(model, "_execution_source", signature)
    result = model.run_project(paper)
    assert result["exit_code"] == 2
    assert any("sources changed during execution" in message for message in result["errors"])
    assert result["execution_source"] == actual


def test_actual_package_upgrade_after_import_requires_restart(tmp_path):
    package = tmp_path / "modules" / "graphunslopify"
    shutil.copytree(
        ROOT / "python/graphunslopify", package, ignore=shutil.ignore_patterns("__pycache__")
    )
    program = """
import graphunslopify
from pathlib import Path
from graphunslopify.project import ProjectError, _execution_source
assert Path(graphunslopify.__file__).parent.resolve() == Path(__import__('sys').argv[1]).resolve()
assert _execution_source()['files']
target = Path(graphunslopify.__file__).parent / 'cli.py'
target.write_bytes(target.read_bytes() + b'\\n# simulated upgrade after import\\n')
try:
    _execution_source()
except ProjectError as error:
    assert 'restart' in str(error)
    print('Actual changed package sources refused after import')
else:
    raise AssertionError('Loaded old code must not adopt new source bytes')
"""
    done = subprocess.run(
        [sys.executable, "-c", program, str(package)],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(package.parent)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_environment_mismatch_is_displayed_without_changing_saved_evidence(paper, monkeypatch):
    actual = review._version
    monkeypatch.setattr(
        review, "_version", lambda name: "changed" if name == "numpy" else actual(name)
    )
    before = bytes_at(paper)
    result = review.project_review(paper)
    for row in result["figures"]:
        assert row["matches_latest_accepted_inputs"]
        assert row["rerun_recommended"]
        assert (
            row["groups"]["reproduction"]["environment"]["state"]
            == "versions_changed_or_incomplete"
        )
    assert before == bytes_at(paper)


def test_invalid_selection_and_concurrent_current_inputs_refuse(paper, monkeypatch):
    with pytest.raises(model.ProjectError, match="intact completed"):
        review.project_review(paper, event_id="../../outside")
    actual = review.project_status
    calls = 0

    def changing(path):
        nonlocal calls
        calls += 1
        if calls == 2:
            data = paper / "results.csv"
            data.write_bytes(data.read_bytes() + b"\n")
        return actual(path)

    monkeypatch.setattr(review, "project_status", changing)
    with pytest.raises(model.ProjectError, match="changed while reading"):
        review.project_review(paper)
