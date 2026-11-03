"""Actual evidence availability stays separate from scientific acceptance."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import shutil
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

from graphunslopify import Figure
from graphunslopify import project as model
from graphunslopify import project_scorecard as cards
from graphunslopify.cli import main
from graphunslopify.project_export import create_review_packet
from graphunslopify.project_review import project_review

ROOT = Path(__file__).resolve().parents[2]


def inventory(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def components(value, identity="line"):
    row = next(f for f in value["figures"] if f["id"] == identity)
    return row, {c["id"]: c for c in row["components"]}


def initialize(root):
    root.mkdir()
    rows = ["step,score,seed,model"]
    for step in range(1, 4):
        for name, offset in (("a", 0), ("b", 2)):
            for seed, value in (("one", 1), ("two", 3), ("three", 5)):
                rows.append(f"{step},{step + value + offset},{seed},{name}")
    (root / "runs.csv").write_text("\n".join(rows) + "\n")
    line = {
        "kind": "line",
        "group": "model",
        "data": {"path": "runs.csv"},
        "x": {"field": "step", "label": "Step"},
        "y": {"field": "score", "label": "Score"},
        "aggregation": "mean",
        "uncertainty": {"kind": "std", "over": "seed"},
    }
    (root / "line.json").write_text(json.dumps(line))
    bar = {**copy.deepcopy(line), "kind": "bar", "orientation": "horizontal"}
    authored = {**copy.deepcopy(line), "output": {"stem": "authored", "formats": ["png"]}}
    (root / "authored.py").write_text(Figure(authored).translate(api="local")["code"])
    (root / "graphunslopify.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "figures": [
                    {"id": "line", "spec": "line.json"},
                    {"id": "bars", "spec": bar},
                    {"id": "authored", "script": "authored.py", "data": "runs.csv"},
                ],
            }
        )
    )
    model.initialize_project(root)
    return root


@pytest.fixture(scope="module")
def checked(tmp_path_factory):
    root = initialize(tmp_path_factory.mktemp("scorecard-original") / "paper with spaces")
    assert model.run_project(root)["exit_code"] == 0
    reused = model.run_project(root, selective=True)
    assert reused["exit_code"] == 0
    assert reused["audit"]["execution_counts"] == {"executed": 1, "reused": 2, "not_run": 0}
    return root


@pytest.fixture
def paper(checked, tmp_path):
    root = tmp_path / "moved paper"
    shutil.copytree(checked, root)
    return root


def test_actual_files_program_hashes_and_reuse_are_read_only(paper, monkeypatch):
    before = inventory(paper)
    monkeypatch.setattr(model, "audit", lambda *a, **k: pytest.fail("Scorecard executed science"))
    result = cards.project_scorecard(paper)
    row, parts = components(result)
    assert set(parts) == {
        "data",
        "definitions",
        "programs",
        "environment",
        "checks",
        "exports",
        "history",
    }
    assert (
        parts["data"]["state"]
        == parts["programs"]["state"]
        == parts["exports"]["state"]
        == "available"
    )
    assert parts["data"]["evidence"]["matches_recorded_bytes"] is True
    assert parts["programs"]["evidence"]["matches_executed_program"] is True
    assert parts["history"]["evidence"]["execution"]["mode"] == "reused"
    assert parts["environment"]["state"] == "partial"
    assert parts["environment"]["evidence"]["complete_environment_lock_claimed"] is False
    assert row["scientific_status"] == "passed" and result["new_execution"] is False
    _, script = components(result, "authored")
    assert script["data"]["state"] == "partial"
    assert script["programs"]["state"] == "available"
    assert script["programs"]["evidence"]["relative_path"].endswith("/source.py")
    assert components(result, "bars")[1]["definitions"]["evidence"]["inline_manifest_definition"]
    assert before == inventory(paper)
    assert "score" not in result


def test_unrun_project_reports_current_data_and_missing_execution(tmp_path):
    root = initialize(tmp_path / "unrun")
    before = inventory(root)
    result = cards.project_scorecard(root)
    row, parts = components(result)
    assert parts["data"]["state"] == parts["definitions"]["state"] == "available"
    assert parts["programs"]["state"] == parts["checks"]["state"] == "missing"
    assert parts["environment"]["state"] == parts["history"]["state"] == "missing"
    assert row["scientific_status"] == "not_available"
    assert before == inventory(root)


def test_restored_data_without_an_old_fingerprint_is_unknown_not_different(tmp_path):
    root = initialize(tmp_path / "missing during audit")
    path = root / "runs.csv"
    content = path.read_bytes()
    path.unlink()
    assert model.run_project(root)["exit_code"] == 2
    path.write_bytes(content)
    before = inventory(root)
    value = cards.project_scorecard(root)
    _, parts = components(value)
    assert parts["data"]["state"] == "partial"
    assert parts["data"]["evidence"]["matches_recorded_bytes"] is None
    assert "no complete data fingerprint" in parts["data"]["summary"]
    assert before == inventory(root)


@pytest.mark.parametrize("operation,state", [("missing", "missing"), ("changed", "partial")])
def test_actual_missing_or_changed_data_never_becomes_available_from_a_hash(
    paper, operation, state
):
    path = paper / "runs.csv"
    if operation == "missing":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b"\n")
    before = inventory(paper)
    row, parts = components(cards.project_scorecard(paper))
    assert parts["data"]["state"] == state
    assert parts["data"]["evidence"]["matches_recorded_bytes"] is (
        None if operation == "missing" else False
    )
    assert row["scientific_status"] == "passed"  # Original result, not new acceptance.
    assert before == inventory(paper)


def test_identical_data_at_a_new_location_preserves_byte_vs_binding_identity(paper):
    shutil.copyfile(paper / "runs.csv", paper / "relocated.csv")
    path = paper / "line.json"
    spec = json.loads(path.read_text())
    spec["data"]["path"] = "relocated.csv"
    path.write_text(json.dumps(spec))
    row, parts = components(cards.project_scorecard(paper))
    data = parts["data"]
    assert data["state"] == "partial"
    assert data["evidence"]["matches_recorded_bytes"] is True
    assert data["evidence"]["matches_recorded_locations"] is False
    assert "different declared locations" in data["summary"]
    assert row["scientific_status"] == "passed"


@pytest.mark.parametrize("operation,state", [("missing", "missing"), ("changed", "partial")])
def test_actual_program_availability_is_not_top_level_receipt_membership(paper, operation, state):
    original = cards.project_scorecard(paper)
    _, parts = components(original)
    event = original["selection"]["event"]
    root = paper / "graphunslopify-project/history" / event
    name = "audit/" + parts["programs"]["evidence"]["relative_path"]
    receipt = json.loads((root / "receipt.json").read_text())
    assert name not in {f["path"] for f in receipt["files"]}
    path = root / name
    if operation == "missing":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b"\n# changed owned program\n")
    changed = cards.project_scorecard(paper)
    row, parts = components(changed)
    assert parts["programs"]["state"] == state
    assert row["scientific_status"] == "passed"
    assert changed["evidence_revision"] != original["evidence_revision"]


def test_program_change_during_query_is_refused(paper, monkeypatch):
    original = cards._program_bytes
    changed = False

    def changing(root, relative):
        nonlocal changed
        result = original(root, relative)
        if not changed and result.get("readable"):
            path = model._inside(root, relative)
            path.write_bytes(path.read_bytes() + b"\n# mid-query mutation\n")
            changed = True
        return result

    monkeypatch.setattr(cards, "_program_bytes", changing)
    with pytest.raises(model.ProjectError, match="availability changed"):
        cards.project_scorecard(paper)


def test_failed_science_remains_failed_with_available_data_and_program(paper):
    path = paper / "line.json"
    spec = json.loads(path.read_text())
    spec["claims"] = [{"kind": "beats_everywhere", "subject": "a", "reference": "b"}]
    path.write_text(json.dumps(spec))
    assert model.run_project(paper)["status"] == "failed"
    result = cards.project_scorecard(paper)
    row, parts = components(result)
    assert row["scientific_status"] == row["paper_status"] == "failed"
    assert all(parts[k]["state"] == "available" for k in ("data", "programs", "checks", "exports"))
    assert parts["checks"]["evidence"]["scientific_status"] == "failed"
    assert any(c["verdict"] == "fails" for c in parts["checks"]["evidence"]["claims"])


def test_damaged_latest_history_does_not_fall_back_to_an_old_pass(paper):
    event = model.project_history(paper)["events"][0]
    path = paper / "graphunslopify-project/history" / event["id"] / "result.json"
    path.write_bytes(path.read_bytes() + b" ")
    result = cards.project_scorecard(paper)
    assert result["selection"]["state"] == "unavailable"
    assert all(
        components(result, row["id"])[1]["checks"]["state"] == "missing"
        for row in result["figures"]
    )


def test_scorecard_cli_and_packet_preserve_local_vs_included_scope(paper, capsys):
    assert main(["project-scorecard", str(paper)]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["schema_version"] == 1 and len(value["figures"]) == 3
    review = project_review(paper)
    raw = create_review_packet(paper, expected_revision=review["evidence_revision"])
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        scorecard = json.loads(z.read("reports/scorecard.json"))
        assert scorecard["evidence_revision"] == review["evidence_revision"]
        assert scorecard["availability_scope"] == "local_project_at_query"
        assert scorecard["packet_inclusion"]["raw_datasets"] is False
        assert scorecard["packet_inclusion"]["source_programs"] is False
        assert not any(name.endswith((".csv", ".py")) for name in z.namelist())
        assert b"Reproducibility scorecard" in z.read("index.html")


def test_actual_pdf_only_project_does_not_invent_data_programs_or_science(tmp_path):
    from graphunslopify import project_inspections as inspections

    paper = tmp_path / "pdf paper"
    paper.mkdir()
    shutil.copyfile(ROOT / "examples/baseline/01-training-curve.pdf", paper / "external.pdf")
    model.initialize_project(paper, review_only=True)
    revision = inspections.project_inspections(paper)["revision"]
    inspections.inspect_project_pdf(
        paper,
        paper / "external.pdf",
        identity="external",
        expected_revision=revision,
        pages=[1],
        dpi=72,
    )
    before = inventory(paper)
    result = cards.project_scorecard(paper)
    row, parts = components(result, "external")
    assert row["source_type"] == "pdf" and row["scientific_status"] == "untested"
    assert all(parts[k]["state"] == "missing" for k in ("data", "definitions", "programs"))
    assert parts["checks"]["state"] == parts["environment"]["state"] == "partial"
    assert parts["exports"]["state"] == "available"
    assert before == inventory(paper)


def test_real_http_scorecard_keeps_authorization_and_expected_revision(paper):
    from graphunslopify.project_preview import ProjectServer

    server = ProjectServer(paper)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_address[1]}/api/scorecard"

    def get(url, token):
        request = urllib.request.Request(url, headers={"X-Preview-Token": token})
        try:
            response = urllib.request.urlopen(request, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.code, json.load(response)

    try:
        assert get(root, "wrong-token")[0] == 403
        code, value = get(root, server.state.token)
        assert code == 200 and value["new_execution"] is False
        code, refused = get(root + "?expected_revision=" + "0" * 64, server.state.token)
        assert code == 400 and "changed" in refused["error"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(10)
