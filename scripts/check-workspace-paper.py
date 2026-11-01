"""Exercise both real nine-step paper workflows; untimed, before the full seal."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "benchmarks/workspace"


def observer_control(out):
    """Two actual plain/direct-observed programs with identical code and input bytes."""
    from graphunslopify import Figure

    measure = runpy.run_path(str(HERE / "measurement.py"))
    controls = []
    for identity in ("penguins-mass", "penguins-scatter"):
        spec = json.loads(
            (HERE / "figures" / (identity + ".json")).read_text(encoding="utf8")
        )
        spec["data"]["path"] = "data.csv"
        raw = (ROOT / "benchmarks/papers/sources/penguins.csv").read_bytes()
        translated = Figure(spec).translate(api="local")
        if not translated["ok"]:
            raise ValueError("Native observer control did not compile")
        code = translated["code"].encode("utf8")
        runs = {}
        for mode in ("plain", "observed"):
            folder = out / identity / mode
            folder.mkdir(parents=True, exist_ok=False)
            program = folder / "figure.py"
            program.write_bytes(code)
            (folder / "data.csv").write_bytes(raw)
            native = ["--strict", "--json", "--report", "runtime.report.json"]
            command = (
                [sys.executable, str(program), *native]
                if mode == "plain"
                else [
                    sys.executable,
                    str(HERE / "paper_capture.py"),
                    "--observations",
                    str(folder / "observations.json"),
                    "--script",
                    str(program),
                    *native,
                ]
            )
            completed = subprocess.run(
                command,
                cwd=folder,
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
                env={**os.environ, "MPLBACKEND": "Agg"},
            )
            (folder / "stdout.log").write_text(completed.stdout, encoding="utf8")
            (folder / "stderr.log").write_text(completed.stderr, encoding="utf8")
            if completed.returncode != 0:
                raise ValueError(
                    "Actual plain/observed control failed: " + completed.stderr[-600:]
                )
            if (
                program.read_bytes() != code
                or (folder / "data.csv").read_bytes() != raw
            ):
                raise ValueError("Control code/data changed")
            report = json.loads(
                (folder / "runtime.report.json").read_text(encoding="utf8")
            )
            assert report["status"] == "passed"
            runs[mode] = {
                fmt: measure["graphic_identity"](
                    (folder / ("figure." + fmt)).read_bytes(), fmt
                )
                for fmt in spec["output"]["formats"]
            }
        if runs["plain"] != runs["observed"] or not all(runs["plain"].values()):
            raise ValueError("Direct observer changed native drawing identity")
        controls.append(
            {
                "figure": identity,
                "program_sha256": hashlib.sha256(code).hexdigest(),
                "data_sha256": hashlib.sha256(raw).hexdigest(),
                "identities": runs,
                "same_program_and_data": True,
            }
        )
    return controls


def check(out, *, controls=True):
    out = Path(out).resolve()
    if out.is_relative_to(ROOT) and not out.is_relative_to(HERE / "results"):
        raise ValueError("Keep evidence outside source or under workspace/results")
    out.mkdir(parents=True, exist_ok=False)
    runpy.run_path(str(ROOT / "scripts/check-workspace-protocol.py"))["check"](ROOT)
    runner = runpy.run_path(str(HERE / "session_runner.py"))
    before = runner["source_snapshot"]()
    import graphunslopify

    package_root = Path(graphunslopify.__file__).resolve().parent
    package_bytes = {
        str(p.relative_to(package_root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in package_root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }
    if package_bytes != runner["expected_package"]():
        raise ValueError("Actual paper SDK files differ from this checkout")
    write = runner["write"]
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf8"))
    truth = json.loads((HERE / "ground-truth.json").read_text(encoding="utf8"))
    evaluate = runpy.run_path(str(HERE / "evaluation.py"))["evaluate"]
    plan = protocol["paper"]["steps"]
    sessions, errors = [], []
    proof = {
        "passed": False,
        "formal_comparison_performed": False,
        "source_sha256": before,
        "package_root": str(package_root),
        "package_sha256": package_bytes,
        "sessions": sessions,
        "errors": errors,
        "scope": "Pre-seal paper integrity only; not the formal54 paper requests or any other fixed study denominator",
    }
    for arm in ("matplotlib", "graphunslopify"):
        rows = [{"step": s["id"], "outcome": "not_run"} for s in plan]
        record = {"arm": arm, "rows": rows}
        sessions.append(record)
        try:
            producer = runpy.run_path(str(HERE / ("paper_" + arm + ".py")))["Session"](
                out / arm
            )
            for index, expected in enumerate(plan):
                name = expected["id"]
                dispatched = time.perf_counter_ns()
                answer = producer.step(name)
                returned = time.perf_counter_ns()
                row = rows[index]
                row.update(answer, outcome="completed")
                row.update(
                    parent_dispatched_ns=dispatched,
                    tool_returned_ns=returned,
                    end_to_end_origin_ns=dispatched,
                )
                checks = {}
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
                    evaluation = evaluate(
                        value["result"],
                        value["folder"],
                        answer["specs"][identity],
                        producer.root,
                        oracle,
                    )
                    checks[identity] = evaluation
                    if any(
                        not e.startswith("actual_width:") for e in evaluation["errors"]
                    ):
                        errors.append(
                            arm
                            + "/"
                            + name
                            + "/"
                            + identity
                            + ":"
                            + json.dumps(evaluation["errors"])
                        )
                    execution = value["result"].get(
                        "paper_execution", value["result"].get("execution")
                    )
                    if execution["mode"] == "executed" and any(
                        not answer["started_ns"]
                        <= e["available_monotonic_ns"]
                        <= answer["tool_end_ns"]
                        for e in value["result"]["save_observations"]
                    ):
                        errors.append("actual_save_clock:" + arm + "/" + name)
                row["evaluations"] = checks
                row["checked_ns"] = time.perf_counter_ns()
                row["task_verified_ns"] = (
                    row["checked_ns"]
                    if answer["native"]["exit_code"] == 0
                    and all(e["task_correct_verified"] for e in checks.values())
                    else None
                )
                if answer["native"]["exit_code"] != expected["exit_code"]:
                    errors.append("paper_native_status:" + arm + "/" + name)
                counts = answer["native"]["audit"]["execution_counts"]
                if arm == "graphunslopify" and (
                    counts["executed"],
                    counts["reused"],
                ) != (expected["expected_executed"], expected["expected_reused"]):
                    errors.append("paper_native_policy:" + name)
                if (
                    arm == "matplotlib"
                    and name in {"recover", "add-alias", "remove-alias"}
                    and counts["acceptance_reused"]
                ):
                    errors.append("stale_baseline_acceptance:" + name)
                write(out / "paper-progress.json", proof)
                print(
                    json.dumps(
                        {
                            "arm": arm,
                            "step": name,
                            "status": answer["native"]["status"],
                            "counts": counts,
                            "independent_task_verified": row["task_verified_ns"]
                            is not None,
                        }
                    ),
                    flush=True,
                )
        except Exception as error:  # noqa: BLE001 - preserve planned denominator and actual failure
            record["error"] = {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            }
            errors.append("execution:" + arm)
            for row in rows:
                if row["outcome"] == "not_run":
                    row["unavailable_reason"] = (
                        "Actual paper execution interrupted; no replacement"
                    )
        finally:
            write(out / "paper-progress.json", proof)
    if controls:
        try:
            proof["observer_controls"] = observer_control(out / "observer-controls")
        except Exception as error:  # noqa: BLE001 - retain actual failed control
            proof["observer_control_error"] = {
                "error": str(error),
                "traceback": traceback.format_exc(),
            }
            errors.append("observer_control")
    if runner["source_snapshot"]() != before:
        errors.append("source_changed")
    proof["passed"] = not errors
    write(out / "untimed-paper.json", proof)
    if errors:
        raise ValueError("Actual pre-seal paper checks failed: " + json.dumps(errors))
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args()
    if args.installed:
        sys.path[:] = [p for p in sys.path if Path(p).resolve() != ROOT / "python"]
        os.environ.pop("PYTHONPATH", None)
    else:
        sys.path.insert(0, str(ROOT / "python"))
        os.environ["PYTHONPATH"] = str(ROOT / "python")
    import graphunslopify

    actual = Path(graphunslopify.__file__).resolve()
    if args.installed:
        assert actual.is_relative_to(Path(sys.prefix).resolve())
    check(args.out)


if __name__ == "__main__":
    main()
