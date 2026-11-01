"""A benchmark must reject real omitted marks and incomplete measurements."""

from __future__ import annotations

import copy
import json
import runpy
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "benchmarks/workspace"
PRODUCER = runpy.run_path(str(HERE / "matplotlib_producer.py"))
NUMBERS = runpy.run_path(str(ROOT / "scripts/check-workspace-matplotlib.py"))["numbers"]
TRUTH = json.loads((HERE / "ground-truth.json").read_text(encoding="utf8"))


def test_actual_missing_scatter_point_cannot_pass_the_frozen_task():
    spec = json.loads((HERE / "figures/iris-scatter.json").read_text(encoding="utf8"))
    rows = PRODUCER["REFERENCE"]["observations"](spec, HERE / "figures")[1:]
    figure, axes = plt.subplots()
    try:
        for group in sorted({r[1] for r in rows}):
            selected = [r for r in rows if r[1] == group]
            axes.scatter([r[0] for r in selected], [r[2] for r in selected], label=group)
        measured = PRODUCER["REFERENCE"]["scatter_artists"](axes)
        assert len(measured) == 149
        with pytest.raises(AssertionError, match="count differs"):
            NUMBERS(measured, TRUTH["iris-scatter/first"]["artists"])
    finally:
        plt.close(figure)


def test_actual_mean_only_image_cannot_pass_a_sample_sd_task(tmp_path):
    spec = json.loads((HERE / "figures/penguins-mass.json").read_text(encoding="utf8"))
    del spec["uncertainty"]
    spec["output"].update(formats=["png"], dpi=144)
    session = PRODUCER["Session"](tmp_path / "owned")
    report = session.render(spec, HERE / "figures", "mean-only-control")
    assert report["status"] == "passed"  # Valid mean-only spec, wrong for the frozen SD task.
    assert all(r["low"] is None and r["high"] is None for r in report["artists"])
    with pytest.raises(AssertionError):
        NUMBERS(report["artists"], TRUTH["penguins-mass/first"]["artists"])


def test_a_probe_cannot_silently_drop_a_required_quantity():
    expected = TRUTH["penguins-mass/first"]["artists"]
    observed = [
        {key: value for key, value in row.items() if key != "n"} for row in copy.deepcopy(expected)
    ]
    NUMBERS(observed, expected)
    del observed[0]["mean"]
    with pytest.raises(AssertionError, match="measurement fields"):
        NUMBERS(observed, expected)


def test_returned_report_cannot_rewrite_expected_output_checksums(tmp_path):
    spec = json.loads((HERE / "figures/iris-scatter.json").read_text(encoding="utf8"))
    spec["output"].update(formats=["png"], dpi=144)
    session = PRODUCER["Session"](tmp_path / "owned")
    report = session.render(spec, HERE / "figures", "client-report-control")
    image = session.root / "runs/client-report-control/figure.png"
    image.write_bytes(image.read_bytes() + b"changed")
    report["outputs"]["figure.png"] = PRODUCER["digest"](image.read_bytes())
    assert report["outputs"] is not session.records["client-report-control"]["outputs"]
    current = session.validate("client-report-control")
    assert not current["strict_accepted"]
    assert "output_changed:figure.png" in current["reasons"]
