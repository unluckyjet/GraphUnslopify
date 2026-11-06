"""Check final estimate marks against independent inputs and actual PNG pixels."""

from __future__ import annotations

import copy
import json
import statistics
from pathlib import Path

import pytest
from PIL import Image
from test_observation_summary_charts import _BAR

from graphunslopify import Figure
from graphunslopify.cli import main as cli
from graphunslopify.observation_geometry import resolve_summary_estimate
from graphunslopify.observation_provenance import (
    _load_observation_selection,
    explain_saved_estimate,
    explain_saved_interval,
)


def render(tmp_path, kind, source_text, **overrides):
    source = tmp_path / "measurements.csv"
    source.write_text(source_text)
    spec = {
        "kind": kind,
        "data": {"path": str(source)},
        "x": {"field": "category", "label": "Condition"},
        "y": {"field": "score", "label": "Score"},
        "aggregation": "mean",
        "category_order": ["c", "a", "b"],
        "output": {"stem": "estimates", "formats": ["png"], "size": "double_column", "dpi": 300},
        **overrides,
    }
    result = Figure(spec).render(cwd=tmp_path / "run", strict=False, trace_observations=True)
    report = result["report"]
    reference = report["observation_selection"]
    directory = Path(result["report_path"]).parent
    _, graph = _load_observation_selection(
        directory,
        report,
        run_id=reference["run_id"],
        program_sha256=report["script"]["sha256"],
        require_contained_png=True,
    )
    geometry = graph._nodes[reference["summary_estimate_geometry_node_id"]]["metadata"]
    return result, graph, geometry, directory / geometry["image"]["path"]


def center(mark):
    if mark["kind"] == "dot":
        return mark["center"]
    left, top, right, bottom = mark["bounds"]
    return [(left + right) / 2, (top + bottom) / 2]


def assert_coloured(image, point):
    rgb = image.getpixel(tuple(map(round, point)))
    assert min(rgb) < 190, (point, rgb)


@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
def test_reindexed_bar_bodies_keep_exact_grouped_estimates(tmp_path, orientation):
    result, graph, geometry, png = render(
        tmp_path,
        "bar",
        _BAR,
        group="method",
        orientation=orientation,
        uncertainty={"kind": "range", "display": "bar"},
    )
    expected = {
        ("ours", "b"): (7, [0, 3]),
        ("ours", "c"): (22, [2, 5]),
        ("other", "a"): (12, [1, 4]),
        ("other", "c"): (31, [6, 7]),
    }
    marks = geometry["estimates"]
    assert len(marks) == len(expected)
    with Image.open(png) as saved:
        pixels = saved.convert("RGB")
        for mark in marks:
            assert mark["kind"] == "bar"
            identity = mark["node_id"]
            estimate = graph._nodes[identity]
            keys = estimate["metadata"]["keys"]
            value, ordinals = expected.pop((keys["method"], keys["category"]))
            assert estimate["value"] == value
            assert graph.explain(identity)["contributing_records"] == ordinals
            point = center(mark)
            assert_coloured(pixels, point)
            assert resolve_summary_estimate(geometry, *point) == identity
            assert explain_saved_estimate(result["report_path"], *point)[
                "explanation"
            ] == graph.explain(identity)
    assert not expected
    overlapped = copy.deepcopy(geometry)
    overlapped["estimates"][1]["bounds"] = overlapped["estimates"][0]["bounds"]
    with pytest.raises(ValueError, match="More than one"):
        resolve_summary_estimate(overlapped, *center(overlapped["estimates"][0]))


@pytest.mark.parametrize(
    ("aggregation", "estimator"),
    [
        ("mean", statistics.mean),
        ("median", statistics.median),
        ("sum", sum),
        ("count", len),
    ],
)
def test_unadorned_bar_estimates_without_interval_geometry(tmp_path, aggregation, estimator):
    result, graph, geometry, _ = render(
        tmp_path,
        "bar",
        "category,score\nb,-6\na,8\nb,-10\nc,0\n",
        aggregation=aggregation,
    )
    selection = result["report"]["observation_selection"]
    assert not any(key.startswith("summary_interval_geometry") for key in selection)
    expected = {"a": [8], "b": [-6, -10], **({"c": [0]} if aggregation == "count" else {})}
    for mark in geometry["estimates"]:
        node = graph._nodes[mark["node_id"]]
        category = node["metadata"]["keys"]["category"]
        assert node["value"] == estimator(expected.pop(category))
    assert not expected


def test_forest_dot_and_interval_share_image_but_have_distinct_calculations(tmp_path, capsys):
    result, graph, geometry, png = render(
        tmp_path,
        "forest",
        "category,score\nb,7\na,10\nb,7\nc,15\na,12\n",
        uncertainty={"kind": "range"},
    )
    assert result["report"]["status"] == "incomplete"
    expected = {"a": (11, [1, 4]), "b": (7, [0, 2]), "c": (15, [3])}
    marks = geometry["estimates"]
    assert len(marks) == 3
    with Image.open(png) as saved:
        pixels = saved.convert("RGB")
        for mark in marks:
            assert mark["kind"] == "dot"
            identity = mark["node_id"]
            node = graph._nodes[identity]
            category = node["metadata"]["keys"]["category"]
            value, ordinals = expected.pop(category)
            assert node["value"] == value
            assert graph.explain(identity)["contributing_records"] == ordinals
            point = mark["center"]
            assert_coloured(pixels, point)
            estimate = explain_saved_estimate(result["report_path"], *point)
            assert estimate["explanation"] == graph.explain(identity)
            interval = explain_saved_interval(result["report_path"], *point)
            assert interval["image"] == estimate["image"]
            if category == "c":
                assert interval["explanation"] is None
                capsys.readouterr()
                assert cli(["explain-estimate", str(result["report_path"]), *map(str, point)]) == 0
                assert json.loads(capsys.readouterr().out) == estimate
            else:
                assert (
                    graph._nodes[interval["explanation"]["node_id"]]["operation"]
                    == "summary_interval"
                )
    assert not expected
    png.write_bytes(png.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="PNG bytes or dimensions changed"):
        explain_saved_estimate(result["report_path"], *marks[0]["center"])
