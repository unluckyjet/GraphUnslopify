"""A PDF-only paper has no invented native manifest or scientific acceptance."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from graphunslopify import project as model
from graphunslopify import project_inspections as inspections
from graphunslopify.audit import load_manifest
from graphunslopify.cli import main
from graphunslopify.project_review import project_review

ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "examples/baseline/01-training-curve.pdf"


def inventory(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.fixture
def paper(tmp_path):
    folder = tmp_path / "PDF paper ü with spaces"
    folder.mkdir()
    model.initialize_project(folder, review_only=True)
    return folder


def test_initialization_keeps_native_manifest_contract_and_exclusive_ownership(paper, tmp_path):
    state = model.project_status(paper)
    assert state["schema_version"] == 2 and state["mode"] == "review_only"
    assert state["status"] == "review_only" and state["figures"] == []
    assert not state["matches_last_run_revision"]
    assert not list(paper.glob("*.json"))
    config = json.loads((paper / "graphunslopify-project/project.json").read_text())
    assert config["manifest"] is None and config["shared"] == {}
    original = inventory(paper)
    with pytest.raises(FileExistsError):
        model.initialize_project(paper, review_only=True)
    assert inventory(paper) == original
    invalid = tmp_path / "empty-native.json"
    invalid.write_text(json.dumps({"schema_version": 1, "figures": []}))
    with pytest.raises(ValueError):
        load_manifest(invalid)


@pytest.mark.parametrize("action", ["run", "figure", "shared", "definition", "entry"])
def test_native_actions_are_refused_without_creating_fake_history(paper, action):
    revision = model.project_status(paper)["revision"]
    original = inventory(paper)
    with pytest.raises(model.ProjectError, match="no source-backed figures"):
        if action == "run":
            model.run_project(paper, expected_revision=revision)
        elif action == "figure":
            model.project_figure(paper, "fake")
        elif action == "shared":
            model.set_project_shared(paper, {}, expected_revision=revision)
        elif action == "definition":
            model.set_project_figure(paper, "fake", {}, expected_revision=revision)
        else:
            model.set_project_entry(paper, "fake", {}, expected_revision=revision, mode="add")
    assert inventory(paper) == original
    assert model.project_history(paper)["events"] == []


def test_real_pdf_inspection_and_move_need_no_native_manifest(paper):
    shutil.copyfile(PDF, paper / "external.pdf")
    before = inventory(paper)
    revision = inspections.project_inspections(paper)["revision"]
    result = inspections.inspect_project_pdf(
        paper,
        paper / "external.pdf",
        identity="paper",
        expected_revision=revision,
        pages=[1],
        dpi=72,
    )
    assert result["status"] == "incomplete" and result["exit_code"] == 2
    assert result["audit"] is None and result["snapshot"]["manifest"] is None
    assert result["snapshot"]["figures"] == []
    assert not list(Path(result["directory"]).rglob("*.pdf"))
    assert not (Path(result["directory"]) / "source/manifest.json").exists()
    for name, digest in before.items():
        assert inventory(paper)[name] == digest
    moved = paper.with_name("moved PDF paper")
    shutil.move(paper, moved)
    row = inspections.project_inspections(moved)["sources"][0]
    assert row["freshness"] == "unchanged" and row["assets_verified"]
    assert row["science_status"] == "untested"
    assert model.project_status(moved)["status"] == "review_only"


@pytest.mark.parametrize(
    "change", [{"manifest": "../fake.json"}, {"shared": {"style": {"grid": True}}}, {"extra": True}]
)
def test_review_only_config_cannot_smuggle_native_inputs_or_settings(paper, change):
    file = paper / "graphunslopify-project/project.json"
    file.write_text(json.dumps(json.loads(file.read_text()) | change))
    with pytest.raises(model.ProjectError, match=r"Invalid project\.json"):
        model.project_status(paper)


def test_actual_review_only_cli_without_plotting_manifest(tmp_path, capsys):
    assert main(["project-init", str(tmp_path), "--review-only"]) == 0
    capsys.readouterr()
    assert main(["project-status", str(tmp_path)]) == 0
    state = json.loads(capsys.readouterr().out)
    assert state["status"] == "review_only" and not state["figures"]
    assert main(["project-run", str(tmp_path)]) == 2
    assert "no source-backed figures" in capsys.readouterr().out
    assert model.project_history(tmp_path)["events"] == []


def test_uploaded_pdf_is_locally_retained_ignored_and_never_copied_to_history(paper):
    result = inspections.inspect_uploaded_pdf(
        paper,
        PDF.read_bytes(),
        identity="uploaded",
        name="Paper ü.pdf",
        expected_revision=inspections.project_inspections(paper)["revision"],
        pages=[1],
        dpi=72,
    )
    row = inspections.project_inspections(paper)["sources"][0]
    assert row["name"] == "Paper ü.pdf" and row["origin"] == "uploaded_local_copy"
    source = paper / row["path"]
    assert source.read_bytes() == PDF.read_bytes()
    assert not list(Path(result["directory"]).rglob("*.pdf"))
    git = "/Library/Developer/CommandLineTools/usr/bin/git"
    if not Path(git).is_file():
        git = shutil.which("git")
    assert git, "Git is required for the actual upload-ignore regression control"
    subprocess.run([git, "init", str(paper)], check=True, capture_output=True)
    ignored = subprocess.run(
        [git, "check-ignore", "--quiet", "--", source.relative_to(paper).as_posix()],
        cwd=paper,
        capture_output=True,
        check=False,
    )
    assert ignored.returncode == 0
    before = inventory(paper)
    review = project_review(paper)
    assert review["schema_version"] == 2
    assert len(review["figures"]) == 1
    figure = review["figures"][0]
    assert figure["source_type"] == "pdf" and not figure["matches_latest_accepted_inputs"]
    assert figure["groups"]["claims"]["state"] == "untested"
    assert figure["groups"]["uncertainty"]["state"] == "untested"
    assert figure["groups"]["reproduction"]["source_data"] == "untested"
    assert not figure["groups"]["reproduction"]["native_programs_executed"]
    assert inventory(paper) == before


def test_saved_pdf_selection_never_borrows_later_failed_inspection_or_native_acceptance(paper):
    first = inspections.inspect_uploaded_pdf(
        paper,
        PDF.read_bytes(),
        identity="external",
        name="External.pdf",
        expected_revision=inspections.project_inspections(paper)["revision"],
        pages=[1],
        dpi=72,
    )
    current = inspections.project_inspections(paper)
    file = paper / current["sources"][0]["path"]
    failed = inspections.inspect_project_pdf(
        paper,
        file,
        identity="external",
        expected_revision=current["revision"],
        pages=[1],
        dpi=72,
        timeout=0.001,
    )
    assert failed["status"] == "failed"
    latest = inspections.project_inspections(paper)
    saved = inspections.project_inspections(paper, event_id=first["id"])
    assert latest["sources"][0]["event"] == failed["id"]
    assert latest["sources"][0]["inspection"] is None
    assert saved["revision"] == latest["revision"]
    old = saved["sources"][0]
    assert old["explicit_history_selection"] and old["assets_verified"]
    assert old["evidence_state"] == "historical_or_needs_inspection"
    review = project_review(paper, event_id=first["id"])
    assert (
        review["selection"]["kind"] == "pdf" and not review["selection"]["matches_current_revision"]
    )
    assert review["figures"][0]["inspection"]["event"] == first["id"]
    index = next(i for i, asset in enumerate(old["assets"]) if asset["path"].endswith(".png"))
    data, name = inspections.inspection_asset(paper, first["id"], index)
    assert data.startswith(b"\x89PNG") and name.endswith(".png")
    target = Path(first["directory"]) / old["assets"][index]["path"]
    target.write_bytes(target.read_bytes() + b"changed")
    with pytest.raises(model.ProjectError, match="intact saved PDF"):
        inspections.inspection_asset(paper, first["id"], index)


def test_stale_and_locked_uploads_leave_original_history_and_sources_untouched(paper):
    revision = inspections.project_inspections(paper)["revision"]
    config = paper / "graphunslopify-project/project.json"
    config.write_bytes(config.read_bytes() + b"\n")
    before = inventory(paper)
    with pytest.raises(model.ProjectError, match="changed since review"):
        inspections.inspect_uploaded_pdf(
            paper,
            PDF.read_bytes(),
            identity="external",
            name="External.pdf",
            expected_revision=revision,
            pages=[1],
            dpi=72,
        )
    assert inventory(paper) == before
    revision = inspections.project_inspections(paper)["revision"]
    lock = config.parent / ".operation.lock"
    lock.write_text('{"token":"another-owner","pid":1}')
    before = inventory(paper)
    with pytest.raises(model.ProjectError, match="locked"):
        inspections.inspect_uploaded_pdf(
            paper,
            PDF.read_bytes(),
            identity="external",
            name="External.pdf",
            expected_revision=revision,
            pages=[1],
            dpi=72,
        )
    assert inventory(paper) == before
