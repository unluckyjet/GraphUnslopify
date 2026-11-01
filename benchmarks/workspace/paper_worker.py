"""One real paper producer for a complete pre-seal nine-update session."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import runpy
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
HELPERS = runpy.run_path(str(HERE / "session_worker.py"))
encoded, package_bytes = HELPERS["encoded"], HELPERS["package_bytes"]


class OwnedChildren:
    """Observe actual Popen objects without changing commands or process options."""

    def __init__(self):
        self.original = subprocess.Popen
        self.children = []
        original, children = self.original, self.children

        class ObservedPopen(original):
            def __init__(self, *args, **kwargs):
                group = bool(kwargs.get("start_new_session"))
                try:
                    super().__init__(*args, **kwargs)
                finally:
                    if getattr(self, "pid", None) is not None and self._child_created:
                        children.append((self, group))

        subprocess.Popen = ObservedPopen

    def close(self):
        subprocess.Popen = self.original
        records = []
        for child, group in reversed(self.children):
            forced = child.poll() is None
            if forced:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(child.pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )
                elif group:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGKILL)
                else:
                    child.kill()
                child.wait(timeout=5)
            records.append(
                {
                    "pid": child.pid,
                    "separate_group": group,
                    "forced_cleanup": forced,
                    "returncode": child.returncode,
                }
            )
        return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--arm", choices=("matplotlib", "graphunslopify"), required=True
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--preseal-only", action="store_true", required=True)
    args = parser.parse_args()
    root, wire = args.root.resolve(), sys.stdout
    producer, before = None, None
    plan = json.loads((HERE / "protocol.json").read_text(encoding="utf8"))["paper"][
        "steps"
    ]
    with (root / "producer.log").open("x", encoding="utf8") as log:
        ownership = OwnedChildren()
        try:
            with contextlib.redirect_stdout(log):
                preparing = time.perf_counter_ns()
                producer = runpy.run_path(str(HERE / ("paper_" + args.arm + ".py")))[
                    "Session"
                ](root / "producer")
                prepared = time.perf_counter_ns()
                evaluate = runpy.run_path(str(HERE / "evaluation.py"))["evaluate"]
                truth = json.loads(
                    (HERE / "ground-truth.json").read_text(encoding="utf8")
                )
                package_root, before = package_bytes()
            ready = {
                "event": "ready",
                "arm": args.arm,
                "track": "paper",
                "pid": os.getpid(),
                "python": sys.version,
                "package_root": package_root,
                "package_sha256": before,
                "producer_preparing_ns": preparing,
                "producer_prepared_ns": prepared,
                "ready_ns": time.perf_counter_ns(),
                "formal_comparison_performed": False,
            }
            (root / "ready.json").write_text(encoded(ready), encoding="utf8")
            wire.write(encoded(ready))
            wire.flush()
            for sequence, line in enumerate(sys.stdin):
                request = json.loads(line)
                if request["operation"] == "close":
                    break
                started = time.perf_counter_ns()
                row = {
                    "event": "result",
                    "sequence": sequence,
                    "case": request["case"],
                    "pid": os.getpid(),
                    "worker_started_ns": started,
                    "formal_comparison_performed": False,
                }
                try:
                    name = request["step"]
                    if (
                        request["operation"] != "step"
                        or sequence >= len(plan)
                        or name != plan[sequence]["id"]
                    ):
                        raise ValueError(
                            "Paper request differs from its frozen sequence"
                        )
                    with contextlib.redirect_stdout(log):
                        answer = producer.step(name)
                        returned = time.perf_counter_ns()
                        checks = {}
                        new_png = []
                        bindings = {}
                        for identity, value in answer["results"].items():
                            figure = (
                                "penguins-mass"
                                if identity == "penguins-mass-alias"
                                else identity
                            )
                            oracle = (
                                truth["penguins-mass-false-claim"]
                                if name == "false-claim" and figure == "penguins-mass"
                                else truth[figure + "/first"]
                            )
                            checks[identity] = evaluate(
                                value["result"],
                                value["folder"],
                                answer["specs"][identity],
                                producer.root,
                                oracle,
                            )
                            result = value["result"]
                            execution = result.get(
                                "paper_execution", result.get("execution")
                            )
                            if execution["mode"] == "executed":
                                for event in result["save_observations"]:
                                    if (
                                        not started
                                        <= event["available_monotonic_ns"]
                                        <= returned
                                    ):
                                        raise ValueError(
                                            "Actual paper save is outside this request"
                                        )
                                    if event["format"] == "png":
                                        new_png.append(event["available_monotonic_ns"])
                            folder = Path(value["folder"])
                            bindings[identity] = {
                                n: hashlib.sha256((folder / n).read_bytes()).hexdigest()
                                for n in ("data.csv", *result["outputs"])
                            }
                        checked = time.perf_counter_ns()
                    first = min(new_png) if new_png else None
                    native = answer["native"]
                    row.update(
                        outcome="completed",
                        paper=answer,
                        evaluations=checks,
                        current_file_sha256=bindings,
                        tool_status=native["status"],
                        tool_exit_code=native["exit_code"],
                        tool_end_ns=returned,
                        checked_ns=checked,
                        first_png_available_ns=first,
                        first_png_unavailable_reason=(
                            "No new PNG save in this reuse-only update; current export-copy availability is not exposed"
                            if first is None
                            else None
                        ),
                        tool_accepted_ns=returned if native["exit_code"] == 0 else None,
                        task_verified_ns=checked
                        if native["exit_code"] == 0
                        and all(e["task_correct_verified"] for e in checks.values())
                        else None,
                    )
                except Exception as error:  # noqa: BLE001 - retain the actual failed request
                    row.update(
                        outcome="execution_error",
                        error_type=type(error).__name__,
                        error=str(error),
                        traceback=traceback.format_exc(),
                        terminal_ns=time.perf_counter_ns(),
                    )
                record = root / f"request-{sequence:03d}.json"
                record.write_text(encoded(row), encoding="utf8")
                wire.write(encoded({**row, "record_file": str(record)}))
                wire.flush()
        finally:
            closing = time.perf_counter_ns()
            try:
                if producer is not None:
                    with contextlib.redirect_stdout(log):
                        close = getattr(producer, "close", None)
                        if close:
                            close()
            finally:
                children = ownership.close()
            if producer is not None:
                with contextlib.redirect_stdout(log):
                    _, after = package_bytes()
                    if before is not None and after != before:
                        raise RuntimeError(
                            "SDK package changed during the paper session"
                        )
            closed = {
                "event": "closed",
                "pid": os.getpid(),
                "closing_started_ns": closing,
                "closed_ns": time.perf_counter_ns(),
                "owned_children": children,
            }
            (root / "closed.json").write_text(encoded(closed), encoding="utf8")
            wire.write(encoded(closed))
            wire.flush()


if __name__ == "__main__":
    main()
