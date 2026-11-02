"""Actual isolated paper processes, observable clocks, old saves and interruptions."""

import json
import os
import runpy
import signal
import subprocess
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "benchmarks/workspace"


@pytest.mark.parametrize("arm", ["matplotlib", "graphunslopify"])
def test_actual_paper_worker_full_sequence(tmp_path, arm):
    paper = runpy.run_path(str(HERE / "paper_sessions.py"))
    assert [s["arm"] for s in paper["schedule"]()] == [
        "matplotlib",
        "graphunslopify",
        "graphunslopify",
        "matplotlib",
        "matplotlib",
        "graphunslopify",
    ]
    context = tmp_path / "execution.json"
    context.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "preseal",
                "track": "paper",
                "arm": arm,
                "case": {"session": 0},
            }
        )
    )
    result = paper["run_sequence"](arm, tmp_path / arm, execution_context=context)
    assert not result["session_error"] and not result["closure_error"]
    assert result["startup"]["child_events_enabled"] is False
    assert not (tmp_path / arm / "live/native-started.jsonl").exists()
    rows = result["rows"]
    execution = result["execution_context"]
    assert result["closure"]["execution_context"] == execution
    for row in rows:
        assert row["execution_context"] == row["paper"]["execution_context"] == execution
        for figure in row["paper"]["results"].values():
            assert figure["result"]["execution_context"] == execution
        assert all(v["execution_context"] == execution for v in row["evaluations"].values())
    assert len(rows) == 9 and all(r["outcome"] == "completed" for r in rows)
    pid = result["startup"]["pid"]
    assert pid != os.getpid() and {r["pid"] for r in rows} == {pid}
    assert result["closure"]["pid"] == pid
    assert rows[0]["end_to_end_origin_ns"] == result["startup"]["launched_ns"]
    assert all(r["end_to_end_origin_ns"] == r["parent_dispatched_ns"] for r in rows[1:])
    assert all(r["timing_envelope_valid"] for r in rows)
    assert rows[0]["first_png_available_ns"] is not None
    assert rows[1]["first_png_available_ns"] is None and rows[1]["first_png_unavailable_reason"]
    old = rows[1]["paper"]["results"]["penguins-mass"]["result"]["save_observations"]
    assert min(e["available_monotonic_ns"] for e in old) < rows[1]["worker_started_ns"]
    assert rows[5]["tool_exit_code"] == 2 and rows[5]["task_verified_ns"] is None
    for row in rows:
        expected = arm == "matplotlib" and row["step"] != "false-claim"
        assert row["task_verified_ns"] == (row["parent_received_ns"] if expected else None)
        assert row["worker_task_verified_ns"] == (row["checked_ns"] if expected else None)
        assert all(
            e.startswith("actual_width:") for v in row["evaluations"].values() for e in v["errors"]
        )
    assert rows[-1]["paper"]["native"]["audit"]["execution_counts"]["executed"] == (
        4 if arm == "graphunslopify" else 0
    )


def test_real_paper_startup_failure_and_existing_evidence(tmp_path):
    paper = runpy.run_path(str(HERE / "paper_sessions.py"))
    folder = tmp_path / "no-interpreter"
    result = paper["run_sequence"]("matplotlib", folder, python=str(tmp_path / "missing-python"))
    assert result["session_error"]["type"] == "FileNotFoundError"
    assert len(result["rows"]) == 9 and all(
        r["outcome"] == "not_run" and r["unavailable_reason"] for r in result["rows"]
    )
    assert json.loads((folder / "sequence.json").read_text()) == result
    with pytest.raises(FileExistsError):
        paper["run_sequence"]("matplotlib", folder)


def test_real_dispatched_request_timeout_retains_all_cells(tmp_path, monkeypatch):
    paper = runpy.run_path(str(HERE / "paper_sessions.py"))
    original = paper["LiveSession"]
    created = []

    def deadline_after_actual_readiness(*args, **kwargs):
        live = original(*args, **kwargs)
        created.append(live)
        live.timeout = 0.001
        return live

    monkeypatch.setitem(
        paper["run_sequence"].__globals__, "LiveSession", deadline_after_actual_readiness
    )
    result = paper["run_sequence"]("matplotlib", tmp_path / "deadline")
    assert result["session_error"]["type"] == "Empty"
    assert len(created) == 1 and created[0].process.poll() is not None
    assert len(result["rows"]) == 9
    assert result["rows"][0]["outcome"] == "response_unavailable"
    assert result["rows"][0]["dispatch_state"] == "flushed"
    assert result["rows"][0]["parent_dispatched_ns"] >= result["startup"]["launched_ns"]
    assert all(r["outcome"] == "not_run" for r in result["rows"][1:])


@pytest.mark.skipif(os.name == "nt", reason="POSIX SIGSTOP fault control")
def test_interrupted_actual_native_renderer_is_reaped(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHUNSLOPIFY_PAPER_CHILD_EVENTS", "1")
    runner = runpy.run_path(str(HERE / "session_runner.py"))
    folder = (tmp_path / "active-native").resolve()
    live = runner["LiveSession"]("graphunslopify", folder, track="paper")
    errors, child, replies = [], None, []

    def invoke():
        try:
            replies.append(
                live.request({"operation": "step", "step": "first", "case": "paper/first"})
            )
        except Exception as error:  # noqa: BLE001 - keep the actual interrupted response
            errors.append(type(error).__name__)

    thread = threading.Thread(target=invoke)
    try:
        thread.start()
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline and child is None:
            events = folder / "native-started.jsonl"
            for line in events.read_text().splitlines() if events.is_file() else []:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue  # A real append may still be in progress.
                if event["parent_pid"] != live.process.pid or event["phase"] != "communicate":
                    continue
                candidate = event["pid"]
                parent = subprocess.run(
                    ["ps", "-p", str(candidate), "-o", "ppid="],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if parent.returncode == 0 and parent.stdout.strip() == str(live.process.pid):
                    try:
                        os.kill(candidate, signal.SIGSTOP)
                    except ProcessLookupError:
                        continue
                    child = candidate
                    break
            if not thread.is_alive() and child is None:
                break
            if child is None:
                time.sleep(0.02)
        assert child is not None, {
            "error": "No actual owned native renderer observed",
            "request_errors": errors,
            "replies": replies,
            "worker_returncode": live.process.poll(),
            "events": str(folder / "native-started.jsonl"),
        }
        live.terminate()
        thread.join(timeout=5)
        assert not thread.is_alive() and errors
        assert live.process.poll() is not None
        assert (
            subprocess.run(
                ["ps", "-p", str(child), "-o", "pid="], capture_output=True, check=False
            ).returncode
            != 0
        )
        closed = json.loads((folder / "closed.json").read_text())
        assert any(
            c["pid"] == child and not c["forced_cleanup"] and c["returncode"] is not None
            for c in closed["owned_children"]
        )
    finally:
        if live.process.poll() is None:
            live.terminate()
        if child is not None:
            current = subprocess.run(
                ["ps", "-ww", "-p", str(child), "-o", "command="],
                capture_output=True,
                text=True,
                check=False,
            )
            if current.returncode == 0 and str(folder) in current.stdout:
                os.killpg(child, signal.SIGKILL)
        if thread.ident is not None:
            thread.join(timeout=5)
