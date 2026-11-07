"""Native projection, binning and display alternatives for the same data."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import defaultdict

import pytest

from graphunslopify.cli import main
from graphunslopify.visual_robustness import robustness_plan, run_robustness

LINE = {
    "kind": "line",
    "title": "Response by interval",
    "data": {"path": "data.csv", "format": "csv"},
    "x": {"field": "x", "label": "Interval"},
    "y": {"field": "y", "label": "Response"},
    "group": "arm",
    "marker": True,
    "output": {"dpi": 144, "formats": ["png"]},
}
DATA = b"x,y,arm\n1,1,A\n2,10,A\n3,100,A\n1,2,B\n2,20,B\n3,200,B\n"


def choice(label, changes):
    return {
        "label": label,
        "justification": "Compare this declared presentation setting.",
        "changes": changes,
    }


def test_native_projection_cropping_and_hidden_legend(tmp_path):
    choices = [
        choice("Log response", {"y.scale": "log"}),
        choice("Restricted display", {"y.limits": [0.5, 50], "legend.show": False}),
        choice("Grid", {"style.grid": True}),
    ]
    report = run_robustness(
        {**LINE, "claims": [{"kind": "beats_everywhere", "subject": "B", "reference": "A"}]},
        choices,
        {"axis_fraction": 0.15},
        data=DATA,
        destination=tmp_path / "evidence",
        reviewed=True,
    )
    assert report["status"] == "review", report
    assert report["exit_code"] == 2
    before, logged, cropped, grid = report["choices"]
    assert logged["visual"]["axis_scales"] == ["linear", "log"]
    assert cropped["visual"]["axis_limits"][1] == [0.5, 50]
    assert before["visual"]["legend_labels"] == ["A", "B"]
    assert cropped["visual"]["legend_labels"] == []
    assert grid["visual"]["grid_visible"] and not before["visual"]["grid_visible"]
    assert grid["comparison"]["status"] == "checked"
    assert [row["centers_lost"] for row in cropped["comparison"]["projected_centers"]] == [1, 1]
    (claim,) = cropped["comparison"]["claim_comparison"]
    assert claim["before"]["verdict"] == claim["after"]["verdict"] == "holds"
    assert not claim["changed"]
    a, _ = logged["comparison"]["projected_centers"]
    assert a["series"] == "A" and a["shift_exceeds_threshold"]
    lower, upper = before["visual"]["axis_limits"][1]
    log_lower, log_upper = map(math.log10, logged["visual"]["axis_limits"][1])
    expected = max(
        abs(
            (value - lower) / (upper - lower)
            - (math.log10(value) - log_lower) / (log_upper - log_lower)
        )
        for value in (1, 10, 100)
    )
    assert a["max_common_center_axis_shift"] == pytest.approx(expected)
    assert len({item["preview"]["sha256"] for item in report["choices"]}) == 4
    output = tmp_path / "evidence"
    assert not (output / "input.csv").exists()
    for item in report["choices"]:
        preview = item["preview"]
        assert (
            hashlib.sha256((output / preview["path"]).read_bytes()).hexdigest() == preview["sha256"]
        )


def test_actual_calibration_bins_and_threshold(tmp_path):
    spec = {
        "kind": "calibration",
        "title": "Reliability by prediction",
        "bins": 3,
        "data": {"format": "csv", "path": "data.csv"},
        "x": {"field": "prediction", "label": "Mean prediction"},
        "y": {"field": "frequency", "label": "Observed fraction"},
        "outcome": "hit",
        "output": {"dpi": 144, "formats": ["png"]},
    }
    observations = [(0.0, 0), (0.19, 0), (0.31, 1), (0.61, 0), (0.64, 1), (0.81, 1), (1.0, 1)]
    data = ("prediction,hit\n" + "".join(f"{p},{hit}\n" for p, hit in observations)).encode()
    report = run_robustness(
        spec,
        [choice("Five bins", {"bins": 5})],
        {"ece_delta": 0.025},
        data=data,
        destination=tmp_path / "reliability",
        reviewed=True,
    )
    assert report["status"] == "review", report
    numbers = []
    for bins, figure in zip((3, 5), report["choices"], strict=True):
        items = defaultdict(list)
        for probability, outcome in observations:
            slot = max(0, math.ceil(probability * bins) - 1)
            items[slot].append((probability, outcome))
        assert figure["visual"]["calibration"]["bins"] == bins
        (series,) = figure["visual"]["calibration"]["series"]
        assert [row["bin"] for row in series["points"]] == sorted(items)
        assert [row["observations"] for row in series["points"]] == [
            len(items[slot]) for slot in sorted(items)
        ]
        independent = sum(
            len(group)
            * abs(statistics.mean(p for p, _ in group) - statistics.mean(o for _, o in group))
            for group in items.values()
        ) / len(observations)
        assert series["ece"] == pytest.approx(independent)
        numbers.append(independent)
    (result,) = report["choices"][1]["comparison"]["calibration"]
    assert result["ece_delta"] == pytest.approx(numbers[1] - numbers[0])
    assert result["ece_exceeds_threshold"]


def test_scatter_captures_scale_domain_loss(tmp_path):
    spec = {**LINE, "kind": "scatter"}
    spec.pop("marker")
    raw = DATA.replace(b"1,1,A", b"1,-1,A")
    report = run_robustness(
        spec,
        [choice("Log y", {"y.scale": "log"})],
        {"axis_fraction": 0.15},
        data=raw,
        destination=tmp_path / "scatter",
        reviewed=True,
    )
    compared, _ = report["choices"][1]["comparison"]["projected_centers"]
    assert compared["series"] == "A"
    assert compared["outside_scale_domain_before"] == 0
    assert compared["outside_scale_domain_after"] == compared["centers_lost"] == 1


def test_native_marker_legend_and_interval_display(tmp_path):
    spec = {
        **LINE,
        "aggregation": "mean",
        "uncertainty": {"kind": "range", "display": "band"},
        "legend": {"position": "upper_left"},
    }
    data = DATA + b"1,3,A\n2,8,A\n3,80,A\n1,4,B\n2,12,B\n3,120,B\n"
    report = run_robustness(
        spec,
        [
            choice("Plain lines", {"marker": False}),
            choice("Legend outside on the right", {"legend.position": "outside_right"}),
            choice("Error bars", {"uncertainty.display": "bar"}),
        ],
        {},
        data=data,
        destination=tmp_path / "display",
        reviewed=True,
    )
    assert report["status"] == "checked", report
    baseline, plain, legend, bars = (item["visual"] for item in report["choices"])
    assert all(row["line_markers"] for row in baseline["series"])
    assert all(not row["line_markers"] for row in plain["series"])
    assert legend["legend_labels"] == baseline["legend_labels"] == ["A", "B"]
    assert legend["legend_bounds_axes"][0][0] > baseline["legend_bounds_axes"][0][0]
    assert baseline["intervals"] == {"bars": 0, "bands": 2}
    assert bars["intervals"] == {"bars": 2, "bands": 0}
    assert [row["data_sha256"] for row in bars["series"]] == [
        row["data_sha256"] for row in baseline["series"]
    ]
    assert all(
        row["centers_lost"] == row["centers_gained"] == 0
        for item in report["choices"][1:]
        for row in item["comparison"]["projected_centers"]
    )


@pytest.mark.parametrize(
    ("changes", "thresholds"),
    [
        ({"filter": []}, {}),
        ({"x.scale": "log"}, {}),
        ({"bins": 5}, {"ece_delta": 0.05}),
        ({"style.grid": False}, {}),
        ({"y.limits": [1, 1]}, {"axis_fraction": 0.1}),
    ],
)
def test_plan_refuses_unsupported_or_unreviewed_changes(changes, thresholds):
    with pytest.raises(ValueError):
        robustness_plan(LINE, [choice("Changed", changes)], thresholds)


def test_cli_review_keeps_original_files(tmp_path, capsys):
    spec_path = tmp_path / "figure.json"
    plan_path = tmp_path / "plan.json"
    output = tmp_path / "results"
    spec_path.write_text(json.dumps(LINE))
    plan_path.write_text(
        json.dumps({"alternatives": [choice("Grid", {"style.grid": True})], "thresholds": {}})
    )
    args = ["robustness", str(spec_path), "--plan", str(plan_path), "--out-dir", str(output)]
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "review_required"
    assert not output.exists()
    (tmp_path / "data.csv").write_bytes(DATA)
    assert main([*args, "--reviewed"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "checked"
    assert json.loads(spec_path.read_bytes()) == LINE
    assert (tmp_path / "data.csv").read_bytes() == DATA
