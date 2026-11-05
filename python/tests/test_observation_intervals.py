"""Trace real capped line intervals through final saved PNG geometry."""

from __future__ import annotations

import copy
import csv
import json
import statistics
from importlib.resources import files
from pathlib import Path

import jsonschema
import numpy as np
import pytest
from PIL import Image

from graphunslopify import Figure
from graphunslopify.cli import main as cli
from graphunslopify.observation_geometry import resolve_summary_interval
from graphunslopify.observation_provenance import (
    _load_observation_selection,
    explain_saved_interval,
)


def render_line(tmp_path, *, group=False, **overrides):
    source = tmp_path / "measurements.csv"
    source.write_text(
        "x,y,method\n3,30,A\n1,10,A\n2,20,A\n4,40,A\n1,12,A\n3,36,A\n4,44,A\n"
        + ("4,55,B\n1,27,B\n1,32,B\n4,59,B\n" if group else "")
    )
    figure = (
        Figure.line(source)
        .x("x", "Condition")
        .y("y", "Response")
        .aggregate("mean")
        .set(
            uncertainty={"kind": "range", "display": "bar"},
            marker=True,
            **overrides,
        )
        .output(stem="intervals", formats=["png"], size="double_column", dpi=300)
    )
    if group:
        figure = figure.by("method")
    return figure.render(cwd=tmp_path / "trace", strict=False, trace_observations=True)


def loaded(result):
    report = result["report"]
    reference = report["observation_selection"]
    assert "summary_interval_geometry_gap" not in reference, reference
    path = result["script"]
    schema = files("graphunslopify").joinpath("schemas", "runtime-report.schema.json")
    jsonschema.Draft202012Validator(json.loads(schema.read_text())).validate(report)
    _, graph = _load_observation_selection(
        path.parent,
        report,
        run_id=reference["run_id"],
        program_sha256=report["script"]["sha256"],
        require_contained_png=True,
    )
    nodes = {node["id"]: node for node in graph.as_dict()["nodes"]}
    root = nodes[reference["summary_interval_geometry_node_id"]]
    return graph, root, nodes


@pytest.mark.parametrize("group", [False, True])
def test_actual_png_stems_and_caps_resolve_sorted_summary_membership(tmp_path, group):
    result = render_line(tmp_path, group=group)
    assert result["report"]["status"] == "incomplete"
    assert any(item["code"] == "uncertainty_unavailable" for item in result["report"]["findings"])
    graph, root, nodes = loaded(result)
    geometry = root["metadata"]
    image_path = result["script"].parent / geometry["image"]["path"]
    by_category = {
        ("A", 1): ([10, 12], [1, 4]),
        ("A", 3): ([30, 36], [0, 5]),
        ("A", 4): ([40, 44], [3, 6]),
    }
    if group:
        by_category.update({("B", 1): ([27, 32], [8, 9]), ("B", 4): ([55, 59], [7, 10])})
    assert len(geometry["strokes"]) == 3 * len(by_category)
    roles = {identity: [] for identity in root["inputs"]}
    with Image.open(image_path) as image:
        pixels = image.convert("RGB")
        for stroke in geometry["strokes"]:
            identity = stroke["node_id"]
            node = nodes[identity]
            keys = node["metadata"]["keys"]
            bounds, members = by_category[(keys.get("method", "A"), int(keys["x"]))]
            assert node["value"] == bounds
            assert node["metadata"]["estimator"] == "range"
            assert graph.explain(identity)["contributing_records"] == members
            roles[identity].append(stroke["role"])
            point = [statistics.mean(values) for values in zip(*stroke["endpoints"], strict=True)]
            assert resolve_summary_interval(geometry, *point) == identity
            # At least one nearby saved pixel is darker than the white axes background.
            x, y = map(round, point)
            assert (
                min(
                    min(pixels.getpixel((x + dx, y + dy))) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                )
                < 180
            )
    assert all(sorted(role) == ["cap", "cap", "stem"] for role in roles.values())
    missing = [
        node
        for node in nodes.values()
        if node.get("operation") == "summary_interval" and node["metadata"].get("unavailable")
    ]
    assert len(missing) == 1 and missing[0]["value"] == [None, None]
    assert missing[0]["id"] not in roles
    assert resolve_summary_interval(geometry, -1, 0) is None

    overlapped = copy.deepcopy(geometry)
    first = next(item for item in overlapped["strokes"] if item["role"] == "stem")
    second = next(item for item in overlapped["strokes"] if item["node_id"] != first["node_id"])
    second.update(endpoints=first["endpoints"], clip=first["clip"])
    point = [statistics.mean(values) for values in zip(*first["endpoints"], strict=True)]
    with pytest.raises(ValueError, match="More than one"):
        resolve_summary_interval(overlapped, *point)

    image_path.write_bytes(image_path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="PNG bytes or dimensions changed"):
        loaded(result)


def test_actual_public_bootstrap_ci_strokes_and_source_membership(tmp_path, capsys):
    source = Path(__file__).parents[2] / "benchmarks/papers/sources/penguins.csv"
    original = source.read_bytes()
    figure = (
        Figure.line(source)
        .x("year", "Year")
        .y("body_mass_g", "Body mass (g)")
        .where("species", "eq", "Adelie")
        .where("sex", "eq", "male")
        .aggregate("mean")
        .set(uncertainty={"kind": "ci", "level": 0.9, "display": "bar"}, marker=True)
        .output(stem="public-ci", formats=["png"], size="double_column", dpi=300)
    )
    result = figure.render(cwd=tmp_path / "public-ci", strict=True, trace_observations=True)
    assert result["report"]["ok"], result["report"]["findings"]
    graph, root, nodes = loaded(result)
    rows = {}
    for ordinal, row in enumerate(csv.DictReader(original.decode().splitlines())):
        if row["species"] == "Adelie" and row["sex"] == "male":
            rows.setdefault(row["year"], []).append((ordinal, float(row["body_mass_g"])))
    rng = np.random.default_rng(20260902)
    reference = {}
    for year, pairs in rows.items():
        ordinals, values = zip(*pairs, strict=True)
        samples = rng.choice(values, size=(2000, len(values)), replace=True)
        reference[year] = list(ordinals), np.quantile(samples.mean(axis=1), [0.05, 0.95])
    assert len(root["inputs"]) == 3
    for stroke in root["metadata"]["strokes"]:
        node = nodes[stroke["node_id"]]
        assert node["metadata"]["estimator"] == "ci"
        expected_rows, limits = reference[node["metadata"]["keys"]["year"]]
        assert graph.explain(node["id"])["contributing_records"] == expected_rows
        assert node["value"] == pytest.approx(limits)
        assert node["metadata"]["bootstrap"] == {
            "draws": 2000,
            "level": 0.9,
            "method": "percentile",
            "seed": 20260902,
            "statistic": "mean",
        }
        point = [statistics.mean(values) for values in zip(*stroke["endpoints"], strict=True)]
        assert resolve_summary_interval(root["metadata"], *point) == node["id"]
    stroke = next(entry for entry in root["metadata"]["strokes"] if entry["role"] == "stem")
    x, y = [statistics.mean(values) for values in zip(*stroke["endpoints"], strict=True)]
    report_path = result["report_path"]
    expected = explain_saved_interval(report_path, x, y)
    assert expected["explanation"] == graph.explain(stroke["node_id"])
    capsys.readouterr()
    assert cli(["explain-interval", str(report_path), str(x), str(y)]) == 0
    assert json.loads(capsys.readouterr().out) == expected
    assert source.read_bytes() == original


def test_clip_hides_outside_interval_and_bounds_scaled_pick_tolerance(tmp_path):
    result = render_line(
        tmp_path,
        y={"field": "y", "label": "Response", "limits": [31, 46]},
    )
    _, root, nodes = loaded(result)
    info = root["metadata"]
    assert {nodes[identity]["metadata"]["keys"]["x"] for identity in root["inputs"]} == {"3", "4"}
    third = [
        stroke
        for stroke in info["strokes"]
        if nodes[stroke["node_id"]]["metadata"]["keys"]["x"] == "3"
    ]
    assert sorted(stroke["role"] for stroke in third) == ["cap", "stem"]
    stem = next(stroke for stroke in third if stroke["role"] == "stem")
    (_, bottom), (x, upper) = stem["endpoints"]
    y = (min(bottom, stem["clip"][3]) + upper) / 2
    assert resolve_summary_interval(info, x + 6, y) is None
    assert resolve_summary_interval(info, x + 6, y, tolerance=12) == stem["node_id"]
    with pytest.raises(ValueError, match="tolerance"):
        resolve_summary_interval(info, x, y, tolerance=65)
