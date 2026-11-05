"""Bind actual bar and forest interval artists to their exact source groups."""

from __future__ import annotations

import math
import statistics

import pytest
from test_observation_intervals import loaded

from graphunslopify import Figure
from graphunslopify.observation_geometry import resolve_summary_interval
from graphunslopify.observation_provenance import explain_saved_interval

_BAR = (
    "category,method,score\nb,ours,6\na,other,10\nc,ours,20\nb,ours,8\n"
    "a,other,14\nc,ours,24\nc,other,30\nc,other,32\n"
)


def midpoint(stroke):
    return [statistics.mean(values) for values in zip(*stroke["endpoints"], strict=True)]


@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
@pytest.mark.parametrize("grouped", [False, True])
def test_actual_bar_positions_follow_reindexed_categories(tmp_path, orientation, grouped):
    source = tmp_path / "methods.csv"
    source.write_text(_BAR)
    spec = {
        "kind": "bar",
        "data": {"path": str(source)},
        "x": {"field": "category", "label": "Condition"},
        "y": {"field": "score", "label": "Score"},
        "aggregation": "mean",
        "uncertainty": {"kind": "range", "display": "bar"},
        "orientation": orientation,
        "category_order": ["c", "a", "b"],
        "output": {"stem": "methods", "formats": ["png"], "dpi": 300, "size": "double_column"},
        **({"group": "method"} if grouped else {"legend": {"show": False}}),
    }
    result = Figure(spec).render(cwd=tmp_path / "bars", strict=True, trace_observations=True)
    assert result["report"]["ok"], result["report"]["findings"]
    graph, root, nodes = loaded(result)
    expected = (
        {
            ("other", "a"): ([10, 14], [1, 4]),
            ("other", "c"): ([30, 32], [6, 7]),
            ("ours", "b"): ([6, 8], [0, 3]),
            ("ours", "c"): ([20, 24], [2, 5]),
        }
        if grouped
        else {
            (None, "a"): ([10, 14], [1, 4]),
            (None, "b"): ([6, 8], [0, 3]),
            (None, "c"): ([20, 32], [2, 5, 6, 7]),
        }
    )
    assert len(root["inputs"]) == len(expected)
    info = root["metadata"]
    assert len(info["strokes"]) == 3 * len(expected)
    actual = set()
    for stroke in info["strokes"]:
        identity = stroke["node_id"]
        item = nodes[identity]
        keys = item["metadata"]["keys"]
        lookup = (keys.get("method"), keys["category"])
        actual.add(lookup)
        assert item["value"] == expected[lookup][0]
        assert graph.explain(identity)["contributing_records"] == expected[lookup][1]
        (x0, y0), (x1, y1) = stroke["endpoints"]
        horizontal = orientation == "horizontal"
        if stroke["role"] == "cap":
            horizontal = not horizontal
        assert math.isclose(y0, y1) if horizontal else math.isclose(x0, x1)
        point = midpoint(stroke)
        assert resolve_summary_interval(info, *point) == identity
    assert actual == expected.keys()
    first = info["strokes"][0]
    explanation = explain_saved_interval(result["report_path"], *midpoint(first))
    assert explanation["explanation"] == graph.explain(first["node_id"])


def test_actual_forest_strokes_share_an_id_for_coincident_caps(tmp_path):
    source = tmp_path / "forest.csv"
    source.write_text("category,score\nb,7\na,10\nb,7\nc,15\na,12\n")
    result = Figure(
        {
            "kind": "forest",
            "data": {"path": str(source)},
            "x": {"field": "category", "label": "Condition"},
            "y": {"field": "score", "label": "Score"},
            "uncertainty": {"kind": "range"},
            "category_order": ["c", "b", "a"],
            "output": {"stem": "forest", "formats": ["png"], "dpi": 300, "size": "double_column"},
        }
    ).render(cwd=tmp_path / "forest", strict=False, trace_observations=True)
    assert result["report"]["status"] == "incomplete"
    graph, root, nodes = loaded(result)
    info = root["metadata"]
    indexed = {
        nodes[identity]["metadata"]["keys"]["category"]: identity for identity in root["inputs"]
    }
    assert set(indexed) == {"a", "b"}
    assert graph.explain(indexed["a"])["contributing_records"] == [1, 4]
    assert graph.explain(indexed["b"])["contributing_records"] == [0, 2]
    assert nodes[indexed["a"]]["value"] == [10, 12]
    assert nodes[indexed["b"]]["value"] == [7, 7]
    caps = [
        stroke
        for stroke in info["strokes"]
        if stroke["role"] == "cap" and stroke["node_id"] == indexed["b"]
    ]
    assert len(caps) == 2 and caps[0]["endpoints"] == caps[1]["endpoints"]
    for stroke in info["strokes"]:
        assert resolve_summary_interval(info, *midpoint(stroke)) == stroke["node_id"]
