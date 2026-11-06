"""Select actual calculated line points and display connections."""

from __future__ import annotations

import copy
import json
import statistics

import pytest
from PIL import Image
from test_observation_bands import render_band
from test_observation_estimates import assert_coloured

from graphunslopify import Figure
from graphunslopify.cli import main as cli
from graphunslopify.observation_geometry import resolve_summary_estimate
from graphunslopify.observation_provenance import (
    _load_observation_selection,
    explain_saved_estimate,
    explain_saved_interval,
)

_SOURCE = "x,y\n4,42\n1,8\n2,20\n1,12\n4,46\n3,\n2,24\n5,54\n5,58\n"


def read_geometry(result):
    report = result["report"]
    reference = report["observation_selection"]
    root = result["script"].parent
    _, graph = _load_observation_selection(
        root,
        report,
        run_id=reference["run_id"],
        program_sha256=report["script"]["sha256"],
        require_contained_png=True,
    )
    return graph, graph._nodes[reference["summary_estimate_geometry_node_id"]]["metadata"]


def mid(first, second):
    return tuple(statistics.mean(values) for values in zip(first, second, strict=True))


@pytest.mark.parametrize("scale", ["linear", "log"])
def test_bare_line_uses_actual_points_and_breaks_without_fabricating_values(
    tmp_path, scale, capsys
):
    source = tmp_path / "ordered.csv"
    source.write_text(_SOURCE)
    result = (
        Figure.line(source)
        .x("x", "Dose", scale=scale)
        .y("y", "Response", scale=scale)
        .aggregate("mean")
        .output(stem="curve", formats=["png"], size="double_column", dpi=300)
        .render(cwd=tmp_path / "curve", strict=False, trace_observations=True)
    )
    graph, geometry = read_geometry(result)
    expected = {"1": (10, [1, 3]), "2": (22, [2, 6]), "4": (44, [0, 4]), "5": (56, [7, 8])}
    vertices = {
        graph._nodes[m["node_id"]]["metadata"]["keys"]["x"]: m
        for m in geometry["estimates"]
        if m["kind"] == "vertex"
    }
    assert set(vertices) == set(expected)
    segments = [m for m in geometry["estimates"] if m["kind"] == "segment"]
    assert len(segments) == 2
    assert [m["endpoint_ids"] for m in segments] == [
        [vertices["1"]["node_id"], vertices["2"]["node_id"]],
        [vertices["4"]["node_id"], vertices["5"]["node_id"]],
    ]
    png = result["script"].parent / geometry["image"]["path"]
    with Image.open(png) as image:
        pixels = image.convert("RGB")
        for key, vertex in vertices.items():
            identity = vertex["node_id"]
            value, ordinals = expected[key]
            assert graph._nodes[identity]["value"] == value
            assert graph.explain(identity)["contributing_records"] == ordinals
            assert resolve_summary_estimate(geometry, *vertex["center"]) == identity
            assert_coloured(pixels, vertex["center"])
        point = mid(*segments[0]["endpoints"])
        assert_coloured(pixels, point)
    gap = mid(vertices["2"]["center"], vertices["4"]["center"])
    assert resolve_summary_estimate(geometry, *gap) is None
    answer = explain_saved_estimate(result["report_path"], *point)
    assert answer["explanation"]["node_id"] == segments[0]["node_id"]
    assert answer["explanation"]["contributing_records"] == [1, 2, 3, 6]
    assert graph._nodes[segments[0]["node_id"]]["value"] is None
    capsys.readouterr()
    assert cli(["explain-estimate", str(result["report_path"]), *map(str, point)]) == 0
    assert json.loads(capsys.readouterr().out) == answer

    overlap = copy.deepcopy(geometry)
    other = next(item for item in overlap["estimates"] if item["node_id"] == segments[1]["node_id"])
    other["endpoints"] = segments[0]["endpoints"]
    with pytest.raises(ValueError, match="More than one"):
        resolve_summary_estimate(overlap, *point)


def test_filled_band_and_estimate_connections_share_the_actual_png(tmp_path):
    result = render_band(tmp_path, "log")
    graph, geometry = read_geometry(result)
    first = next(mark for mark in geometry["estimates"] if mark["kind"] == "segment")
    point = mid(*first["endpoints"])
    estimate = explain_saved_estimate(result["report_path"], *point)
    interval = explain_saved_interval(result["report_path"], *point)
    assert estimate["image"] == interval["image"]
    assert estimate["explanation"]["node_id"] == first["node_id"]
    assert interval["explanation"] is not None
    assert graph._nodes[interval["explanation"]["node_id"]]["operation"] == "summary_band_span"


def test_dashed_line_keeps_real_marker_positions_and_exposes_connection_gap(tmp_path):
    source = tmp_path / "series.csv"
    source.write_text("x,y,model\n1,2,A\n2,4,A\n3,8,A\n1,6,B\n2,4,B\n3,2,B\n")
    result = (
        Figure.line(source)
        .x("x", "Dose")
        .y("y", "Response")
        .by("model")
        .aggregate("mean")
        .set(marker=True)
        .output(stem="curves", formats=["png"], size="double_column", dpi=300)
        .render(cwd=tmp_path / "curve", strict=False, trace_observations=True)
    )
    graph, geometry = read_geometry(result)
    assert geometry["coverage"] and "Dashed" in geometry["coverage"][0]
    dots = [item for item in geometry["estimates"] if item["kind"] == "dot"]
    assert len(dots) == 6
    shared = [
        mark for mark in dots if graph._nodes[mark["node_id"]]["metadata"]["keys"]["x"] == "2"
    ]
    assert len(shared) == 2 and shared[0]["center"] == shared[1]["center"]
    assert {tuple(graph.explain(mark["node_id"])["contributing_records"]) for mark in shared} == {
        (1,),
        (4,),
    }
    with pytest.raises(ValueError, match="More than one"):
        resolve_summary_estimate(geometry, *shared[0]["center"])


def test_simplified_line_preserves_marker_calculations_without_unsimplified_connections(tmp_path):
    source = tmp_path / "dense.csv"
    source.write_text("x,y\n" + "".join(f"{x},{x + 5}\n" for x in range(135)))
    result = (
        Figure.line(source)
        .x("x", "Step")
        .y("y", "Response")
        .aggregate("mean")
        .set(marker=True)
        .output(stem="dense", formats=["png"], size="double_column", dpi=300)
        .render(cwd=tmp_path / "curve", strict=False, trace_observations=True)
    )
    graph, geometry = read_geometry(result)
    assert geometry["coverage"] and "Simplified" in geometry["coverage"][0]
    assert {mark["kind"] for mark in geometry["estimates"]} == {"dot"}
    assert len(geometry["estimates"]) == 135
    example = geometry["estimates"][73]
    assert graph._nodes[example["node_id"]]["value"] == 78
    assert graph.explain(example["node_id"])["contributing_records"] == [73]
