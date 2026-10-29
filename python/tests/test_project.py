"""Real project audits, retained failures, shared policy and declared-input freshness."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from graphunslopify import Figure
from graphunslopify import project as model
from graphunslopify.cli import main
from graphunslopify.project import (
    ProjectError,
    initialize_project,
    project_figure,
    project_history,
    project_status,
    run_project,
    set_project_entry,
    set_project_figure,
    set_project_shared,
)
from graphunslopify.provenance import read_provenance

ROOT = Path(__file__).resolve().parents[2]


def create(root):
    shutil.copytree(ROOT / "examples/paper", root)
    return Path(initialize_project(root)["config"])


@pytest.fixture(scope="module")
def checked(tmp_path_factory):
    config = create(tmp_path_factory.mktemp("project-module") / "paper ü with spaces")
    result = run_project(config)
    assert result["status"] == "passed" and result["exit_code"] == 0, result
    return config.parent.parent


@pytest.fixture
def copy(checked, tmp_path):
    root = tmp_path / "paper moved"
    shutil.copytree(checked, root)
    return root / "graphunslopify-project/project.json"


def test_exclusive_initialization_preserves_all_originals_and_no_data_is_snapshotted(tmp_path):
    root = tmp_path / "paper"
    shutil.copytree(ROOT / "examples/paper", root)
    original = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    created = initialize_project(root)
    for name, raw in original.items():
        assert (root / name).read_bytes() == raw
    with pytest.raises(FileExistsError):
        initialize_project(root)
    assert all(f["freshness"] == "not_run" for f in project_status(created["config"])["figures"])
    result = run_project(created["config"])
    assert result["exit_code"] == 0
    assert not list(Path(created["config"]).parent.rglob("*.csv"))


def test_actual_status_history_and_cli_are_portable_read_queries(copy, capsys):
    assert main(["project-status", str(copy)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "inputs_match_last_run"
    assert {r["id"] for r in status["figures"]} == {"training", "results-table"}
    assert all(r["last_status"] == "passed" and r["artifacts_verified"] for r in status["figures"])
    assert main(["project-history", str(copy)]) == 0
    history = json.loads(capsys.readouterr().out)
    assert history["integrity"] == "verified" and len(history["events"]) == 1
    assert history["events"][0]["result"]["audit"]["status"] == "passed"


def test_failed_claim_and_recovery_keep_prior_records_and_per_figure_status(copy):
    old = next((copy.parent / "history").iterdir())
    original = {str(p.relative_to(old)): p.read_bytes() for p in old.rglob("*") if p.is_file()}
    source = copy.parent.parent / "training.figure.json"
    raw = source.read_bytes()
    spec = json.loads(raw)
    spec["claims"][0].update(subject="base", reference="ours")
    source.write_text(json.dumps(spec))
    failed = run_project(copy)
    assert failed["exit_code"] == 2 and failed["audit_status"] == "failed"
    assert failed["baseline"] == old.name
    rows = {r["id"]: r for r in project_status(copy)["figures"]}
    assert rows["training"]["last_status"] == "failed"
    assert rows["results-table"]["last_status"] == "passed"
    source.write_bytes(raw)
    assert project_status(copy)["status"] == "needs_audit"
    recovered = run_project(copy)
    assert recovered["exit_code"] == 0
    assert len(project_history(copy)["events"]) == 3
    assert original == {
        str(p.relative_to(old)): p.read_bytes() for p in old.rglob("*") if p.is_file()
    }


def test_shared_settings_apply_to_actual_exports_without_rewriting_sources(copy):
    paper = copy.parent.parent
    original = {str(p): p.read_bytes() for p in paper.iterdir() if p.is_file()}
    revision = project_status(copy)["revision"]
    shared = {"style": {"grid": True}, "output": {"size": "double_column", "dpi": 144}}
    event = set_project_shared(copy, shared, expected_revision=revision)
    assert event["status"] == "settings_saved"
    assert all(r["freshness"] == "changed" for r in project_status(copy)["figures"])
    result = run_project(copy)
    assert result["exit_code"] == 0, result
    for figure in result["audit"]["figures"]:
        report = figure["report"]
        assert report["spec"]["style"]["grid"] is True
        assert report["spec"]["output"]["size"] == "double_column"
        assert report["environment"]["rendering"]["target_width_in"] > 6
        output = next(x for x in figure["outputs"] if x["format"] == "png")
        provenance = read_provenance(Path(result["directory"]) / "audit" / output["path"])
        assert provenance["spec"] == report["spec"]
    assert original == {str(p): p.read_bytes() for p in paper.iterdir() if p.is_file()}
    assert project_status(copy)["status"] == "inputs_match_last_run"


def test_changed_definition_only_stales_its_figure_but_shared_data_stales_both(copy):
    paper = copy.parent.parent
    path = paper / "training.figure.json"
    value = json.loads(path.read_text())
    value["title"] = "New title"
    path.write_text(json.dumps(value))
    rows = {r["id"]: r for r in project_status(copy)["figures"]}
    assert (
        rows["training"]["freshness"] == "changed"
        and rows["results-table"]["freshness"] == "unchanged"
    )
    data = paper / "results.csv"
    data.write_bytes(data.read_bytes() + b"\n")
    assert all(r["freshness"] == "changed" for r in project_status(copy)["figures"])


def test_revision_and_operation_guards_refuse_stale_writes_and_runs(copy):
    token = project_status(copy)["revision"]
    current = copy.read_bytes()
    source = copy.parent.parent / "training.figure.json"
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ProjectError, match="changed since review"):
        set_project_shared(copy, {}, expected_revision=token)
    with pytest.raises(ProjectError, match="changed since review"):
        run_project(copy, expected_revision=token)
    assert copy.read_bytes() == current
    with model._operation(copy.parent):
        with pytest.raises(ProjectError, match="locked"):
            run_project(copy)
        with pytest.raises(ProjectError, match="locked"):
            set_project_shared(copy, {}, expected_revision=project_status(copy)["revision"])
    assert not (copy.parent / ".operation.lock").exists()
    assert len(project_history(copy)["events"]) == 1


@pytest.mark.parametrize(
    "settings",
    [
        {"color": "red"},
        {"output": {"stem": "x"}},
        {"output": {"dpi": 1}},
        {"style": {"font_size": 99}},
        {"palette_lock": "https://example.org/lock"},
    ],
)
def test_shared_schema_refuses_unknown_presentation_or_invalid_values_without_writes(
    copy, settings
):
    before = copy.read_bytes()
    with pytest.raises(ValueError):
        set_project_shared(copy, settings, expected_revision=project_status(copy)["revision"])
    assert copy.read_bytes() == before and len(project_history(copy)["events"]) == 1


@pytest.mark.parametrize(
    "name", ["result.json", "source/0000.json", "audit/audit.report.json", "receipt.json"]
)
def test_damaged_or_missing_completed_evidence_never_reuses_an_old_pass(copy, name):
    folder = next((copy.parent / "history").iterdir())
    target = folder / name
    if name == "receipt.json":
        target.unlink()
    else:
        target.write_text("damaged")
    history = project_history(copy)
    assert history["exit_code"] == 2 and not history["events"][0]["integrity"]
    assert project_status(copy)["status"] == "needs_audit"


def test_changed_export_is_unavailable_even_when_saved_reports_are_intact(copy):
    event = project_history(copy)["events"][0]
    report = event["result"]["audit"]
    item = report["figures"][0]["outputs"][0]
    path = copy.parent / "history" / event["id"] / "audit" / item["path"]
    path.write_bytes(b"changed PNG")
    rows = project_status(copy)["figures"]
    assert rows[0]["freshness"] == "unavailable" and not rows[0]["artifacts_verified"]
    assert rows[1]["freshness"] == "unchanged"


def test_interrupted_history_is_explicit_and_independent_recovery_can_follow_it(copy):
    target = copy.parent / "history" / ("00000002-" + "a" * 32)
    target.mkdir()
    (target / "started.json").write_text("{}")
    assert project_history(copy)["events"][0]["phase"] == "incomplete"
    assert project_status(copy)["status"] == "needs_audit"
    with pytest.raises(ProjectError, match="incomplete/damaged"):
        run_project(copy)
    assert run_project(copy, baseline=None)["exit_code"] == 0
    assert project_status(copy)["status"] == "inputs_match_last_run"
    assert project_history(copy)["integrity"] == "partial"


def test_setup_failure_is_recorded_and_does_not_fall_back_after_manifest_recovery(copy):
    source = copy.parent.parent / "graphunslopify.json"
    raw = source.read_bytes()
    source.write_text("{")
    failed = run_project(copy)
    assert failed["exit_code"] == 2 and failed["audit_status"] == "not_run"
    assert (Path(failed["directory"]) / "source/manifest.json").read_text() == "{"
    source.write_bytes(raw)
    assert project_status(copy)["status"] == "needs_audit"
    assert all(r["last_status"] == "not_run" for r in project_status(copy)["figures"])
    assert run_project(copy)["exit_code"] == 0


def test_changes_during_actual_audit_reject_overall_acceptance(copy, monkeypatch):
    original = model.audit

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        path = copy.parent.parent / "results.csv"
        path.write_bytes(path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(model, "audit", changed)
    result = run_project(copy)
    assert (
        result["audit_status"] == "passed"
        and result["status"] == "failed"
        and result["exit_code"] == 2
    )
    assert "changed during auditing" in " ".join(result["errors"])


def test_changed_then_restored_data_cannot_borrow_the_original_snapshot_identity(copy, monkeypatch):
    original = model.audit
    path = copy.parent.parent / "results.csv"
    raw = path.read_bytes()

    def replaced(*args, **kwargs):
        path.write_bytes(raw + b"\n")
        try:
            return original(*args, **kwargs)
        finally:
            path.write_bytes(raw)

    monkeypatch.setattr(model, "audit", replaced)
    result = run_project(copy)
    assert result["audit_status"] == "passed" and result["exit_code"] == 2
    assert "Audited data bytes differ" in str(result["policy_errors"])


@pytest.mark.parametrize("reserved", [False, True])
def test_shared_palette_uses_existing_identity_and_requires_review_after_reservation(
    copy, reserved
):
    from graphunslopify.lockfile import reserve, save

    lock = {"version": 1, "series": {}}
    if reserved:
        reserve(lock, ["base", "ours"])
    path = copy.parent.parent / "series.json"
    save(path, lock)
    before = path.read_bytes()
    set_project_shared(
        copy, {"palette_lock": "series.json"}, expected_revision=project_status(copy)["revision"]
    )
    result = run_project(copy)
    if reserved:
        assert result["exit_code"] == 0 and path.read_bytes() == before
    else:
        assert result["audit_status"] == "passed" and result["exit_code"] == 2
        assert "changed during auditing" in str(result["errors"])
        assert run_project(copy)["exit_code"] == 0
    assert set(json.loads(path.read_text())["series"]) == {"base", "ours"}


@pytest.mark.parametrize("declared", [False, True])
def test_script_status_does_not_execute_and_shared_policy_does_not_rewrite_scripts(
    tmp_path, declared
):
    paper = tmp_path / "paper"
    config = create(paper)
    spec = json.loads((paper / "training.figure.json").read_text())
    spec["data"]["path"] = str(paper / "results.csv")
    marker = paper / "executed.txt"
    source = paper / "authored.py"
    source.write_text(
        Figure(spec).translate(api="local")["code"]
        + f"\nPath({str(marker)!r}).write_text('executed')\n"
    )
    raw = source.read_bytes()
    entry = {
        "id": "script",
        "script": "authored.py",
        **({"data": "results.csv"} if declared else {}),
    }
    (paper / "graphunslopify.json").write_text(
        json.dumps({"schema_version": 1, "figures": [entry]})
    )
    state = project_status(config)
    assert not marker.exists()
    result = run_project(config)
    assert result["exit_code"] == 0 and marker.exists()
    marker.unlink()
    state = project_status(config)
    assert not marker.exists()
    assert state["figures"][0]["freshness"] == ("unchanged" if declared else "unknown")
    set_project_shared(
        config, {"output": {"size": "double_column"}}, expected_revision=state["revision"]
    )
    failed = run_project(config)
    assert failed["audit_status"] == "passed" and failed["exit_code"] == 2
    assert "Shared output.size" in " ".join(failed["policy_errors"]["script"])
    assert source.read_bytes() == raw


def test_owned_paths_refuse_receipt_traversal_and_symlink_history(copy, tmp_path):
    event = next((copy.parent / "history").iterdir())
    path = event / "receipt.json"
    value = json.loads(path.read_text())
    value["files"][0]["path"] = "../outside"
    path.write_text(json.dumps(value))
    assert project_history(copy)["events"][0]["phase"] == "damaged"
    outside = tmp_path / "outside"
    outside.mkdir()
    moved = copy.parent / "history"
    moved.rename(copy.parent / "preserved-history")
    try:
        moved.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ProjectError, match="symlinks"):
        project_history(copy)
    assert not list(outside.iterdir())


def test_removing_a_binding_requires_a_new_paper_audit_even_if_remaining_inputs_match(copy):
    paper = copy.parent.parent
    manifest = paper / "graphunslopify.json"
    value = json.loads(manifest.read_text())
    value["figures"].pop()
    manifest.write_text(json.dumps(value))
    state = project_status(copy)
    assert state["figures"][0]["freshness"] == "unchanged"
    assert state["status"] == "needs_audit" and not state["matches_last_run_revision"]
    assert run_project(copy)["exit_code"] == 0
    assert project_status(copy)["status"] == "inputs_match_last_run"


def test_definition_edit_retains_prior_bytes_and_advanced_intent_without_touching_data(copy):
    paper = copy.parent.parent
    data = (paper / "results.csv").read_bytes()
    source = paper / "training.figure.json"
    original = source.read_bytes()
    read = project_figure(copy, "training")
    assert read["editable"] and "seed" in read["columns"]
    spec = json.loads(read["text"])
    spec["title"] = "Edited <literal> title"
    result = set_project_figure(copy, "training", spec, expected_revision=read["revision"])
    assert result["status"] == "definition_saved"
    assert (Path(result["directory"]) / "source/0000.json").read_bytes() == original
    assert json.loads(source.read_text()) == spec
    assert (paper / "results.csv").read_bytes() == data
    state = project_status(copy)
    assert state["status"] == "needs_audit"
    assert [row["freshness"] for row in state["figures"]] == ["changed", "unchanged"]
    assert project_history(copy)["integrity"] == "verified"


def test_stale_and_invalid_definition_updates_do_not_write_or_create_history(copy):
    read = project_figure(copy, "training")
    source = copy.parent.parent / "training.figure.json"
    original = source.read_bytes()
    invalid = json.loads(read["text"])
    invalid["kind"] = "invented"
    with pytest.raises(ProjectError, match="Correct the figure definition"):
        set_project_figure(copy, "training", invalid, expected_revision=read["revision"])
    assert source.read_bytes() == original and len(project_history(copy)["events"]) == 1
    source.write_bytes(original + b"\n")
    with pytest.raises(ProjectError, match="changed since review"):
        set_project_figure(
            copy, "training", json.loads(original), expected_revision=read["revision"]
        )
    assert source.read_bytes() == original + b"\n" and len(project_history(copy)["events"]) == 1


def test_shared_source_references_use_resolved_identity_not_path_spelling(copy):
    paper = copy.parent.parent
    path = paper / "graphunslopify.json"
    manifest = json.loads(path.read_text())
    manifest["figures"][1]["spec"] = str(paper / "training.figure.json")
    path.write_text(json.dumps(manifest))
    read = project_figure(copy, "training")
    assert read["shared_by"] == ["training", "results-table"]


def test_clone_rebases_nested_source_and_keeps_ids_and_originals_on_add_remove(copy):
    paper = copy.parent.parent
    nested = paper / "definitions"
    nested.mkdir()
    spec = json.loads((paper / "training.figure.json").read_text())
    spec["data"]["path"] = "../results.csv"
    (nested / "curve.json").write_text(json.dumps(spec))
    manifest_path = paper / "graphunslopify.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["figures"][0]["spec"] = "definitions/curve.json"
    manifest_path.write_text(json.dumps(manifest))
    read = project_figure(copy, "training")
    assert read["clone"]["spec"]["data"]["path"] == "results.csv"
    entry = {**read["clone"], "id": "duplicate"}
    added = set_project_entry(
        copy, "duplicate", entry, mode="add", expected_revision=read["revision"]
    )
    assert added["change"] == "add" and len(project_status(copy)["figures"]) == 3
    assert run_project(copy)["exit_code"] == 0
    current = project_figure(copy, "duplicate")
    edited = json.loads(current["text"])
    edited["caption"] = "Inline source preserves advanced fields."
    set_project_figure(copy, "duplicate", edited, expected_revision=current["revision"])
    assert project_figure(copy, "duplicate")["entry"]["spec"] == edited
    set_project_entry(
        copy, "duplicate", None, mode="remove", expected_revision=project_status(copy)["revision"]
    )
    assert len(project_status(copy)["figures"]) == 2 and (nested / "curve.json").exists()
    assert project_status(copy)["status"] == "needs_audit"
    assert project_history(copy)["integrity"] == "verified"


@pytest.mark.parametrize("change", ["duplicate", "rename", "unknown", "empty"])
def test_invalid_manifest_binding_changes_preserve_originals(copy, change):
    before = (copy.parent.parent / "graphunslopify.json").read_bytes()
    state = project_status(copy)
    entry = project_figure(copy, "training")["entry"]
    if change == "duplicate":
        args = ("training", entry)
        mode = "add"
    elif change == "rename":
        args = ("training", {**entry, "id": "different"})
        mode = "update"
    elif change == "unknown":
        args = ("training", {**entry, "colour": "red"})
        mode = "update"
    else:
        set_project_entry(
            copy, "results-table", None, mode="remove", expected_revision=state["revision"]
        )
        before = (copy.parent.parent / "graphunslopify.json").read_bytes()
        state = project_status(copy)
        args = ("training", None)
        mode = "remove"
    count = len(project_history(copy)["events"])
    with pytest.raises(ProjectError):
        set_project_entry(copy, *args, mode=mode, expected_revision=state["revision"])
    assert (copy.parent.parent / "graphunslopify.json").read_bytes() == before
    assert len(project_history(copy)["events"]) == count


def test_invalid_json_source_can_be_repaired_and_retains_original_failed_text(copy):
    source = copy.parent.parent / "training.figure.json"
    original = json.loads(source.read_text())
    source.write_text("{")
    read = project_figure(copy, "training")
    assert read["text"] == "{" and read["editable"] and read["errors"]
    result = set_project_figure(copy, "training", original, expected_revision=read["revision"])
    assert (Path(result["directory"]) / "source/0000.json").read_text() == "{"
    assert run_project(copy)["exit_code"] == 0


@pytest.mark.parametrize("shape", ["columns", "axis", "group", "data", "inline-data"])
def test_schema_invalid_but_parseable_definitions_remain_readable_and_repairable(copy, shape):
    source = copy.parent.parent / "training.figure.json"
    good = json.loads(source.read_text())
    broken = json.loads(source.read_text())
    if shape == "columns":
        broken["data"]["columns"] = None
    elif shape == "axis":
        broken["x"] = 42
    elif shape == "group":
        broken["group"] = ["not-a-field"]
    else:
        broken["data"] = None
    if shape == "inline-data":
        path = copy.parent.parent / "graphunslopify.json"
        manifest = json.loads(path.read_text())
        manifest["figures"][0]["spec"] = broken
        path.write_text(json.dumps(manifest))
    else:
        source.write_text(json.dumps(broken))
    read = project_figure(copy, "training")
    assert read["editable"] and json.loads(read["text"]) == broken
    saved = set_project_figure(copy, "training", good, expected_revision=read["revision"])
    assert saved["exit_code"] == 0 and json.loads(project_figure(copy, "training")["text"]) == good


@pytest.mark.parametrize("target", ["external", "data", "history", "symlink"])
def test_definition_source_ownership_never_rewrites_external_data_or_history(
    copy, tmp_path, target
):
    paper = copy.parent.parent
    manifest_path = paper / "graphunslopify.json"
    value = json.loads(manifest_path.read_text())
    raw = (paper / "training.figure.json").read_bytes()
    if target == "external":
        source = tmp_path / "external.json"
        source.write_bytes(raw)
    elif target == "data":
        source = paper / "results.csv"
    elif target == "history":
        source = next((copy.parent / "history").iterdir()) / "source/0000.json"
    else:
        source = paper / "linked.json"
        source.symlink_to(paper / "training.figure.json")
    original = source.read_bytes()
    value["figures"][0]["spec"] = str(source)
    manifest_path.write_text(json.dumps(value))
    read = project_figure(copy, "training")
    assert not read["editable"] and read["reason"]
    with pytest.raises(ProjectError):
        set_project_figure(copy, "training", json.loads(raw), expected_revision=read["revision"])
    assert source.read_bytes() == original
