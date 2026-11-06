"""Bind a painted band span to the two intervals that actually define it."""

from __future__ import annotations

import copy
import math
import statistics

import pytest
from test_observation_intervals import loaded

from graphunslopify import Figure
from graphunslopify.observation_geometry import resolve_summary_interval
from graphunslopify.observation_provenance import explain_saved_interval

_VALUES = "x,y\n30,27\n1,8\n100,50\n3,13\n10,21\n300,90\n1,12\n30,40\n3,19\n100,66\n300,111\n"
_EXPECTED = {
    "1": ([8, 12], [1, 6]),
    "3": ([13, 19], [3, 8]),
    "10": ([None, None], [4]),
    "30": ([27, 40], [0, 7]),
    "100": ([50, 66], [2, 9]),
    "300": ([90, 111], [5, 10]),
}


def render_band(tmp_path, scale, sort=True):
    source = tmp_path / "band.csv"
    source.write_text(_VALUES)
    return (
        Figure.line(source)
        .x("x", "Dose", scale=scale)
        .y("y", "Response", scale=scale)
        .aggregate("mean")
        .set(uncertainty={"kind": "range", "display": "band"}, sort_x=sort)
        .output(stem="band", formats=["png"], size="double_column", dpi=300)
        .render(cwd=tmp_path / "drawn", strict=False, trace_observations=True)
    )


@pytest.mark.parametrize("scale", ["linear", "log"])
def test_saved_band_picks_exact_endpoints_and_rendered_spans(tmp_path, scale):
    result = render_band(tmp_path, scale)
    assert result["report"]["status"] == "incomplete"
    graph, root, nodes = loaded(result)
    info = root["metadata"]
    assert info["strokes"] == [] and len(info["bands"]) == 3
    pairs = []
    for strip in info["bands"]:
        a, b = [nodes[identity] for identity in strip["interval_ids"]]
        names = [item["metadata"]["keys"]["x"] for item in (a, b)]
        pairs.append(tuple(names))
        assert nodes[strip["node_id"]]["inputs"] == strip["interval_ids"]
        assert nodes[strip["node_id"]]["operation"] == "summary_band_span"
        assert nodes[strip["node_id"]]["value"] is None
        for item, name in zip((a, b), names, strict=True):
            bounds, records = _EXPECTED[name]
            assert item["value"] == bounds
            assert graph.explain(item["id"])["contributing_records"] == records
        first, second, third, fourth = strip["endpoints"]
        mid = [statistics.mean(axis) for axis in zip(first, second, third, fourth, strict=True)]
        assert resolve_summary_interval(info, *mid, tolerance=0) == strip["node_id"]
        explanation = explain_saved_interval(result["report_path"], *mid)
        assert explanation["explanation"]["node_id"] == strip["node_id"]
        assert explanation["explanation"]["contributing_records"] == sorted(
            _EXPECTED[names[0]][1] + _EXPECTED[names[1]][1]
        )
        for identity, low, high in zip(
            strip["interval_ids"], (first, third), (second, fourth), strict=True
        ):
            assert (
                resolve_summary_interval(info, low[0], statistics.mean((low[1], high[1])))
                == identity
            )
    assert pairs == [("1", "3"), ("30", "100"), ("100", "300")]

    end_first = info["bands"][0]["endpoints"][2][0]
    start_second = info["bands"][1]["endpoints"][0][0]
    gap_ratio = (10 - 3) / (30 - 3) if scale == "linear" else math.log(10 / 3) / math.log(30 / 3)
    gap = end_first + (start_second - end_first) * gap_ratio
    left, top, right, bottom = info["bands"][0]["clip"]
    assert left < gap < right
    assert resolve_summary_interval(info, gap, (top + bottom) / 2) is None

    overlap = copy.deepcopy(info)
    first, second = overlap["bands"][:2]
    second.update(endpoints=first["endpoints"], clip=first["clip"])
    mid = [statistics.mean(axis) for axis in zip(*first["endpoints"], strict=True)]
    with pytest.raises(ValueError, match="More than one"):
        resolve_summary_interval(overlap, *mid)


def test_nonmonotone_draw_retains_graph_and_reports_unsupported_placement(tmp_path):
    result = render_band(tmp_path, "linear", sort=False)
    report = result["report"]
    assert report["status"] == "incomplete"
    reference = report["observation_selection"]
    assert reference["summary_node_id"]
    assert "summary_interval_geometry_node_id" not in reference
    assert "not monotone" in reference["summary_interval_geometry_gap"]
    with pytest.raises(ValueError, match="not monotone"):
        explain_saved_interval(result["report_path"], 100, 100)
