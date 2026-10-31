"""Actual visual packets never borrow native numerical acceptance or hide drift."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from graphunslopify import project as model
from graphunslopify import project_inspections as inspections
from graphunslopify.cli import main

ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "examples/baseline/01-training-curve.pdf"
OTHER_PDF = ROOT / "examples/baseline/02-loss-log.pdf"


def inventory(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.fixture(scope="module")
def checked(tmp_path_factory):
    root = tmp_path_factory.mktemp("inspected-original") / "paper with spaces"
    shutil.copytree(ROOT / "examples/paper", root)
    shutil.copyfile(PDF, root / "external.pdf")
    model.initialize_project(root)
    assert model.run_project(root)["exit_code"] == 0
    revision = inspections.project_inspections(root)["revision"]
    result = inspections.inspect_project_pdf(
        root,
        root / "external.pdf",
        identity="external",
        expected_revision=revision,
        pages=[1],
        dpi=72,
    )
    assert result["exit_code"] == 2 and result["status"] == "incomplete", result
    return root


@pytest.fixture
def paper(checked, tmp_path):
    root = tmp_path / "moved paper"
    shutil.copytree(checked, root)
    return root


def test_real_saved_visual_evidence_moves_without_borrowing_native_acceptance(paper):
    native = model.project_status(paper)
    result = inspections.project_inspections(paper)
    assert native["status"] == "inputs_match_last_run"
    row = result["sources"][0]
    assert row["path"] == "external.pdf" and row["freshness"] == "unchanged"
    assert row["assets_verified"] and row["evidence_state"] == "saved_visual_evidence"
    assert row["science_status"] == "untested" and row["operation_status"] == "incomplete"
    assert all(check["status"] == "untested" for check in row["inspection"]["checks"])
    history = model.project_history(paper)
    assert history["integrity"] == "verified"
    assert history["events"][0]["action"] == "inspection"
    assert all(item["last_run"] != row["event"] for item in native["figures"])
    assert not list((paper / "graphunslopify-project/history" / row["event"]).rglob("*.pdf"))


def test_query_is_read_only_and_never_executes_native_programs(paper, monkeypatch):
    before = inventory(paper)
    monkeypatch.setattr(
        inspections, "_run", lambda *a, **k: pytest.fail("query executed a process")
    )
    result = inspections.project_inspections(paper)
    assert result["query_status"] == "ok"
    assert inventory(paper) == before


def test_changed_source_remains_historical_and_changes_review_revision(paper):
    before = inspections.project_inspections(paper)
    shutil.copyfile(OTHER_PDF, paper / "external.pdf")
    after = inspections.project_inspections(paper)
    row = after["sources"][0]
    assert after["revision"] != before["revision"]
    assert (
        row["freshness"] == "changed" and row["evidence_state"] == "historical_or_needs_inspection"
    )
    assert row["assets_verified"] and row["science_status"] == "untested"
    with pytest.raises(model.ProjectError, match="changed since review"):
        inspections.inspect_project_pdf(
            paper,
            paper / "external.pdf",
            identity="external",
            expected_revision=before["revision"],
            pages=[1],
        )


def test_missing_source_does_not_erase_saved_inspection(paper):
    (paper / "external.pdf").unlink()
    row = inspections.project_inspections(paper)["sources"][0]
    assert row["freshness"] == "unavailable" and row["inspection"]
    assert row["evidence_state"] == "historical_or_needs_inspection"


def test_tampered_rendered_asset_is_separate_from_receipt_integrity(paper):
    row = inspections.project_inspections(paper)["sources"][0]
    image = next(a for a in row["assets"] if a["path"].endswith(".png"))
    target = paper / "graphunslopify-project/history" / row["event"] / image["path"]
    target.write_bytes(b"changed image")
    assert model.project_history(paper)["integrity"] == "verified"
    after = inspections.project_inspections(paper)["sources"][0]
    assert not after["assets_verified"]
    assert after["evidence_state"] == "historical_or_needs_inspection"


def test_real_timeout_keeps_a_failed_event_and_does_not_fall_back(paper):
    before = inspections.project_inspections(paper)
    result = inspections.inspect_project_pdf(
        paper,
        paper / "external.pdf",
        identity="external",
        expected_revision=before["revision"],
        pages=[1],
        timeout=0.001,
    )
    assert result["status"] == "failed" and result["exit_code"] == 2
    assert any("exceeded" in e for e in result["errors"])
    assert (Path(result["directory"]) / "inspection.stdout.log").is_file()
    assert (Path(result["directory"]) / "inspection.stderr.log").is_file()
    after = inspections.project_inspections(paper)
    assert after["sources"][0]["event"] == result["id"]
    assert after["sources"][0]["inspection"] is None
    assert after["sources"][0]["evidence_state"] == "historical_or_needs_inspection"
    assert model.project_history(paper)["integrity"] == "verified"


def test_incomplete_newer_history_blocks_current_visual_label(paper):
    model._event(paper / "graphunslopify-project", "inspection")
    result = inspections.project_inspections(paper)
    assert result["query_status"] == "partial"
    assert result["sources"][0]["evidence_state"] == "historical_or_needs_inspection"
    with pytest.raises(model.ProjectError, match="history"):
        inspections.inspect_project_pdf(
            paper,
            paper / "external.pdf",
            identity="next",
            expected_revision=result["revision"],
            pages=[1],
        )


def test_invalid_inputs_native_collisions_and_owned_lock_do_not_create_events(paper):
    before = model.project_history(paper)
    revision = inspections.project_inspections(paper)["revision"]
    for identity, timeout, pages in [
        ("../escape", 120, [1]),
        ("training", 120, [1]),
        ("external", float("nan"), [1]),
        ("external", 120, [0]),
    ]:
        with pytest.raises(model.ProjectError):
            inspections.inspect_project_pdf(
                paper,
                paper / "external.pdf",
                identity=identity,
                expected_revision=revision,
                timeout=timeout,
                pages=pages,
            )
    lock = paper / "graphunslopify-project/.operation.lock"
    lock.write_text('{"token":"someone-else"}')
    with pytest.raises(model.ProjectError, match="locked"):
        inspections.inspect_project_pdf(
            paper, paper / "external.pdf", identity="next", expected_revision=revision, pages=[1]
        )
    assert lock.read_text() == '{"token":"someone-else"}'
    lock.unlink()
    assert model.project_history(paper) == before


def test_cli_read_success_is_separate_from_actual_inspection_incompleteness(paper, capsys):
    assert main(["project-inspections", str(paper)]) == 0
    current = json.loads(capsys.readouterr().out)
    assert (
        main(
            [
                "project-inspect-pdf",
                str(paper),
                "--id",
                "second-pdf",
                "--pdf",
                str(paper / "external.pdf"),
                "--expected-revision",
                current["revision"],
                "--pages",
                "1",
                "--dpi",
                "72",
            ]
        )
        == 2
    )
    created = json.loads(capsys.readouterr().out)
    assert created["status"] == "incomplete" and created["inspection"]["status"] == "incomplete"


def test_actual_pdf_source_change_during_worker_rejects_current_evidence(paper, monkeypatch):
    before = inspections.project_inspections(paper)
    actual = inspections._run

    def changed(*args, **kwargs):
        result = actual(*args, **kwargs)
        shutil.copyfile(OTHER_PDF, paper / "external.pdf")
        return result

    monkeypatch.setattr(inspections, "_run", changed)
    result = inspections.inspect_project_pdf(
        paper,
        paper / "external.pdf",
        identity="external",
        expected_revision=before["revision"],
        pages=[1],
        dpi=72,
    )
    assert result["status"] == "failed" and result["exit_code"] == 2
    assert any("changed during inspection" in e for e in result["errors"])
    row = inspections.project_inspections(paper)["sources"][0]
    assert (
        row["freshness"] == "changed" and row["evidence_state"] == "historical_or_needs_inspection"
    )
    assert model.project_status(paper)["status"] == "inputs_match_last_run"


def test_actual_native_input_change_during_inspection_is_not_current(paper, monkeypatch):
    before = inspections.project_inspections(paper)
    actual = inspections._run

    def changed(*args, **kwargs):
        result = actual(*args, **kwargs)
        data = paper / "results.csv"
        data.write_bytes(data.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(inspections, "_run", changed)
    result = inspections.inspect_project_pdf(
        paper,
        paper / "external.pdf",
        identity="external",
        expected_revision=before["revision"],
        pages=[1],
        dpi=72,
    )
    assert result["status"] == "failed" and any(
        "changed during inspection" in e for e in result["errors"]
    )
    assert model.project_status(paper)["status"] == "needs_audit"
    assert (
        inspections.project_inspections(paper)["sources"][0]["evidence_state"]
        == "historical_or_needs_inspection"
    )
