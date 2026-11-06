"""Bind smoothed marks to the actual pandas output and summary positions."""

from __future__ import annotations

import copy
import json

import pandas as pd
import pytest
from test_observation_line_estimates import read_geometry

from graphunslopify import Figure
from graphunslopify.cli import main as cli
from graphunslopify.observation_geometry import validate_summary_estimate_geometry
from graphunslopify.observation_provenance import explain_saved_estimate

_GAPS = "x,y\n3,22\n1,8\n2,\n5,34\n1,12\n4,\n3,18\n5,36\n"


def render_smoothing(tmp_path, source_text, *, method, window, raw=True):
    source = tmp_path / "observations.csv"
    source.write_text(source_text)
    return (
        Figure.line(source)
        .x("x", "Step")
        .y("y", "Response")
        .aggregate("mean")
        .set(marker=True, smooth={"kind": method, "window": window, "show_raw": raw})
        .output(stem="smooth", formats=["png"], size="double_column", dpi=300)
        .render(cwd=tmp_path / "render", strict=False, trace_observations=True)
    )


def points_for(graph, geometry, curve):
    points = [
        mark
        for mark in geometry["estimates"]
        if mark.get("curve") == curve and mark["kind"] in ("dot", "vertex")
    ]
    return {graph._nodes[mark["node_id"]]["metadata"]["keys"]["x"]: mark for mark in points}


def test_rolling_mean_links_exact_centered_window_with_scoped_exclusions(tmp_path):
    result = render_smoothing(tmp_path, _GAPS, method="rolling", window=4)
    graph, geometry = read_geometry(result)
    points = points_for(graph, geometry, "smoothed")
    expected = {
        "1": (10, [1, 4], [2]),
        "2": (15, [0, 1, 4, 6], [2]),
        "3": (15, [0, 1, 4, 6], [2, 5]),
        "4": (27.5, [0, 3, 6, 7], [2, 5]),
        "5": (27.5, [0, 3, 6, 7], [5]),
    }
    assert points.keys() == expected.keys()
    for key, (mean, records, excluded) in expected.items():
        mark = points[key]
        node = graph._nodes[mark["node_id"]]
        metadata = node["metadata"]
        assert node["operation"] == "summary_smoothed_estimate"
        assert node["value"] == mean
        assert metadata["window"] == 4 and metadata["center"] and metadata["min_periods"] == 1
        assert (
            metadata["estimator"] == "centered_rolling_mean"
            and metadata["pandas"] == pd.__version__
        )
        answer = explain_saved_estimate(result["report_path"], *mark["center"])["explanation"]
        assert answer["node_id"] == node["id"]
        assert answer["contributing_records"] == records
        assert answer["excluded_records"] == excluded
        assert all(graph._nodes[item]["operation"] == "summary_estimate" for item in node["inputs"])
    # The optional unsmoothed artist has neither markers nor adjacent finite positions here.
    assert not points_for(graph, geometry, "raw")


def test_ema_keeps_actual_runtime_value_and_missing_decay_step(tmp_path):
    result = render_smoothing(tmp_path, _GAPS, method="ema", window=3)
    graph, geometry = read_geometry(result)
    points = points_for(graph, geometry, "smoothed")
    expected = (
        pd.Series([10.0, float("nan"), 20.0, float("nan"), 35.0]).ewm(span=3, adjust=False).mean()
    )
    ids = [points[str(index)]["node_id"] for index in range(1, 6)]
    nodes = [graph._nodes[identity] for identity in ids]
    assert [node["value"] for node in nodes] == pytest.approx(expected.tolist())
    assert nodes[1]["inputs"] == [ids[0]] and nodes[1]["value"] == 10
    missing = graph._nodes[nodes[1]["excluded"][0]]
    assert (
        missing["reason"] == "smoothing_input_unavailable" and missing["metadata"]["advances_decay"]
    )
    assert nodes[2]["inputs"][0] == ids[1] and len(nodes[2]["inputs"]) == 2
    assert graph._nodes[nodes[2]["inputs"][1]]["value"] == 20
    metadata = nodes[2]["metadata"]
    assert metadata["span"] == 3 and metadata["estimator"] == "exponential_mean"
    assert not metadata["ignore_na"] and not metadata["adjust"]
    assert metadata["pandas"] == pd.__version__
    answer = explain_saved_estimate(result["report_path"], *points["5"]["center"])["explanation"]
    assert answer["contributing_records"] == [0, 1, 3, 4, 6, 7]
    assert answer["excluded_records"] == [2, 5]


@pytest.mark.parametrize("show_raw", [True, False])
def test_coincident_raw_and_smoothed_curves_are_picked_independently(tmp_path, capsys, show_raw):
    result = render_smoothing(
        tmp_path, "x,y\n3,10\n1,10\n2,10\n", method="rolling", window=3, raw=show_raw
    )
    graph, geometry = read_geometry(result)
    smoothed = points_for(graph, geometry, "smoothed")["2"]
    smooth_answer = explain_saved_estimate(result["report_path"], *smoothed["center"])
    assert smooth_answer["explanation"]["node_id"] == smoothed["node_id"]
    assert smooth_answer["explanation"]["contributing_records"] == [0, 1, 2]
    if not show_raw:
        assert not points_for(graph, geometry, "raw")
        with pytest.raises(ValueError, match="no visible marks"):
            explain_saved_estimate(result["report_path"], *smoothed["center"], curve="raw")
        return

    raw = points_for(graph, geometry, "raw")["2"]
    assert raw["center"] == smoothed["center"]
    answer = explain_saved_estimate(result["report_path"], *smoothed["center"], curve="raw")
    assert answer["explanation"]["node_id"] == raw["node_id"]
    assert answer["explanation"]["contributing_records"] == [2]
    capsys.readouterr()
    assert (
        cli(
            [
                "explain-estimate",
                str(result["report_path"]),
                *map(str, smoothed["center"]),
                "--curve",
                "raw",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == answer

    reference = result["report"]["observation_selection"]
    altered = copy.deepcopy(graph._nodes[reference["summary_estimate_geometry_node_id"]])
    changed = next(
        mark for mark in altered["metadata"]["estimates"] if mark["node_id"] == raw["node_id"]
    )
    changed["curve"] = "smoothed"
    with pytest.raises(ValueError, match="finite summary estimate"):
        validate_summary_estimate_geometry(altered, graph._nodes)


def test_smoothing_state_starts_again_in_each_actual_facet(tmp_path):
    source = tmp_path / "facets.csv"
    source.write_text("x,y,panel\n2,200,B\n1,10,A\n1,100,B\n2,20,A\n3,30,A\n3,300,B\n")
    result = (
        Figure.line(source)
        .x("x", "Step")
        .y("y", "Response")
        .aggregate("mean")
        .facet("panel")
        .set(marker=True, smooth={"kind": "ema", "window": 3, "show_raw": False})
        .output(stem="facets", formats=["png"], size="double_column", dpi=300)
        .render(cwd=tmp_path / "render", strict=False, trace_observations=True)
    )
    graph, geometry = read_geometry(result)
    final_marks = [
        mark
        for mark in geometry["estimates"]
        if mark["kind"] == "dot" and graph._nodes[mark["node_id"]]["metadata"]["keys"]["x"] == "3"
    ]
    assert len(final_marks) == 2
    expected = {22.5: [1, 3, 4], 225.0: [0, 2, 5]}
    for mark in final_marks:
        node = graph._nodes[mark["node_id"]]
        answer = explain_saved_estimate(result["report_path"], *mark["center"])["explanation"]
        assert answer["node_id"] == node["id"]
        assert answer["contributing_records"] == expected.pop(node["value"])
    assert not expected
