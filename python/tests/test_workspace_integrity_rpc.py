"""Real post-render custody queries must not borrow stale scientific acceptance."""

from __future__ import annotations

import contextlib
import json
import queue
import runpy
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "benchmarks/workspace"


@pytest.mark.parametrize("arm", ["matplotlib", "graphunslopify"])
def test_actual_owned_file_faults_use_live_producer_validation(tmp_path, arm):
    runner = runpy.run_path(str(HERE / "session_runner.py"))
    spec = json.loads((HERE / "figures/penguins-mass.json").read_text())
    original = (HERE / "figures" / spec["data"]["path"]).read_bytes()
    data = tmp_path / "owned-input.csv"
    data.write_bytes(original)
    spec["data"]["path"] = str(data)
    live = runner["LiveSession"](arm, tmp_path / "live")
    request = {"name": "first", "case": "penguins-mass/first"}
    try:
        rendered = live.request(
            {**request, "operation": "render", "spec": spec, "base": str(tmp_path)}
        )
        assert rendered["outcome"] == "completed", rendered
        assert rendered["current_evidence"]["current"] is True
        folder = Path(rendered["folder"])
        result = json.loads(Path(rendered["report_file"]).read_text())
        program = (
            folder / "figure.py"
            if arm == "graphunslopify"
            else tmp_path / "live/producer/code/producer.py"
        )
        report = folder / (
            result["native_report_file"] if arm == "graphunslopify" else "report.json"
        )
        faults = [
            (
                folder / "figure.png",
                "file_changed:figure.png"
                if arm == "graphunslopify"
                else "output_changed:figure.png",
            ),
            (
                report,
                "file_changed:" + report.name if arm == "graphunslopify" else "report_changed",
            ),
            (data, "input_changed"),
            (
                program,
                "file_changed:figure.py"
                if arm == "graphunslopify"
                else "producer_changed:code/producer.py",
            ),
        ]
        for path, reason in faults:
            before = path.read_bytes()
            changed = (
                before.replace(b"\n", b"\r\n")
                if path == data
                else before + b"\n# actual owned custody control\n"
            )
            assert changed != before
            try:
                path.write_bytes(changed)
                guarded = live.request({**request, "operation": "validate"})
                assert guarded["outcome"] == "completed", guarded
                assert guarded["current_evidence"]["current"] is False
                assert guarded["current_evidence"]["strict_accepted"] is False
                assert reason in guarded["current_evidence"]["reasons"]
                assert (
                    guarded["worker_started_ns"]
                    <= guarded["checked_ns"]
                    <= guarded["parent_received_ns"]
                )
                assert guarded["task_verified_ns"] is None
                assert guarded["tool_accepted_ns"] is None
                assert "first_png_available_ns" not in guarded
            finally:
                path.write_bytes(before)
            restored = live.request({**request, "operation": "validate"})
            assert restored["current_evidence"]["current"] is True
            assert restored["task_verified_ns"] is None
        unrelated = live.request({**request, "operation": "validate", "case": "iris-scatter/first"})
        assert unrelated["outcome"] == "execution_error"
        assert unrelated["error_type"] == "ValueError"
        assert "current_evidence" not in unrelated
        assert data.read_bytes() == original
    finally:
        live.close()


def test_actual_late_render_reply_cannot_answer_a_post_timeout_guard(tmp_path):
    runner = runpy.run_path(str(HERE / "session_runner.py"))
    spec = json.loads((HERE / "figures/penguins-mass.json").read_text())
    data = tmp_path / "owned-input.csv"
    data.write_bytes((HERE / "figures" / spec["data"]["path"]).read_bytes())
    spec["data"]["path"] = str(data)
    live = runner["LiveSession"]("matplotlib", tmp_path / "live")
    request = {"name": "first", "case": "penguins-mass/first"}
    try:
        live.timeout = 0.001
        with pytest.raises(queue.Empty):
            live.request({**request, "operation": "render", "spec": spec, "base": str(tmp_path)})
        deadline = time.monotonic() + 30
        while not (tmp_path / "live/request-000.json").is_file():
            assert time.monotonic() < deadline, "Actual original render never completed"
            time.sleep(0.02)
        data.write_bytes(data.read_bytes() + b"\n")
        live.timeout = 30
        with pytest.raises(RuntimeError, match="different operation/request"):
            live.request({**request, "operation": "validate"})
    finally:
        # Its genuine outstanding guard reply is retained, never substituted.
        with contextlib.suppress(RuntimeError):
            live.close()
    assert live.process.poll() is not None
