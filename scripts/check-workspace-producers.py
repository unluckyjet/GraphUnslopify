"""Untimed original-save evaluation of both producer arms; retain every task failure.

A successful harness check establishes execution and numerical/observation
integrity. Task/physical failures remain explicit outcomes, not passing figures.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import runpy
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "benchmarks/workspace"

if not __debug__:
    raise RuntimeError("Do not optimize scientific conformance guards")


def check(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source_names = [
        "benchmarks/workspace/" + name
        for name in (
            "matplotlib_producer.py",
            "graphunslopify_producer.py",
            "capture_driver.py",
            "execution_context.py",
            "measurement.py",
            "evaluation.py",
            "corpus.py",
            "policy-clarification-v2.json",
            "protocol.json",
            "ground-truth.json",
        )
    ] + [
        "scripts/check-workspace-producers.py",
        "benchmarks/papers/reference.py",
        "benchmarks/certified/measurement.py",
    ]
    source_hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in source_names
    }
    runpy.run_path(str(ROOT / "scripts/check-workspace-protocol.py"))["check"](ROOT)
    corpus = runpy.run_path(str(HERE / "corpus.py"))
    evaluator = runpy.run_path(str(HERE / "evaluation.py"))["evaluate"]
    baseline = runpy.run_path(str(HERE / "matplotlib_producer.py"))["Session"](
        output / "matplotlib"
    )
    graph = runpy.run_path(str(HERE / "graphunslopify_producer.py"))["Session"](
        output / "graphunslopify"
    )
    truth = json.loads((HERE / "ground-truth.json").read_text(encoding="utf8"))
    records = []
    integrity = []
    try:
        for index, (key, oracle) in enumerate(truth.items()):
            if "/" in key:
                name, step = key.split("/")
                original = json.loads(
                    (HERE / "figures" / (name + ".json")).read_text(encoding="utf8")
                )
                spec = dict(corpus["requests"](original, HERE / "figures"))[step]
            else:
                spec = json.loads(
                    (HERE / "figures" / (key + ".json")).read_text(encoding="utf8")
                )
            arms = [("matplotlib", baseline), ("graphunslopify", graph)]
            if index % 2:
                arms.reverse()
            for arm, session in arms:
                record = {"arm": arm, "case": key, "formal_comparison_performed": False}
                name = key.replace("/", "--")
                try:
                    result = session.render(spec, HERE / "figures", name)
                    folder = (
                        graph.folder(name)
                        if arm == "graphunslopify"
                        else baseline.root / "runs" / name
                    )
                    record.update(
                        {
                            "folder": str(folder),
                            "tool_status": result["status"],
                            "evaluation": evaluator(
                                result, folder, spec, HERE / "figures", oracle
                            ),
                            "current_evidence": session.validate(name),
                            "native_execution": result.get("execution"),
                            "translator_execution": result.get("translation_execution"),
                            "save_events": len(result["save_observations"]),
                        }
                    )
                except Exception as error:  # noqa: BLE001 - retain all attempts/tracebacks, then fail integrity below
                    record["execution_error"] = {
                        "type": type(error).__name__,
                        "message": str(error),
                        "traceback": traceback.format_exc(),
                    }
                records.append(record)
                (output / "untimed-progress.json").write_text(
                    json.dumps(records, ensure_ascii=False, indent=2, allow_nan=False)
                    + "\n",
                    encoding="utf8",
                )
                print(
                    json.dumps(
                        {
                            "arm": arm,
                            "case": key,
                            "errors": record.get("evaluation", {}).get("errors"),
                            "execution_error": record.get("execution_error", {}).get(
                                "type"
                            ),
                        }
                    ),
                    flush=True,
                )
        inputs = output / "integrity-inputs"
        inputs.mkdir()
        data = inputs / "iris.csv"
        data.write_bytes(
            (ROOT / "examples/published-papers/data/iris.csv").read_bytes()
        )
        spec = copy.deepcopy(
            json.loads((HERE / "figures/iris-scatter.json").read_text(encoding="utf8"))
        )
        spec["data"]["path"] = data.name
        for arm, session in (("matplotlib", baseline), ("graphunslopify", graph)):
            result = session.render(spec, inputs, "integrity-control")
            folder = (
                graph.folder("integrity-control")
                if arm == "graphunslopify"
                else baseline.root / "runs/integrity-control"
            )
            if not session.validate("integrity-control")["strict_accepted"]:
                raise RuntimeError(
                    "The native clean integrity fixture was not accepted"
                )
            report_file = folder / (result.get("native_report_file") or "report.json")
            producer_file = (
                folder / "figure.py" if arm == "graphunslopify" else baseline.program
            )
            targets = [
                (
                    folder / "figure.png",
                    "file_changed:figure.png"
                    if arm == "graphunslopify"
                    else "output_changed:figure.png",
                    lambda raw: raw + b"changed",
                ),
                (
                    report_file,
                    "file_changed:figure.report.json"
                    if arm == "graphunslopify"
                    else "report_changed",
                    lambda raw: raw + b" ",
                ),
                (data, "input_changed", lambda raw: raw.replace(b"\n", b"\r\n")),
                (
                    producer_file,
                    "file_changed:figure.py"
                    if arm == "graphunslopify"
                    else "producer_changed:code/producer.py",
                    lambda raw: raw + b"\n# owned source control\n",
                ),
            ]
            for path, relevant, mutation in targets:
                original = path.read_bytes()
                try:
                    path.write_bytes(mutation(original))
                    checked = session.validate("integrity-control")
                    integrity.append(
                        {
                            "arm": arm,
                            "case": relevant,
                            "detected": not checked["strict_accepted"]
                            and relevant in checked["reasons"],
                            "result": checked,
                        }
                    )
                finally:
                    path.write_bytes(original)
                if not session.validate("integrity-control")["strict_accepted"]:
                    raise RuntimeError("Restored native evidence did not recover")
                (output / "untimed-integrity-progress.json").write_text(
                    json.dumps(integrity, indent=2) + "\n", encoding="utf8"
                )
    finally:
        graph.close()
    if len(records) != 74 or {r["case"] for r in records} != set(truth):
        raise RuntimeError("An untimed case/arm was lost")
    if any(
        hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected
        for name, expected in source_hashes.items()
    ):
        raise RuntimeError("Producer/evaluator source changed during the untimed check")
    numerical_prefixes = (
        "actual_artist",
        "actual_quantity",
        "actual_identity_or_interval",
        "retained_observations",
        "current_data_bytes",
    )
    observation_prefixes = (
        "missing_original_save",
        "final_export_bytes",
        "original_save_binding",
    )
    numerical = all(
        "execution_error" not in r
        and not any(e.startswith(numerical_prefixes) for e in r["evaluation"]["errors"])
        for r in records
    )
    observation = all(
        "execution_error" not in r
        and not any(
            e.startswith(observation_prefixes) for e in r["evaluation"]["errors"]
        )
        and r["current_evidence"]["current"]
        for r in records
    )
    summary = {
        "formal_comparison_performed": False,
        "source_sha256": source_hashes,
        "actual_cases": 74,
        "native_figure_runs": sum(r.get("save_events", 0) > 0 for r in records),
        "integrity_fixture_native_runs": 2,
        "actual_native_runs_including_controls": sum(
            r.get("save_events", 0) > 0 for r in records
        )
        + 2,
        "integrity_controls": integrity,
        "refusal_cases_without_native_report": sum(
            r.get("evaluation", {}).get("correct_refusal_without_native_report", False)
            for r in records
        ),
        "numerical_parity_verified": numerical,
        "original_save_binding_verified": observation,
        "task_conformance": {
            arm: {
                "cases": 37,
                "conformant": sum(
                    r.get("evaluation", {}).get("conformant", False)
                    for r in records
                    if r["arm"] == arm
                ),
                "task_correct_verified": sum(
                    r.get("evaluation", {}).get("task_correct_verified", False)
                    for r in records
                    if r["arm"] == arm
                ),
                "execution_errors": sum(
                    "execution_error" in r for r in records if r["arm"] == arm
                ),
            }
            for arm in ("matplotlib", "graphunslopify")
        },
        "scope": "Untimed paired implementation check only. A valid harness is not a task-conformance or speed win; physical/other task failures remain in all74 rows. No formal workload denominator is filled.",
        "records": records,
    }
    (output / "untimed-producers.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf8",
    )
    if (
        not numerical
        or not observation
        or len(integrity) != 8
        or not all(r["detected"] for r in integrity)
    ):
        raise RuntimeError(
            "Original-save numerical or observation integrity is unproven; inspect retained rows"
        )
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True, type=Path)
    result = check(p.parse_args().out)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "actual_cases",
                    "native_figure_runs",
                    "refusal_cases_without_native_report",
                    "numerical_parity_verified",
                    "original_save_binding_verified",
                    "task_conformance",
                    "formal_comparison_performed",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
