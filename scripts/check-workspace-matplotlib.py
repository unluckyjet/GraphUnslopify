"""Untimed conformance of the independent producer, actual exports and integrity.

This is implementation validation, not the preregistered formal comparison.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
import runpy
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "benchmarks/workspace"

if not __debug__:
    raise RuntimeError("Run conformance checks without Python optimization")


def numbers(actual, expected, *, counts=False):
    assert len(actual) == len(expected), "Actual artist/summary count differs"
    for left, right in zip(actual, expected, strict=True):
        required = set(right) - (set() if counts else {"n"})
        assert set(left) == required, "Actual measurement fields differ"
        for key, value in left.items():
            if isinstance(value, float):
                assert math.isclose(value, right[key], rel_tol=1e-10, abs_tol=1e-10), (
                    key,
                    value,
                    right[key],
                )
            else:
                assert value == right[key], (key, value, right[key])


def exports(folder, spec, report):
    width = {"single_column": 3.4, "double_column": 7.0}[spec["output"]["size"]]
    result = []
    assert set(report["outputs"]) == {
        "figure." + fmt for fmt in spec["output"]["formats"]
    }
    for fmt in spec["output"]["formats"]:
        path = folder / ("figure." + fmt)
        if fmt == "png":
            with Image.open(path) as image:
                dpi = image.info["dpi"]
                assert all(abs(value - spec["output"]["dpi"]) < 1 for value in dpi)
                actual = image.width / dpi[0]
        elif fmt == "svg":
            token = ET.fromstring(path.read_bytes()).attrib["width"]
            match = re.fullmatch(r"([0-9.]+)pt", token)
            assert match, token
            actual = float(match[1]) / 72
        else:
            assert fmt == "pdf"
            actual = float(PdfReader(path).pages[0].mediabox.width) / 72
        assert abs(actual - width) <= 0.02, (fmt, actual, width)
        result.append({"format": fmt, "actual_width_in": actual})
    return result


def check(output):
    protocol = runpy.run_path(str(ROOT / "scripts/check-workspace-protocol.py"))[
        "check"
    ](ROOT)
    clarification = json.loads(
        (HERE / "policy-clarification-v2.json").read_text(encoding="utf8")
    )
    assert clarification["original_protocol_sha256"] == protocol["protocol_sha256"]
    assert (
        clarification["paper_execution_expectations_apply_to"]
        == "graphunslopify-policy-conformance"
    )
    assert clarification["baseline_execution_counts_are_observed_outcomes"] is True
    assert (
        clarification["baseline_may_safely_reuse_unchanged_renders_and_calculations"]
        is True
    )
    assert (
        clarification[
            "both_arms_must_establish_current_acceptance_for_all_paper_members"
        ]
        is True
    )
    assert clarification["old_acceptance_may_be_copied_as_a_calculation"] is False
    assert (
        clarification["formal_measurements_permitted_by_this_checkpoint_alone"] is False
    )
    producer = runpy.run_path(str(HERE / "matplotlib_producer.py"))
    corpus = runpy.run_path(str(HERE / "corpus.py"))
    truth = json.loads((HERE / "ground-truth.json").read_text(encoding="utf8"))
    session = producer["Session"](output)
    cases = []
    for key, oracle in truth.items():
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
        name = key.replace("/", "--")
        report = session.render(spec, HERE / "figures", name)
        assert report["status"] == oracle["status"], (
            key,
            report["status"],
            report["inspection"]["findings"],
        )
        assert report["exit_code"] == oracle["exit_code"]
        assert report["retained_observations"] == oracle["retained_observations"]
        numbers(report["artists"], oracle["artists"])
        if spec["kind"] == "bar":
            numbers(report["reference"], oracle["artists"], counts=True)
        folder = session.root / "runs" / name
        for saved in report["save_observations"]:
            numbers(saved["artists"], oracle["artists"])
            assert saved["sha256"] == producer["digest"](
                (folder / saved["file"]).read_bytes()
            )
        assert report["labels"] == {
            "title": spec.get("title", ""),
            "x": producer["axis_label"](spec["x"]),
            "y": producer["axis_label"](spec["y"]),
        }
        receipt = session.validate(name)
        assert receipt["current"] and receipt["strict_accepted"] == (
            oracle["status"] == "passed"
        )
        cases.append(
            {
                "case": key,
                "status": report["status"],
                "cache_hit": report["calculation_cache"]["hit"],
                "actual_saved_artists": len(report["artists"]),
                "exports": exports(folder, spec, report),
            }
        )
        (session.root / "untimed-progress.json").write_bytes(producer["encoded"](cases))
    assert len(cases) == 37
    assert next(c for c in cases if c["case"] == "penguins-mass/title")["cache_hit"]
    assert next(c for c in cases if c["case"] == "penguins-mass-false-claim")[
        "cache_hit"
    ]
    # All mutations use owned clones; original data and installed sources stay intact.
    data = session.root / "control-data.csv"
    data.write_bytes((ROOT / "examples/published-papers/data/iris.csv").read_bytes())
    spec = copy.deepcopy(
        json.loads((HERE / "figures/iris-scatter.json").read_text(encoding="utf8"))
    )
    spec["data"]["path"] = data.name
    session.render(spec, session.root, "integrity-control")
    folder = session.root / "runs/integrity-control"
    controls = []
    for path, reason, changed in [
        (folder / "figure.png", "output_changed:figure.png", lambda b: b + b"changed"),
        (folder / "report.json", "report_changed", lambda b: b + b" "),
        (data, "input_changed", lambda b: b.replace(b"\n", b"\r\n")),
        (
            session.program,
            "producer_changed:code/producer.py",
            lambda b: b + b"\n# owned control\n",
        ),
    ]:
        original = path.read_bytes()
        try:
            path.write_bytes(changed(original))
            current = session.validate("integrity-control")
            assert not current["strict_accepted"] and reason in current["reasons"]
            controls.append({"case": reason, "result": current})
        finally:
            path.write_bytes(original)
        assert session.validate("integrity-control")["strict_accepted"]
    result = {
        "passed": True,
        "protocol_sha256": protocol["protocol_sha256"],
        "formal_comparison_performed": False,
        "numerical_cases": cases,
        "integrity_controls": controls,
        "actual_producer_executions": 38,
        "producer_sha256": producer["digest"](session.program.read_bytes()),
        "conformance_checker_sha256": producer["digest"](Path(__file__).read_bytes()),
        "policy_clarification_sha256": producer["digest"](
            (HERE / "policy-clarification-v2.json").read_bytes()
        ),
        "scope": "Untimed baseline implementation conformance only. No Graph comparison, formal reliability/reproduction/GUI track, speed result or outside evaluation.",
    }
    (session.root / "untimed-conformance.json").write_bytes(producer["encoded"](result))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True, type=Path)
    output = p.parse_args().out
    try:
        result = check(output)
    except Exception as error:
        if output.is_dir():
            (output / "untimed-failure.json").write_text(
                json.dumps(
                    {
                        "type": type(error).__name__,
                        "message": str(error),
                        "formal_comparison_performed": False,
                    }
                )
                + "\n",
                encoding="utf8",
            )
        raise
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "numerical_cases": len(result["numerical_cases"]),
                "integrity_controls": len(result["integrity_controls"]),
                "formal_comparison_performed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
