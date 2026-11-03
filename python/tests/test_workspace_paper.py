"""Real paper audits, strong reuse, native observer controls and current custody."""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "benchmarks/workspace"


@pytest.fixture(scope="module")
def paper_evidence(tmp_path_factory):
    path = tmp_path_factory.mktemp("actual-public-paper") / "evidence"
    module = runpy.run_path(str(ROOT / "scripts/check-workspace-paper.py"))
    proof = module["check"](path)
    assert proof["passed"]
    return path, proof


def test_real_sdk_paper_policy_and_history(paper_evidence):
    from graphunslopify.project import project_history

    path, proof = paper_evidence
    session = next(s for s in proof["sessions"] if s["arm"] == "graphunslopify")
    counts = [
        (
            r["native"]["audit"]["execution_counts"]["executed"],
            r["native"]["audit"]["execution_counts"]["reused"],
        )
        for r in session["rows"]
    ]
    assert counts == [(4, 0), (0, 4), (1, 3), (2, 2), (2, 2), (1, 3), (4, 0), (5, 0), (4, 0)]
    assert all(
        figure["edit_map"]["available"]
        for row in session["rows"]
        for figure in row["native"]["audit"]["figures"]
    )
    assert session["rows"][5]["native"]["exit_code"] == 2
    assert session["rows"][3]["review"]["can_apply"]
    assert project_history(path / "graphunslopify")["integrity"] == "verified"


def test_baseline_rechecks_acceptance_without_forcing_draws(paper_evidence):
    _, proof = paper_evidence
    rows = next(s["rows"] for s in proof["sessions"] if s["arm"] == "matplotlib")
    assert rows[1]["native"]["audit"]["execution_counts"]["acceptance_reused"] == 4
    assert rows[4]["native"]["audit"]["execution_counts"]["executed"] == 0
    for index in (6, 7, 8):
        assert rows[index]["native"]["audit"]["execution_counts"]["acceptance_reused"] == 0
    old = rows[3]["results"]["penguins-mass"]["result"]
    current = rows[4]["results"]["penguins-mass"]["result"]
    assert old["data_sha256"] != current["data_sha256"]
    assert current["execution"]["original_save_data_sha256"] != current["data_sha256"]
    assert old["outputs"] == current["outputs"]
    assert rows[5]["results"]["penguins-mass"]["result"]["scientific_findings"]
    assert rows[5]["task_verified_ns"] is None


def test_direct_observer_preserves_actual_native_drawings(paper_evidence):
    _, proof = paper_evidence
    assert len(proof["observer_controls"]) == 2
    for control in proof["observer_controls"]:
        assert control["same_program_and_data"]
        assert set(control["identities"]["plain"]) == {"png", "svg", "pdf"}
        assert control["identities"]["plain"] == control["identities"]["observed"]
        assert control["identities"]["plain"] == control["identities"]["geometry"]
        assert control["identities"]["plain"] == control["identities"]["geometry_observed"]
        assert all(control["identities"]["plain"].values())


def test_reencoded_current_input_never_needs_an_unnecessary_save(tmp_path, monkeypatch):
    from matplotlib.figure import Figure

    module = runpy.run_path(str(HERE / "paper_matplotlib.py"))
    session = module["Session"](tmp_path / "paper")
    first = session.step("first")

    def forbidden(*args, **kwargs):
        pytest.fail("Byte-only change unexpectedly called Figure.savefig")

    monkeypatch.setattr(Figure, "savefig", forbidden)
    current = session.step("reencoded-data")
    assert current["native"]["audit"]["execution_counts"]["executed"] == 0
    old = first["results"]["penguins-mass"]["result"]
    new = current["results"]["penguins-mass"]["result"]
    assert old["outputs"] == new["outputs"] and old["data_sha256"] != new["data_sha256"]


def test_changed_latest_paper_image_or_report_cannot_reuse_acceptance(tmp_path):
    module = runpy.run_path(str(HERE / "paper_matplotlib.py"))
    session = module["Session"](tmp_path / "paper")
    first = session.step("first")
    folder = Path(first["results"]["penguins-mass"]["folder"])
    for name in ("figure.png", "report.json"):
        path = folder / name
        original = path.read_bytes()
        path.write_bytes(original + b"changed-current-history")
        with pytest.raises(ValueError, match="Saved paper history changed"):
            session.step("unchanged")
        path.write_bytes(original)
    assert (
        hashlib.sha256((folder / "figure.png").read_bytes()).hexdigest()
        == json.loads((folder / "report.json").read_text())["outputs"]["figure.png"]
    )
