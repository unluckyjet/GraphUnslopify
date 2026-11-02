"""Real isolated process/request envelopes for the frozen operational sequence.

This checkpoint only supports pre-seal conformance. Complete paper/reliability/
profile/GUI controllers and a public implementation seal remain prerequisites
for a formal comparison. No observations here establish performance superiority.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import queue
import runpy
import signal
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def write(path, value):
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf8"
    )


def source_snapshot():
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf8"))
    names = set(protocol["frozen_assets"])
    names.update(
        p.relative_to(ROOT).as_posix()
        for p in HERE.rglob("*")
        if p.is_file()
        and p.suffix in {".py", ".json", ".csv"}
        and "results" not in p.relative_to(HERE).parts
        and "__pycache__" not in p.parts
    )
    names.update(
        ("benchmarks/papers/reference.py", "benchmarks/certified/measurement.py")
    )
    names.update(
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "scripts").glob("check-workspace-*.py")
    )
    names.add(".github/workflows/checks.yml")
    names.add(".github/workflows/workspace-native-reproduction.yml")
    return {
        n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in sorted(names)
    }


def expected_package():
    base = ROOT / "python/graphunslopify"
    return {
        p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(base.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }


def schedule():
    """Exactly24 complete eight-request sessions; never alternate mid-session."""
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf8"))
    result = []
    for index, figure in enumerate(protocol["single_pipeline"]["figures"]):
        for repeat in range(protocol["single_pipeline"]["sessions_per_arm_figure"]):
            arms = ["matplotlib", "graphunslopify"]
            if (index + repeat) % 2:
                arms.reverse()
            for arm in arms:
                result.append({"figure": figure, "session": repeat, "arm": arm})
    return result


class LiveSession:
    """One owned worker and its actual children; no timeout-driven replacement."""

    def __init__(
        self,
        arm,
        folder,
        *,
        python=sys.executable,
        installed=False,
        timeout=240,
        track="single",
    ):
        if track not in {"single", "paper"}:
            raise ValueError("Unknown isolated session track")
        self.track = track
        self.request_sequence = 0
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=False)
        self.timeout = timeout
        self.events = queue.Queue()
        self.process = None
        self.reader = None
        self.closed = None
        self.source_before = source_snapshot()
        self.package_before = expected_package()
        env = {**os.environ, "MPLBACKEND": "Agg", "PYTHONIOENCODING": "utf-8"}
        env["MPLCONFIGDIR"] = str(self.folder / "fresh-font-cache")
        if installed:
            env.pop("PYTHONPATH", None)
        else:
            env["PYTHONPATH"] = str(ROOT / "python")
        self.stderr = (self.folder / "stderr.log").open("x", encoding="utf8")
        self.wire = (self.folder / "wire.jsonl").open("x", encoding="utf8")
        self.launched_ns = time.perf_counter_ns()
        options = (
            {"start_new_session": True}
            if os.name != "nt"
            else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        )
        try:
            self.process = subprocess.Popen(
                [
                    python,
                    str(
                        HERE
                        / (
                            "paper_worker.py"
                            if track == "paper"
                            else "session_worker.py"
                        )
                    ),
                    "--arm",
                    arm,
                    "--root",
                    str(self.folder),
                    "--preseal-only",
                ],
                cwd=self.folder,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self.stderr,
                text=True,
                encoding="utf8",
                bufsize=1,
                **options,
            )
            self.reader = threading.Thread(target=self._read, daemon=True)
            self.reader.start()
            self.ready = self.receive()
            self.ready_received_ns = time.perf_counter_ns()
            if self.ready.get("event") != "ready":
                raise RuntimeError("Worker did not establish readiness")
            if self.ready["package_sha256"] != self.package_before:
                raise RuntimeError("Actual worker SDK files do not match this checkout")
            write(
                self.folder / "parent-startup.json",
                {
                    "launched_ns": self.launched_ns,
                    "ready_received_ns": self.ready_received_ns,
                    "ready": self.ready,
                    "font_cache": env["MPLCONFIGDIR"],
                    "formal_comparison_performed": False,
                },
            )
        except BaseException:
            self.terminate()
            raise

    def _read(self):
        try:
            for line in self.process.stdout:
                self.wire.write(line)
                self.wire.flush()
                self.events.put(line)
        finally:
            self.events.put(None)

    def receive(self):
        line = self.events.get(timeout=self.timeout)
        if line is None:
            raise RuntimeError("Owned worker exited before its response")
        return json.loads(line)

    def request(self, payload):
        dispatched = time.perf_counter_ns()
        sequence = self.request_sequence
        self.request_sequence += 1
        self.last_dispatch = {
            "case": payload["case"],
            "operation": payload["operation"],
            "sequence": sequence,
            "parent_dispatched_ns": dispatched,
            "dispatch_state": "attempted",
        }
        self.process.stdin.write(json.dumps(payload, allow_nan=False) + "\n")
        self.process.stdin.flush()
        self.last_dispatch["dispatch_state"] = "flushed"
        row = self.receive()
        received = time.perf_counter_ns()
        if (
            row.get("event") != "result"
            or row.get("case") != payload["case"]
            or row.get("sequence") != sequence
            or self.track == "single"
            and row.get("operation") != payload["operation"]
        ):
            raise RuntimeError("Response belongs to a different operation/request")
        # The outer actor observes task acceptance after receiving the response.
        row["worker_task_verified_ns"] = row.get("task_verified_ns")
        if row.get("task_verified_ns") is not None:
            row["task_verified_ns"] = received
        return {
            **row,
            "parent_dispatched_ns": dispatched,
            "parent_received_ns": received,
        }

    def terminate(self):
        if self.process is not None and self.process.poll() is None:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                # Give the owned worker's finally block a chance to close SDK
                # children, which deliberately own separate process groups.
                try:
                    os.kill(self.process.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
                try:
                    self.process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    # Identify actual descendants before reparenting; no name/
                    # pattern based process killing. Retain the observed tree.
                    listing = subprocess.check_output(
                        ["ps", "-axo", "pid=,ppid="], text=True
                    )
                    parents = {
                        int(p): int(parent)
                        for p, parent in (line.split() for line in listing.splitlines())
                    }
                    owned = {self.process.pid}
                    while True:
                        found = {p for p, parent in parents.items() if parent in owned}
                        if found <= owned:
                            break
                        owned.update(found)
                    write(self.folder / "forced-cleanup-pids.json", sorted(owned))
                    for pid in sorted(owned - {self.process.pid}, reverse=True):
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    try:
                        os.killpg(self.process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            self.process.wait(timeout=30)
        if self.process is not None and os.name != "nt":
            # The worker owns this process group from Popen(start_new_session).
            # Drain inherited-group descendants even when its leader exited;
            # separately grouped SDK children are closed inside the worker.
            try:
                os.killpg(self.process.pid, 0)
            except ProcessLookupError:
                pass
            else:
                write(
                    self.folder / "session-group-cleanup.json",
                    {"pgid": self.process.pid},
                )
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(self.process.pid, signal.SIGKILL)
        if self.reader is not None:
            self.reader.join(timeout=10)
            if self.reader.is_alive():
                raise RuntimeError("Owned stdout reader did not close")
        if self.process is not None:
            for stream in (self.process.stdin, self.process.stdout):
                if stream:
                    stream.close()
        self.stderr.close()
        self.wire.close()

    def close(self):
        try:
            self.process.stdin.write('{"operation":"close"}\n')
            self.process.stdin.flush()
            self.closed = self.receive()
            if self.closed.get("event") != "closed":
                raise RuntimeError("Owned worker did not acknowledge closure")
            if self.process.wait(timeout=30) != 0:
                raise RuntimeError("Owned worker did not exit successfully")
            if source_snapshot() != self.source_before:
                raise RuntimeError("Comparison code/data changed during the session")
            write(self.folder / "parent-closure.json", self.closed)
        finally:
            self.terminate()


def run_sequence(
    arm, figure, folder, *, python=sys.executable, installed=False, timeout=240
):
    """Retain all eight planned cells even if process startup/request/shutdown fails."""
    spec = json.loads(
        (HERE / "figures" / (figure + ".json")).read_text(encoding="utf8")
    )
    corpus = runpy.run_path(str(HERE / "corpus.py"))
    requests = corpus["requests"](spec, HERE / "figures")
    folder = Path(folder).resolve()
    if folder.is_relative_to(ROOT) and not folder.is_relative_to(HERE / "results"):
        raise ValueError("Keep owned outputs outside source or under workspace/results")
    folder.mkdir(parents=True, exist_ok=False)
    rows = [
        {
            "arm": arm,
            "figure": figure,
            "step": step,
            "phase": "cold" if i == 0 else "warm",
            "outcome": "not_run",
            "formal_comparison_performed": False,
        }
        for i, (step, _) in enumerate(requests)
    ]
    result = {
        "arm": arm,
        "figure": figure,
        "rows": rows,
        "formal_comparison_performed": False,
        "scope": "Pre-seal live-session conformance only; no formal latency comparison",
        "session_error": None,
        "closure_error": None,
    }
    live = None
    try:
        live = LiveSession(
            arm, folder / "live", python=python, installed=installed, timeout=timeout
        )
        result["startup"] = {
            "launched_ns": live.launched_ns,
            "ready_received_ns": live.ready_received_ns,
            "pid": live.ready["pid"],
            "python": live.ready["python"],
            "package_root": live.ready["package_root"],
        }
        for index, (step, request) in enumerate(requests):
            answer = live.request(
                {
                    "operation": "render",
                    "spec": request,
                    "base": str(HERE / "figures"),
                    "name": step,
                    "case": figure + "/" + step,
                }
            )
            rows[index].update(answer)
            origin = live.launched_ns if index == 0 else answer["parent_dispatched_ns"]
            rows[index]["end_to_end_origin_ns"] = origin
            if answer["outcome"] == "completed" and (
                not origin
                <= answer["worker_started_ns"]
                <= answer["tool_end_ns"]
                <= answer["checked_ns"]
                <= answer["parent_received_ns"]
            ):
                rows[index]["timing_envelope_valid"] = False
                raise ValueError(
                    "Real process timestamps do not share the request envelope"
                )
            rows[index]["timing_envelope_valid"] = answer["outcome"] == "completed"
            write(Path(folder) / "sequence-progress.json", result)
    except Exception as error:  # noqa: BLE001 - retain the full planned denominator and actual traceback
        result["session_error"] = {
            "type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
        }
        for row in rows:
            if row["outcome"] == "not_run":
                row["unavailable_reason"] = (
                    "Session interrupted; no substitute worker/request"
                )
    finally:
        if live is not None:
            try:
                live.close()
                result["closure"] = live.closed
            except Exception as error:  # noqa: BLE001 - an unsuccessful close invalidates clean-session evidence
                result["closure_error"] = {
                    "type": type(error).__name__,
                    "error": str(error),
                    "traceback": traceback.format_exc(),
                }
        write(Path(folder) / "sequence.json", result)
    return result
