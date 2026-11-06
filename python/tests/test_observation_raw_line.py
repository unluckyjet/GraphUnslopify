"""Trace unaggregated line vertices to the exact drawn prepared positions."""

from __future__ import annotations

import copy
import hashlib

import pytest
from test_observation_line_estimates import read_geometry

from graphunslopify import Figure
from graphunslopify.observation_geometry import resolve_summary_estimate
from graphunslopify.observation_provenance import (
    _load_observation_selection,
    explain_saved_estimate,
)


def raw_line(tmp_path, csv, *, x="x", temporal=False, **options):
    source = tmp_path / "rows.csv"
    source.write_text(csv)
    return (
        Figure.line(source)
        .x(x, "Step", temporal=temporal)
        .y("y", "Response")
        .set(marker=True, **options)
        .output(stem="rows", formats=["png"], size="double_column", dpi=300)
        .render(cwd=tmp_path / "render", strict=False, trace_observations=True)
    )


def plotted_points(graph, geometry, curve=None):
    for mark in geometry["estimates"]:
        if mark["kind"] in ("dot", "vertex") and mark.get("curve") == curve:
            yield mark, graph._nodes[mark["node_id"]]


def test_temporal_sort_preserves_quoted_csv_ordinals_and_duplicate_points(tmp_path):
    result = raw_line(
        tmp_path,
        'day,y,notes,selected\n2026-01-03,40,"two\nlines",yes\n2026-01-01,10,first,yes\n'
        "2026-01-02,20,one,yes\n2026-01-02,20,two,yes\n2026-01-04,99,no,no\n",
        x="day",
        temporal=True,
        filter=[{"field": "selected", "op": "eq", "value": "yes"}],
    )
    graph, geometry = read_geometry(result)
    points = list(plotted_points(graph, geometry))
    assert [node["value"] for _, node in points] == [10, 20, 20, 40]
    assert all(node["operation"] == "line_observation" for _, node in points)
    observed_ordinals = [graph.explain(node["id"])["contributing_records"] for _, node in points]
    assert observed_ordinals[0] == [1] and observed_ordinals[-1] == [0]
    assert {tuple(rows) for rows in observed_ordinals[1:3]} == {(2,), (3,)}
    assert points[1][0]["center"] == points[2][0]["center"]
    with pytest.raises(ValueError, match="More than one"):
        resolve_summary_estimate(geometry, *points[1][0]["center"])
    answer = explain_saved_estimate(result["report_path"], *points[-1][0]["center"])
    assert answer["explanation"]["contributing_records"] == [0]
    reference = result["report"]["observation_selection"]
    assert graph.explain(reference["node_id"])["excluded_records"] == [4]


def test_unaggregated_delta_keeps_the_hidden_baseline_observations(tmp_path):
    result = raw_line(
        tmp_path,
        "x,y,method\n2,15,ours\n1,8,base\n1,10,ours\n2,5,base\n1,6,base\n",
        group="method",
        transform={"kind": "delta_vs_baseline", "baseline": "base"},
    )
    graph, geometry = read_geometry(result)
    expected = {"1": (3, [1, 2, 4]), "2": (10, [0, 3])}
    for mark, node in plotted_points(graph, geometry):
        keys = node["metadata"]["keys"]
        assert keys["method"] == "ours"
        value, records = expected.pop(keys["x"])
        assert node["value"] == value
        answer = explain_saved_estimate(result["report_path"], *mark["center"])["explanation"]
        assert answer["contributing_records"] == records
        assert any(item.get("operation") == "delta_vs_baseline" for item in answer["nodes"])
    assert not expected


def test_unaggregated_wide_fields_keep_original_measurement_identity(tmp_path):
    result = raw_line(
        tmp_path,
        "x,01,1\n3,9,31\n1,4,11\n2,6,21\n",
        series_from_columns={"fields": ["01", "1"], "series_name": "method", "value_name": "y"},
    )
    graph, geometry = read_geometry(result)
    expected = {
        ("01", "1"): (4, 1),
        ("01", "2"): (6, 2),
        ("01", "3"): (9, 0),
        ("1", "1"): (11, 1),
        ("1", "2"): (21, 2),
        ("1", "3"): (31, 0),
    }
    for _, node in plotted_points(graph, geometry):
        keys = node["metadata"]["keys"]
        method = keys["method"]
        value, ordinal = expected.pop((method, keys["x"]))
        assert node["value"] == value
        answer = graph.explain(node["id"])
        assert answer["contributing_records"] == [ordinal]
        fields = {
            item["metadata"]["source_field"]
            for item in answer["nodes"]
            if item.get("operation") == "wide_reshape"
        }
        assert fields == {method}
    assert not expected


def test_unaggregated_line_smoothing_uses_raw_positions(tmp_path):
    result = raw_line(
        tmp_path,
        "x,y\n3,14\n1,7\n2,12\n",
        smooth={"kind": "rolling", "window": 3, "show_raw": True},
    )
    graph, geometry = read_geometry(result)
    raw = next(
        (mark, node)
        for mark, node in plotted_points(graph, geometry, "raw")
        if node["metadata"]["keys"]["x"] == "2"
    )
    smoothed = next(
        (mark, node)
        for mark, node in plotted_points(graph, geometry, "smoothed")
        if node["metadata"]["keys"]["x"] == "2"
    )
    assert raw[1]["value"] == 12 and smoothed[1]["value"] == 11
    assert graph.explain(raw[1]["id"])["contributing_records"] == [2]
    answer = explain_saved_estimate(result["report_path"], *smoothed[0]["center"])["explanation"]
    assert answer["contributing_records"] == [0, 1, 2]
    assert {graph._nodes[item]["operation"] for item in smoothed[1]["inputs"]} == {
        "line_observation"
    }


def test_moved_raw_position_is_refused_even_with_rehashed_graph(tmp_path):
    result = raw_line(tmp_path, "x,y\n1,4\n2,8\n")
    graph, _ = read_geometry(result)
    report = copy.deepcopy(result["report"])
    ref = report["observation_selection"]
    summary = graph._nodes[ref["summary_node_id"]]
    panel = graph._nodes[summary["inputs"][0]]
    first, second = [graph._nodes[identity] for identity in panel["inputs"]]
    moved = graph.calculate(
        "line_observation",
        first["inputs"],
        value=first["value"],
        metadata={
            **first["metadata"],
            "prepared_position": second["metadata"]["prepared_position"],
        },
    )
    updated_panel = graph.calculate(
        "summary_panel", [moved, second["id"]], value=2, metadata=panel["metadata"]
    )
    ref["summary_node_id"] = graph.calculate("ordinary_summaries", [updated_panel], value=1)
    directory = result["script"].parent
    payload = graph.to_json()
    (directory / ref["path"]).write_bytes(payload)
    ref["sha256"] = hashlib.sha256(payload).hexdigest()
    with pytest.raises(ValueError, match="Line observation inputs do not match"):
        _load_observation_selection(
            directory,
            report,
            run_id=ref["run_id"],
            program_sha256=report["script"]["sha256"],
            require_contained_png=True,
        )


def test_missing_raw_measurement_keeps_its_exclusion_and_breaks_the_line(tmp_path):
    result = raw_line(tmp_path, "x,y\n1,4\n2,\n3,8\n")
    graph, geometry = read_geometry(result)
    assert [node["value"] for _, node in plotted_points(graph, geometry)] == [4, 8]
    assert all(mark["kind"] == "dot" for mark in geometry["estimates"])
    (unavailable,) = [
        node
        for node in graph._nodes.values()
        if node.get("operation") == "line_observation" and node["value"] is None
    ]
    assert unavailable["metadata"]["value_status"] == "missing"
    explanation = graph.explain(unavailable["id"])
    assert explanation["contributing_records"] == []
    assert explanation["excluded_records"] == [1]
