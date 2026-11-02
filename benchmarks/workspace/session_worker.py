"""Isolated live producer session. These are pre-seal observations, not a study."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import runpy
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXECUTION = runpy.run_path(str(HERE / "execution_context.py"))


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n"


def package_bytes():
    import graphunslopify

    root = Path(graphunslopify.__file__).parent
    return str(root), {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--arm", choices=("matplotlib", "graphunslopify"), required=True
    )
    parser.add_argument("--root", type=Path, required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preseal-only", action="store_true")
    modes.add_argument("--execution-context", type=Path)
    args = parser.parse_args()
    context = EXECUTION["load"](
        args.execution_context,
        repo=HERE.parents[1],
        track={"single", "reliability", "local", "native_ci"},
        arm=args.arm,
    )
    execution = EXECUTION["receipt"](context)
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf8"))
    root = args.root.resolve()
    session = None
    package_sha256 = None
    wire = sys.stdout
    with (root / "producer.log").open("x", encoding="utf8") as log:
        try:
            with contextlib.redirect_stdout(log):
                source = HERE / (args.arm + "_producer.py")
                session = runpy.run_path(str(source))["Session"](
                    root / "producer", execution_context=args.execution_context
                )
                evaluate = runpy.run_path(str(HERE / "evaluation.py"))["evaluate"]
                truth = json.loads(
                    (HERE / "ground-truth.json").read_text(encoding="utf8")
                )
                package_root, package_sha256 = package_bytes()
            ready = {
                "event": "ready",
                "arm": args.arm,
                "pid": os.getpid(),
                "python": sys.version,
                "execution_environment": runpy.run_path(str(HERE / "environment.py"))[
                    "observed"
                ](),
                "package_root": package_root,
                "package_sha256": package_sha256,
                "ready_ns": time.perf_counter_ns(),
                "formal_comparison_performed": context["formal_comparison_performed"],
                "execution_context": execution,
            }
            (root / "ready.json").write_text(encoded(ready), encoding="utf8")
            wire.write(encoded(ready))
            wire.flush()
            owned_cases = {}
            for sequence, line in enumerate(sys.stdin):
                request = json.loads(line)
                if request["operation"] == "close":
                    break
                EXECUTION["request"](context, request, sequence, protocol)
                started = time.perf_counter_ns()
                row = {
                    "event": "result",
                    "sequence": sequence,
                    "case": request["case"],
                    "operation": request["operation"],
                    "worker_started_ns": started,
                    "pid": os.getpid(),
                    "formal_comparison_performed": context[
                        "formal_comparison_performed"
                    ],
                    "execution_context": execution,
                }
                try:
                    if request["operation"] == "validate":
                        if owned_cases.get(request["name"]) != request["case"]:
                            raise ValueError(
                                "Validation must name this worker's original rendered case"
                            )
                        with contextlib.redirect_stdout(log):
                            current = session.validate(request["name"])
                        row.update(
                            outcome="completed",
                            current_evidence=current,
                            checked_ns=time.perf_counter_ns(),
                            task_verified_ns=None,
                            tool_accepted_ns=None,
                            scope="Current custody only; no new render or scientific acceptance",
                        )
                    else:
                        if request["operation"] != "render":
                            raise ValueError("Unsupported worker operation")
                        with contextlib.redirect_stdout(log):
                            result = session.render(
                                request["spec"], Path(request["base"]), request["name"]
                            )
                            tool_end = time.perf_counter_ns()
                            folder = (
                                session.folder(request["name"])
                                if args.arm == "graphunslopify"
                                else session.root / "runs" / request["name"]
                            )
                            current = session.validate(request["name"])
                            evaluation = evaluate(
                                result,
                                folder,
                                request["spec"],
                                Path(request["base"]),
                                truth[request["case"]],
                                execution_context=args.execution_context,
                                execution_context_sha256=context.get("context_sha256"),
                            )
                            checked = time.perf_counter_ns()
                        png = [
                            e["available_monotonic_ns"]
                            for e in result["save_observations"]
                            if e["format"] == "png"
                        ]
                        first = min(png) if png else None
                        if first is not None and not started <= first <= tool_end:
                            raise ValueError(
                                "Original-save counter is outside this request"
                            )
                        if not current["current"]:
                            raise ValueError("Current producer evidence changed")
                        report_name = (
                            "workspace-result.json"
                            if args.arm == "graphunslopify"
                            else "report.json"
                        )
                        row.update(
                            outcome="completed",
                            folder=str(folder),
                            report_file=str(folder / report_name),
                            report_sha256=hashlib.sha256(
                                (folder / report_name).read_bytes()
                            ).hexdigest(),
                            tool_status=result["status"],
                            tool_exit_code=result["exit_code"],
                            native_report_present=result.get(
                                "native_report_present", True
                            ),
                            tool_end_ns=tool_end,
                            checked_ns=checked,
                            first_png_available_ns=first,
                            first_png_unavailable_reason=(
                                "No actual PNG save; inspect the retained refusal/report"
                                if first is None
                                else None
                            ),
                            tool_accepted_ns=(
                                tool_end if result["status"] == "passed" else None
                            ),
                            task_verified_ns=(
                                checked if evaluation["task_correct_verified"] else None
                            ),
                            evaluation=evaluation,
                            current_evidence=current,
                            native_execution=result.get("execution"),
                            translation_execution=result.get("translation_execution"),
                        )
                        owned_cases[request["name"]] = request["case"]
                except Exception as error:  # noqa: BLE001 - preserve each real failed attempt
                    row.update(
                        outcome="execution_error",
                        error_type=type(error).__name__,
                        error=str(error),
                        traceback=traceback.format_exc(),
                        terminal_ns=time.perf_counter_ns(),
                    )
                path = root / (f"request-{sequence:03d}.json")
                path.write_text(encoded(row), encoding="utf8")
                wire.write(encoded({**row, "record_file": str(path)}))
                wire.flush()
        finally:
            closing = time.perf_counter_ns()
            if session is not None:
                with contextlib.redirect_stdout(log):
                    close = getattr(session, "close", None)
                    if close:
                        close()
                _, after = package_bytes()
                if package_sha256 is not None and after != package_sha256:
                    raise RuntimeError("SDK package changed during the live session")
            closed = {
                "event": "closed",
                "execution_context": execution,
                "pid": os.getpid(),
                "closing_started_ns": closing,
                "closed_ns": time.perf_counter_ns(),
            }
            (root / "closed.json").write_text(encoded(closed), encoding="utf8")
            wire.write(encoded(closed))
            wire.flush()


if __name__ == "__main__":
    main()
