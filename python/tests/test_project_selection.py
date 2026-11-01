"""Selection ownership, actual targeted regeneration and unchanged scientific inputs."""

import json
import shutil
from pathlib import Path

import pytest

from graphunslopify.project import (
    ProjectError,
    _capture,
    _config,
    _operation,
    initialize_project,
    project_history,
    project_status,
    run_project,
    set_project_shared,
)
from graphunslopify.project_inspections import inspect_project_pdf, project_inspections
from graphunslopify.project_selection import apply_project_selection, review_project_selection

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = {"style": {"grid": True}, "output": {"dpi": 144}}


@pytest.fixture
def paper(tmp_path):
    paper = tmp_path / "paper with spaces"
    shutil.copytree(ROOT / "examples/paper", paper)
    initialize_project(paper)
    return paper


def inventory(paper):
    return {str(p.relative_to(paper)): p.read_bytes() for p in paper.rglob("*") if p.is_file()}


def review(paper, ids=None, settings=SETTINGS, **kwargs):
    return review_project_selection(
        paper,
        ["training"] if ids is None else ids,
        settings,
        expected_revision=project_status(paper)["revision"],
        **kwargs,
    )


def apply(paper, plan):
    args = (
        {"undo_event": plan["undo_event"]}
        if plan["undo_event"]
        else {"ids": plan["ids"], "settings": plan["settings"], "reset": plan["reset"]}
    )
    return apply_project_selection(
        paper, expected_revision=plan["revision"], proposal_token=plan["proposal_token"], **args
    )


def test_review_has_no_writes_and_selected_fingerprint_is_the_only_changed_one(paper):
    before = inventory(paper)
    plan = review(paper)
    assert inventory(paper) == before
    assert plan["can_apply"] and plan["requires_audit"] and plan["execution"] == "not_run"
    assert plan["affected_ids"] == ["training"] and not plan["excluded"]
    assert plan["figures"][0]["after"]["output"]["dpi"] == 144
    assert review(paper)["proposal_token"] == plan["proposal_token"]
    source, config = _config(paper)
    old = _capture(source, config)[0]
    candidate = _capture(source, config, figure_settings_override=plan["figure_settings"])[0]
    assert old["figures"][0]["fingerprint"] != candidate["figures"][0]["fingerprint"]
    assert old["figures"][1] == candidate["figures"][1]


def test_actual_selected_audit_and_undo_preserve_data_definitions_and_binding(paper):
    original_files = {p.name: p.read_bytes() for p in paper.iterdir() if p.is_file()}
    config = paper / "graphunslopify-project/project.json"
    original_config = config.read_bytes()
    initial = run_project(paper, baseline=None)
    assert initial["exit_code"] == 0
    saved = apply(paper, review(paper))
    assert saved["status"] == "selection_saved"
    state = project_status(paper)
    assert state["schema_version"] == 3 and state["status"] == "needs_audit"
    assert {r["id"]: r["freshness"] for r in state["figures"]} == {
        "training": "changed",
        "results-table": "unchanged",
    }
    current = run_project(paper, selective=True)
    assert current["exit_code"] == 0, current
    rows = {r["id"]: r for r in current["audit"]["figures"]}
    assert rows["training"]["execution"]["mode"] == "executed"
    assert rows["results-table"]["execution"]["mode"] == "reused"
    assert rows["training"]["report"]["spec"]["output"]["dpi"] == 144
    assert rows["results-table"]["report"] == initial["audit"]["figures"][1]["report"]
    assert {p.name: p.read_bytes() for p in paper.iterdir() if p.is_file()} == original_files
    undo = review_project_selection(
        paper, expected_revision=project_status(paper)["revision"], undo_event=saved["id"]
    )
    assert apply(paper, undo)["undo_of"] == saved["id"]
    assert (
        config.read_bytes() == original_config and project_history(paper)["integrity"] == "verified"
    )


@pytest.mark.parametrize(
    "settings",
    [
        {"data": {}},
        {"claims": []},
        {"palette_lock": "x"},
        {"output": {"stem": "x"}},
        {"output": {"dpi": 0}},
        {"style": {"grid": "yes"}},
        {},
    ],
)
def test_scientific_or_invalid_settings_refuse_before_writes(paper, settings):
    before = inventory(paper)
    with pytest.raises((ProjectError, ValueError)):
        review(paper, settings=settings)
    assert inventory(paper) == before


@pytest.mark.parametrize("mutation", ["data", "history", "selection"])
def test_changed_proposal_context_never_writes_new_history(paper, mutation):
    plan = review(paper)
    if mutation == "data":
        p = paper / "results.csv"
        p.write_bytes(p.read_bytes() + b"\n")
    elif mutation == "history":
        set_project_shared(paper, {}, expected_revision=project_status(paper)["revision"])
    else:
        apply(paper, review(paper, settings={"style": {"despine": False}}))
    before = inventory(paper)
    with pytest.raises(ProjectError, match=r"changed|stale"):
        apply(paper, plan)
    assert inventory(paper) == before


def test_reset_restores_paper_defaults_and_undo_retains_later_source_changes(paper):
    set_project_shared(
        paper, {"output": {"dpi": 150}}, expected_revision=project_status(paper)["revision"]
    )
    saved = apply(paper, review(paper))
    p = paper / "results.csv"
    p.write_bytes(p.read_bytes() + b"\n")
    source_before = p.read_bytes()
    undo = review_project_selection(
        paper, expected_revision=project_status(paper)["revision"], undo_event=saved["id"]
    )
    apply(paper, undo)
    assert p.read_bytes() == source_before
    apply(paper, review(paper))
    plan = review(paper, settings=None, reset=True)
    assert plan["figures"][0]["after"]["output"]["dpi"] == 150
    apply(paper, plan)
    assert project_status(paper)["figure_settings"] == {}


def test_shared_source_bindings_remain_distinct_and_shared_policy_respects_selection(paper):
    path = paper / "figures.json"
    if not path.exists():
        path = next(
            p
            for p in paper.glob("*.json")
            if isinstance(json.loads(p.read_text()).get("figures"), list)
        )
    manifest = json.loads(path.read_text())
    manifest["figures"][1]["spec"] = manifest["figures"][0]["spec"]
    path.write_text(json.dumps(manifest))
    original = inventory(paper)
    saved = apply(paper, review(paper))
    set_project_shared(
        paper, {"output": {"dpi": 300}}, expected_revision=project_status(paper)["revision"]
    )
    source, config = _config(paper)
    figures = _capture(source, config)[1]["figures"]
    assert [r["spec"]["output"]["dpi"] for r in figures] == [144, 300]
    for name, data in original.items():
        if not name.startswith("graphunslopify-project/"):
            assert (paper / name).read_bytes() == data
    before = inventory(paper)
    with pytest.raises(ProjectError, match="Other project settings"):
        review_project_selection(
            paper, expected_revision=project_status(paper)["revision"], undo_event=saved["id"]
        )
    assert inventory(paper) == before


def test_mixed_authored_and_pdf_selection_is_explicit_and_never_executes(paper):
    manifest = next(
        p
        for p in paper.glob("*.json")
        if isinstance(json.loads(p.read_text()).get("figures"), list)
    )
    value = json.loads(manifest.read_text())
    value["figures"].append({"id": "authored", "script": "do-not-run.py", "data": "results.csv"})
    manifest.write_text(json.dumps(value))
    script = paper / "do-not-run.py"
    script.write_text("raise RuntimeError('review must never execute this program')\n")
    result = inspect_project_pdf(
        paper,
        ROOT / "python/tests/fixtures/project-review-pages.pdf",
        identity="external",
        expected_revision=project_inspections(paper)["revision"],
        pages=[1],
        dpi=72,
    )
    assert result["exit_code"] == 2
    before = inventory(paper)
    plan = review(paper, ["training", "authored", "pdf:external"])
    assert {r["id"] for r in plan["excluded"]} == {"authored", "pdf:external"}
    assert plan["affected_ids"] == ["training"] and inventory(paper) == before
    apply(paper, plan)
    assert project_status(paper)["figure_settings"] == {"training": SETTINGS}
    assert script.read_bytes() == before[script.name]


def test_operation_lock_and_tampered_proposal_refuse_without_a_new_event(paper):
    plan = review(paper)
    before = inventory(paper)
    with _operation(paper / "graphunslopify-project"), pytest.raises(ProjectError):
        apply(paper, plan)
    assert inventory(paper) == before
    plan["settings"] = {"output": {"dpi": 288}}
    with pytest.raises(ProjectError, match="stale"):
        apply(paper, plan)
    assert inventory(paper) == before


def test_new_pdf_collection_invalidates_a_review_without_native_revision_change(paper):
    plan = review(paper)
    inspected = inspect_project_pdf(
        paper,
        ROOT / "python/tests/fixtures/project-review-pages.pdf",
        identity="late",
        expected_revision=project_inspections(paper)["revision"],
        pages=[1],
        dpi=72,
    )
    assert inspected["exit_code"] == 2
    assert project_status(paper)["revision"] == plan["revision"]
    before = inventory(paper)
    with pytest.raises(ProjectError, match="stale"):
        apply(paper, plan)
    assert inventory(paper) == before


def test_failed_owned_write_retains_incomplete_evidence_and_original_configuration(
    paper, monkeypatch
):
    from graphunslopify import project_selection as selection

    plan = review(paper)
    config = paper / "graphunslopify-project/project.json"
    original = config.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("controlled owned-write failure")

    monkeypatch.setattr(selection, "_write_authoring", fail)
    with pytest.raises(OSError, match="controlled owned-write failure"):
        apply(paper, plan)
    history = project_history(paper)
    assert config.read_bytes() == original
    assert history["integrity"] == "partial"
    assert history["events"][0]["phase"] == "incomplete"
    assert not history["events"][0]["integrity"]
