"""Pilot accounting must not turn abstentions or missing images into successes."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "scripts/research-benchmark.py"
spec = importlib.util.spec_from_file_location("research_benchmark", SOURCE)
assert spec and spec.loader
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def test_pilot_keeps_abstentions_and_execution_errors_out_of_confirmed_detections():
    rows = [
        {
            "arm": "test",
            "truth": truth,
            "exit_codes": [code, code],
            "statuses": [status, status],
            "pixel_hashes": hashes,
        }
        for truth, code, status, hashes in (
            ("valid", 0, "passed", ["abc", "abc"]),
            ("invalid", 2, "failed", ["def", "def"]),
            ("unavailable", 2, "incomplete", ["ghi", "ghi"]),
            ("execution_error", 1, "execution_error", [None, None]),
            ("outside_scope", 0, "passed", ["jkl", "changed"]),
        )
    ]
    summary = pilot.summarize(rows, "test")
    assert summary["invalid"] == {"cases": 1, "blocked": 1, "confirmed_failed": 1, "incomplete": 0}
    assert summary["unavailable"] == {
        "cases": 1,
        "blocked": 1,
        "confirmed_failed": 0,
        "incomplete": 1,
    }
    assert summary["execution_error"]["confirmed_failed"] == 0
    assert summary["outside_scope"]["blocked"] == 0
    assert summary["pixel_reproductions"] == {"comparable": 4, "identical": 3}
    assert pilot.summarize(rows, "absent")["valid"]["cases"] == 0


def test_pilot_exposes_a_second_attempt_failure():
    rows = [
        {
            "arm": "test",
            "truth": "valid",
            "exit_codes": [0, 1],
            "statuses": ["passed", "failed"],
            "pixel_hashes": ["abc", None],
        }
    ]
    summary = pilot.summarize(rows, "test")
    assert summary["valid"]["blocked"] == 1
    assert summary["repeat_consistency"] == {"cases": 1, "disagreements": 1}
    assert summary["pixel_reproductions"] == {"comparable": 0, "identical": 0}
