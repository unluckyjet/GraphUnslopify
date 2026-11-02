"""Real editor HTTP server with owned original-save observation, never mocked replies."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import runpy
import sys
import threading
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNNER = runpy.run_path(str(HERE / "session_runner.py"))
write = RUNNER["write"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def saved_result(state, answer, payload, execution):
    """Read this actual response's original native run; never rerender it."""
    folder = state.runs[answer["run_id"]]["folder"]
    native = answer["report"]
    stem = native["spec"]["output"]["stem"]
    program = folder / (stem + ".py")
    phase = json.loads((folder / "phase-timings.json").read_text(encoding="utf8"))
    if phase.get("execution_context") != execution:
        raise ValueError("Actual GUI observer execution context differs from server")
    if phase["program_sha256"] != digest(program):
        raise ValueError("GUI observation belongs to a different program")
    events = phase["events"]
    pngs = [event for event in events if event["format"] == "png"]
    if not pngs:
        raise ValueError("No original GUI PNG save was observed")
    source = state.uploads[payload["data_id"]]["path"]
    data = folder / "data.csv"
    if source.read_bytes() != data.read_bytes():
        raise ValueError("Original GUI upload and rendered CSV differ")
    paths = {
        stem + "." + fmt: folder / (stem + "." + fmt)
        for fmt in native["spec"]["output"]["formats"]
    }
    return {
        "status": native["status"],
        "native_report_present": True,
        "native_exit_code": answer["exit_code"],
        "exit_code_source": "actual_native_process",
        "exit_code": answer["exit_code"],
        "strict": native["policy"]["strict"],
        "fail_on_warning": native["policy"]["fail_on_warning"],
        "spec": native["spec"],
        "retained_observations": native["data"]["counts"]["finite"],
        "artists": pngs[-1]["artists"],
        "labels": pngs[-1]["labels"],
        "save_observations": events,
        "outputs": {name: digest(path) for name, path in paths.items()},
        "data_sha256": digest(data),
        "producer_sha256": digest(program),
        "environment": native["environment"],
        "execution": answer["execution"],
        "translation_execution": answer["translation_execution"],
        "native_run_id": answer["run_id"],
        "owned_folder": str(folder),
        "formal_comparison_performed": execution["formal_comparison_performed"],
        "execution_context": execution,
    }


def serve(output, *, installed=False, execution_context=None):
    if not __debug__:
        raise RuntimeError("Do not optimize GUI evidence guards")
    context = RUNNER["EXECUTION"]["load"](
        execution_context, repo=ROOT, track="gui", arm="graphunslopify"
    )
    execution = RUNNER["EXECUTION"]["receipt"](context)
    if context.get("case", {}).get(
        "profile", "fresh-wheel" if installed else "source-current"
    ) != ("fresh-wheel" if installed else "source-current"):
        raise ValueError(
            "GUI actual installed/source profile differs from execution context"
        )
    output = Path(output).resolve()
    if output.is_relative_to(ROOT) and not output.is_relative_to(HERE / "results"):
        raise ValueError("Keep GUI evidence outside source or under workspace/results")
    output.mkdir(parents=True, exist_ok=False)
    os.environ["MPLBACKEND"] = "Agg"
    os.environ["MPLCONFIGDIR"] = str(output / "fresh-font-cache")
    import graphunslopify
    from graphunslopify.preview import PreviewServer

    package = Path(graphunslopify.__file__).resolve().parent
    source_package = ROOT / "python/graphunslopify"
    if (package == source_package) == installed:
        raise ValueError("GUI source/installed package location does not match profile")
    expected = RUNNER["expected_package"]()

    def actual_package():
        return {name: digest(package / name) for name in expected}

    if actual_package() != expected:
        raise ValueError("Actual GUI package does not match checkout bytes")
    sources = RUNNER["source_snapshot"]()
    session = runpy.run_path(str(HERE / "graphunslopify_producer.py"))["Session"](
        output / "editor", execution_context=execution_context
    )
    server = PreviewServer(0)
    server.state.close()  # Unused default state has never accepted a browser request.
    server.state = session.state
    original = server.state.render
    receipts = output / "receipts"
    receipts.mkdir()
    lock = threading.Lock()
    counter = 0

    def render(payload):
        nonlocal counter
        requested = copy.deepcopy(payload)
        answer = original(payload)
        receipt = {
            "request": requested,
            "response": copy.deepcopy(answer),
            "result": None,
            "observation_error": None,
            "formal_comparison_performed": execution["formal_comparison_performed"],
            "execution_context": execution,
        }
        try:
            if (
                answer.get("run_id")
                and answer.get("report")
                and not answer.get("stale")
            ):
                receipt["result"] = saved_result(
                    server.state, answer, requested, execution
                )
        except Exception:  # noqa: BLE001 - observation must never replace the real reply
            receipt["observation_error"] = traceback.format_exc()
        with lock:
            index = counter
            counter += 1
            write(receipts / f"response-{index:04d}.json", receipt)
        return answer

    server.state.render = render
    environment = runpy.run_path(str(HERE / "environment.py"))["observed"]()
    startup = {
        "pid": os.getpid(),
        "environment": environment,
        "installed": installed,
        "package_root": str(package),
        "package_sha256": expected,
        "source_sha256": sources,
        "formal_comparison_performed": execution["formal_comparison_performed"],
        "execution_context": execution,
    }
    write(output / "startup.json", startup)

    def control():
        # Private process lifecycle only; all authoring remains in actual browser controls.
        try:
            line = sys.stdin.readline()
            if line and json.loads(line) != {"operation": "close"}:
                write(
                    output / "control-error.json",
                    {"error": "Unknown lifecycle command"},
                )
        finally:
            server.shutdown()

    threading.Thread(target=control, daemon=True).start()
    print(
        json.dumps({"url": f"http://127.0.0.1:{server.server_address[1]}", **startup}),
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
        errors = []
        if RUNNER["source_snapshot"]() != sources:
            errors.append("source_changed")
        if actual_package() != expected:
            errors.append("package_changed")
        for path, signature in session.sources.items():
            if digest(path) != signature:
                errors.append("owned_observer_changed:" + path.name)
        write(
            output / "closure.json",
            {
                "pid": os.getpid(),
                "responses": counter,
                "errors": errors,
                "execution_context": execution,
            },
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--installed", action="store_true")
    parser.add_argument("--execution-context", type=Path)
    args = parser.parse_args()
    serve(args.out, installed=args.installed, execution_context=args.execution_context)
