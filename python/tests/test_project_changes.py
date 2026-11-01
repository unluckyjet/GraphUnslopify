"""Real resolved shared intent, unchanged source bytes and history-bound undo."""

import json
import shutil
from pathlib import Path

import pytest

from graphunslopify import project_changes as changes
from graphunslopify.project import (
    ProjectError,
    initialize_project,
    project_history,
    project_status,
    run_project,
    set_project_shared,
)
from graphunslopify.project_inspections import inspect_project_pdf, project_inspections

ROOT = Path(__file__).resolve().parents[2]
SHARED = {"style": {"grid": True}, "output": {"size": "double_column", "dpi": 144}}


@pytest.fixture
def paper(tmp_path):
    result = tmp_path / "paper ü with spaces"
    shutil.copytree(ROOT / "examples/paper", result)
    initialize_project(result)
    return result


def inventory(paper):
    return {str(p.relative_to(paper)): p.read_bytes() for p in paper.rglob("*") if p.is_file()}


def review(paper, shared=SHARED, **kwargs):
    return changes.review_project_shared(
        paper, shared, expected_revision=project_status(paper)["revision"], **kwargs
    )


def apply(paper, plan):
    return changes.apply_project_shared(
        paper,
        None if plan["undo_event"] else plan["shared"],
        expected_revision=plan["revision"],
        proposal_token=plan["proposal_token"],
        undo_event=plan["undo_event"],
    )


def test_review_resolves_defaults_and_changes_without_writes_or_science_acceptance(paper):
    before = inventory(paper)
    plan = review(paper)
    assert plan["can_apply"] and plan["execution"] == "not_run" and plan["requires_audit"]
    assert set(plan["affected_ids"]) == {"training", "results-table"}
    assert all(row["state"] == "validated_intent" and not row["errors"] for row in plan["figures"])
    assert any(
        change["path"] == "/output/dpi" and change["after"] == 144
        for row in plan["figures"]
        for change in row["changes"]
    )
    assert all(row["after"]["output"]["dpi"] == 144 for row in plan["figures"])
    assert inventory(paper) == before
    assert review(paper)["proposal_token"] == plan["proposal_token"]


def test_actual_apply_audit_and_raw_configuration_undo_preserve_sources(paper):
    config = paper / "graphunslopify-project/project.json"
    value = json.loads(config.read_text())
    config.write_text(json.dumps(value, indent=4))
    original = config.read_bytes()
    source = {p.name: p.read_bytes() for p in paper.iterdir() if p.is_file()}
    plan = review(paper)
    saved = apply(paper, plan)
    assert saved["status"] == "settings_saved" and saved["review"] == plan
    assert project_status(paper)["status"] == "needs_audit"
    actual = run_project(paper, baseline=None)
    assert actual["exit_code"] == 0, actual
    assert all(row["report"]["spec"]["output"]["dpi"] == 144 for row in actual["audit"]["figures"])
    undo = review(paper, None, undo_event=saved["id"])
    reverted = apply(paper, undo)
    assert reverted["undo_of"] == saved["id"] and config.read_bytes() == original
    assert {p.name: p.read_bytes() for p in paper.iterdir() if p.is_file()} == source
    assert project_history(paper)["integrity"] == "verified"
    assert project_status(paper)["status"] == "needs_audit"


def test_undo_preserves_later_data_and_definition_changes_but_requires_their_current_token(paper):
    saved = apply(paper, review(paper))
    source = paper / "training.figure.json"
    raw = json.loads(source.read_text())
    raw["title"] = "A later title"
    source.write_text(json.dumps(raw))
    data = paper / "results.csv"
    data.write_bytes(data.read_bytes() + b"\n")
    before = {p.name: p.read_bytes() for p in paper.iterdir() if p.is_file()}
    apply(paper, review(paper, None, undo_event=saved["id"]))
    assert {p.name: p.read_bytes() for p in paper.iterdir() if p.is_file()} == before
    assert project_status(paper)["shared"] == {}


@pytest.mark.parametrize(
    "value", [{"data": {}}, {"claims": []}, {"style": {"grid": "yes"}}, {"output": {"dpi": 0}}, []]
)
def test_invalid_or_scientific_shared_patches_never_write(paper, value):
    before = inventory(paper)
    with pytest.raises((ProjectError, ValueError)):
        review(paper, value)
    assert inventory(paper) == before


@pytest.mark.parametrize("mutation", ["data", "definition", "settings", "history"])
def test_stale_review_rejects_before_new_history(paper, mutation):
    plan = review(paper)
    if mutation == "data":
        file = paper / "results.csv"
        file.write_bytes(file.read_bytes() + b"\n")
    elif mutation == "definition":
        file = paper / "training.figure.json"
        raw = json.loads(file.read_text())
        raw["title"] = "Changed"
        file.write_text(json.dumps(raw))
    elif mutation == "settings":
        set_project_shared(
            paper, {"output": {"dpi": 145}}, expected_revision=project_status(paper)["revision"]
        )
    else:
        # A completed no-op legacy change still changes the reviewed history.
        set_project_shared(paper, {}, expected_revision=project_status(paper)["revision"])
    before = inventory(paper)
    with pytest.raises(ProjectError, match=r"changed|stale"):
        apply(paper, plan)
    assert inventory(paper) == before


def test_proposed_new_palette_bytes_are_bound_even_before_becoming_current_inputs(paper):
    palette = paper / "next-palette.json"
    palette.write_text('{"first":1}')
    plan = review(paper, {"palette_lock": palette.name})
    revision = project_status(paper)["revision"]
    palette.write_text('{"second":2}')
    assert project_status(paper)["revision"] == revision
    before = inventory(paper)
    with pytest.raises(ProjectError, match="stale"):
        apply(paper, plan)
    assert inventory(paper) == before


def test_actual_pdf_added_after_review_invalidates_the_collection_without_native_drift(paper):
    plan = review(paper)
    pdf = ROOT / "python/tests/fixtures/project-review-pages.pdf"
    inspected = inspect_project_pdf(
        paper,
        pdf,
        identity="external",
        expected_revision=project_inspections(paper)["revision"],
        pages=[1],
        dpi=72,
    )
    assert inspected["exit_code"] == 2 and project_status(paper)["revision"] == plan["revision"]
    before = inventory(paper)
    with pytest.raises(ProjectError, match="stale"):
        apply(paper, plan)
    assert inventory(paper) == before
    fresh = review(paper)
    assert fresh["pdf_excluded"][0]["id"] == "external"
    assert "external" not in fresh["affected_ids"]


def test_conflicting_later_settings_cannot_be_undone_from_an_older_event(paper):
    old = apply(paper, review(paper))
    set_project_shared(
        paper, {"output": {"dpi": 150}}, expected_revision=project_status(paper)["revision"]
    )
    before = inventory(paper)
    with pytest.raises(ProjectError, match="conflict"):
        review(paper, None, undo_event=old["id"])
    assert inventory(paper) == before


def test_damaged_original_configuration_and_partial_history_block_undo(paper):
    old = apply(paper, review(paper))
    file = Path(old["directory"]) / "source/project.json"
    file.write_bytes(file.read_bytes() + b" ")
    before = inventory(paper)
    with pytest.raises(ProjectError, match="history"):
        review(paper, None, undo_event=old["id"])
    assert inventory(paper) == before


def test_authored_program_is_never_executed_or_rewritten_by_review_or_apply(paper):
    manifest = paper / "graphunslopify.json"
    value = json.loads(manifest.read_text())
    program = paper / "authored.py"
    program.write_text("from pathlib import Path\nPath('executed').write_text('ran')\n")
    value["figures"][1] = {"id": "authored", "script": program.name, "data": "results.csv"}
    manifest.write_text(json.dumps(value))
    plan = review(paper)
    row = next(r for r in plan["figures"] if r["id"] == "authored")
    assert row["state"] == "manual_source_review" and row["affected"] and row["before"] is None
    original = program.read_bytes()
    apply(paper, plan)
    assert program.read_bytes() == original and not (paper / "executed").exists()


def test_real_data_change_after_actual_prepare_is_refused_before_history(paper, monkeypatch):
    plan = review(paper)
    prepare = changes._prepare

    def prepare_then_edit(*args, **kwargs):
        result = prepare(*args, **kwargs)
        file = paper / "results.csv"
        file.write_bytes(file.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(changes, "_prepare", prepare_then_edit)
    with pytest.raises(ProjectError, match="changed"):
        apply(paper, plan)
    assert project_history(paper)["events"] == []
    assert project_status(paper)["shared"] == {}
    assert not (paper / "graphunslopify-project/.operation.lock").exists()


def test_review_only_project_cannot_acquire_dummy_native_style_acceptance(tmp_path):
    initialize_project(tmp_path, review_only=True)
    before = inventory(tmp_path)
    with pytest.raises(ProjectError, match="review-only"):
        review(tmp_path)
    assert inventory(tmp_path) == before


def test_invalid_native_intent_remains_visible_and_cannot_be_applied(paper):
    file = paper / "training.figure.json"
    value = json.loads(file.read_text())
    value["uncertainty"]["level"] = 1.5
    file.write_text(json.dumps(value))
    plan = review(paper)
    row = next(r for r in plan["figures"] if r["id"] == "training")
    assert row["errors"] and row["state"] == "invalid" and not plan["can_apply"]
    before = inventory(paper)
    with pytest.raises(ProjectError, match="invalid intent"):
        apply(paper, plan)
    assert inventory(paper) == before


def test_no_change_is_a_successful_read_with_no_apply_or_history(paper):
    plan = review(paper, {})
    assert plan["exit_code"] == 0 and not plan["can_apply"] and plan["affected_ids"] == []
    before = inventory(paper)
    with pytest.raises(ProjectError, match="no shared settings change"):
        apply(paper, plan)
    assert inventory(paper) == before


def test_review_token_cannot_be_replayed_into_another_owned_project(paper, tmp_path):
    plan = review(paper)
    other = tmp_path / "other"
    shutil.copytree(ROOT / "examples/paper", other)
    initialize_project(other)
    before = inventory(other)
    with pytest.raises(ProjectError, match="stale"):
        changes.apply_project_shared(
            other,
            SHARED,
            expected_revision=project_status(other)["revision"],
            proposal_token=plan["proposal_token"],
        )
    assert inventory(other) == before


def test_retained_review_must_fit_the_real_history_metadata_reader(paper, monkeypatch):
    plan = review(paper)
    monkeypatch.setattr(changes, "MAX_SOURCE_BYTES", len(changes._bytes(plan)) + 1)
    before = inventory(paper)
    with pytest.raises(ProjectError, match="history limit"):
        review(paper)
    assert inventory(paper) == before
