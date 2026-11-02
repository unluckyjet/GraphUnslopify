"""Complete frozen study plans and actual preflight refusal retain every cell."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STUDY = runpy.run_path(str(ROOT / "benchmarks/workspace/study_runner.py"))
QUALIFY = runpy.run_path(str(ROOT / "benchmarks/workspace/qualification.py"))


def test_complete_frozen_denominators_and_actual_session_order():
    for track, expected in {
        "single": 192,
        "paper": 54,
        "reliability": 48,
        "local": 64,
        "gui": 14,
    }.items():
        plan = STUDY["plan"](track)
        assert sum(len(r["cells"]) for r in plan) == expected
        assert len({r["id"] for r in plan}) == len(plan)
    single = STUDY["plan"]("single")
    assert len(single) == 24
    assert [r["case"]["arm"] for r in single[:4]] == [
        "matplotlib",
        "graphunslopify",
        "graphunslopify",
        "matplotlib",
    ]
    assert all(len(r["cells"]) == 8 for r in single)
    assert [r["case"]["arm"] for r in STUDY["plan"]("paper")] == [
        "matplotlib",
        "graphunslopify",
        "graphunslopify",
        "matplotlib",
        "matplotlib",
        "graphunslopify",
    ]
    native = [
        STUDY["plan"]("native_ci", native_profile=p)
        for p in ("ubuntu3.10", "ubuntu3.12", "windows3.12", "macos3.12")
    ]
    assert sum(len(p) for p in native) == 64
    assert len({r["id"] for p in native for r in p}) == 64


def test_actual_wrong_checkout_keeps_all_native_cells_unstarted(tmp_path):
    proof = STUDY["run"](
        "native_ci", tmp_path / "refused", native_profile="macos3.12", expected_revision="0" * 40
    )
    assert proof["complete"] is False
    assert proof["planned_cells"] == proof["retained_cells"] == 16
    assert len(proof["records"]) == 16 and all(
        not r["attempted"] and r["outcome"] == "not_run" for r in proof["records"]
    )
    assert "Actual checkout differs" in proof["errors"][0]["message"]
    assert json.loads((tmp_path / "refused/study.json").read_text()) == proof
    assert not any((tmp_path / "refused").glob("case-*"))


def test_existing_study_evidence_is_never_overwritten(tmp_path):
    path = tmp_path / "retained"
    path.mkdir()
    (path / "study.json").write_text("original failed run\n")
    with pytest.raises(FileExistsError):
        STUDY["run"]("single", path)
    assert (path / "study.json").read_text() == "original failed run\n"


def test_local_profiles_cannot_be_reduced_or_relabelled_installed():
    with pytest.raises(ValueError, match="every registered"):
        STUDY["configurations"](
            "local", {"checkout-current3.12": {"python": "python", "installed": False}}
        )
    with pytest.raises(ValueError, match="disagree"):
        STUDY["configurations"](
            "gui",
            {
                "source-current": {"python": "python", "installed": False},
                "fresh-wheel": {"python": "python", "installed": False},
            },
        )


def test_ci_bytes_alone_cannot_qualify_a_partial_implementation():
    with pytest.raises(ValueError, match="prospective preparation qualification"):
        QUALIFY["validate_summary"]({"source_sha256": {}, "package_sha256": {}})
    with pytest.raises(ValueError, match="six full"):
        QUALIFY["qualify"]({}, source_sha256={}, package_sha256={})


def test_missing_formal_seal_retains_all192_cells_without_claiming_execution(tmp_path):
    proof = STUDY["run"](
        "single", tmp_path / "refused", mode="formal", seal_path=tmp_path / "missing.json"
    )
    assert not proof["formal_comparison_performed"] and not proof["complete"]
    assert proof["planned_cells"] == proof["retained_cells"] == 192
    assert all(not r["attempted"] and len(r["unavailable_cells"]) == 8 for r in proof["records"])
    assert proof["errors"][0]["type"] == "FileNotFoundError"
    assert not list((tmp_path / "refused").glob("case-*"))
