"""Real isolated starts, warm native reuse, independent acceptance and custody."""

from __future__ import annotations

import json
import os
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "benchmarks/workspace"
RUNNER = runpy.run_path(str(HERE / "session_runner.py"))


@pytest.fixture(scope="module")
def native_sessions(tmp_path_factory):
    root = tmp_path_factory.mktemp("real-workspace-sessions")
    checker = runpy.run_path(str(ROOT / "scripts/check-workspace-sessions.py"))
    proof = checker["check"](root / "conformance")
    assert proof["passed"]
    return {r["arm"]: r for r in proof["sessions"]}


def test_real_cold_start_warm_math_and_outer_acceptance(native_sessions):
    result = native_sessions["matplotlib"]
    rows = result["rows"]
    assert len(rows) == 8 and rows[0]["phase"] == "cold"
    assert all(row["phase"] == "warm" for row in rows[1:])
    assert len({row["pid"] for row in rows}) == 1 and rows[0]["pid"] != os.getpid()
    assert rows[0]["end_to_end_origin_ns"] == result["startup"]["launched_ns"]
    for row in rows:
        assert row["outcome"] == "completed" and row["timing_envelope_valid"]
        assert row["task_verified_ns"] == row["parent_received_ns"]
        assert row["worker_task_verified_ns"] == row["checked_ns"]
        assert row["worker_started_ns"] <= row["first_png_available_ns"] <= row["tool_end_ns"]
    reports = [json.loads(Path(row["report_file"]).read_text()) for row in rows]
    assert not reports[0]["calculation_cache"]["hit"]
    assert reports[1]["calculation_cache"]["hit"]
    assert not reports[6]["calculation_cache"]["hit"]
    assert reports[7]["calculation_cache"]["hit"]
    assert result["closure"]["closed_ns"] >= rows[-1]["parent_received_ns"]


def test_real_editor_worker_reuse_does_not_forge_task_success(native_sessions):
    result = native_sessions["graphunslopify"]
    rows = result["rows"]
    assert len({r["native_execution"]["pid"] for r in rows}) == 1
    assert len({r["translation_execution"]["pid"] for r in rows}) == 1
    assert [r["native_execution"]["request_number"] for r in rows] == list(range(1, 9))
    assert rows[0]["native_execution"]["process_started"]
    assert all(not r["native_execution"]["process_started"] for r in rows[1:])
    failed = [r for r in rows if not r["evaluation"]["task_correct_verified"]]
    assert failed
    for row in failed:
        assert row["tool_status"] == "passed" and row["tool_accepted_ns"] is not None
        assert row["task_verified_ns"] is None and row["worker_task_verified_ns"] is None
    assert result["closure_error"] is None


def test_failed_actual_interpreter_start_retains_every_planned_cell(tmp_path):
    result = RUNNER["run_sequence"](
        "matplotlib", "penguins-mass", tmp_path / "owned", python=str(tmp_path / "missing-python")
    )
    assert result["session_error"]["type"] == "FileNotFoundError"
    assert len(result["rows"]) == 8
    assert all(r["outcome"] == "not_run" and r["unavailable_reason"] for r in result["rows"])
    assert not any("first_png_available_ns" in r for r in result["rows"])
    assert (tmp_path / "owned/sequence.json").is_file()


def test_existing_evidence_is_never_overwritten(tmp_path):
    owned = tmp_path / "owned"
    owned.mkdir()
    marker = owned / "sequence.json"
    marker.write_text("retain previous failed attempt\n")
    with pytest.raises(FileExistsError):
        RUNNER["run_sequence"]("matplotlib", "penguins-mass", owned)
    assert marker.read_text() == "retain previous failed attempt\n"
