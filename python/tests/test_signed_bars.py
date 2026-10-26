"""Known signed values must retain their complete visible lengths."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from graphunslopify.inspect import inspect_figure
from graphunslopify.transport import local_request


def spec(orientation="vertical", **extra):
    return {
        "kind": "bar",
        "data": {"path": "data.csv"},
        "x": {"field": "category", "label": "Category"},
        "y": {"field": "value", "label": "Value"},
        "aggregation": "mean",
        "orientation": orientation,
        "legend": {"show": False},
        "output": {"stem": "bars", "formats": ["png"], "size": "double_column"},
        **extra,
    }


def generated(tmp_path, raw):
    result = local_request("convert", raw)
    assert result["ok"], result
    path = tmp_path / "bars.py"
    path.write_text(result["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("signed_bars", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module


def findings(fig):
    return {item.code for item in inspect_figure(fig).findings}


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
@pytest.mark.parametrize(
    "values", [[-30, -20, -10.5], [-0.03, 0.02, 0.04], [0.02, 0.03, 0.04], [0, 0, 0]]
)
@pytest.mark.parametrize("grouped", [True, False])
def test_actual_automatic_range_contains_zero_and_each_signed_endpoint(
    tmp_path, orientation, values, grouped
):
    raw = spec(orientation, **({"group": "series"} if grouped else {}))
    module = generated(tmp_path, raw)
    data = pd.DataFrame({"category": ["B", "01", "1"], "value": values, "series": ["one"] * 3})
    fig, ax = plt.subplots()
    module.draw_panel(ax, data)
    module.decorate_panel(ax, data, None, True, True)
    limits = ax.get_ylim() if orientation == "vertical" else ax.get_xlim()
    assert min(limits) <= min(0, *values) and max(limits) >= max(0, *values)
    actual = [p.get_height() if orientation == "vertical" else p.get_width() for p in ax.patches]
    np.testing.assert_allclose(actual, values)
    assert "bar_mark_clipped" not in findings(fig)


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
@pytest.mark.parametrize(
    "values,limits",
    [([2, 5], (0, 3)), ([-2, -5], (-3, 0)), ([-5, 4], (-3, 3)), ([0.02, 0.05], (0, 0.03))],
)
def test_inspector_detects_value_endpoint_clipping_independently_of_sign_or_aspect(
    orientation, values, limits
):
    fig, ax = plt.subplots()
    (ax.bar if orientation == "vertical" else ax.barh)([0, 1], values)
    (ax.set_ylim if orientation == "vertical" else ax.set_xlim)(*limits)
    assert "bar_mark_clipped" in findings(fig)


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
@pytest.mark.parametrize("sign", [1, -1])
def test_inspector_detects_zero_baseline_excluded_on_both_sides(orientation, sign):
    fig, ax = plt.subplots()
    values = np.array([0.02, 0.03]) * sign
    (ax.bar if orientation == "vertical" else ax.barh)([0, 1], values)
    limits = (0.01, 0.04) if sign == 1 else (-0.04, -0.01)
    (ax.set_ylim if orientation == "vertical" else ax.set_xlim)(*limits)
    assert "truncated_bar_axis" in findings(fig)


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
@pytest.mark.parametrize("same_start", [True, False])
@pytest.mark.parametrize("clipped", [True, False])
def test_legitimate_floating_bar_baselines_are_not_forced_to_zero(orientation, same_start, clipped):
    fig, ax = plt.subplots()
    starts = [10, 10] if same_start else [10, 12]
    limits = (11, 13) if clipped else (9, 13)
    if orientation == "vertical":
        ax.bar([0, 1], [2, -1], bottom=starts)
        ax.set_ylim(*limits)
    else:
        ax.barh([0, 1], [2, -1], left=starts)
        ax.set_xlim(*limits)
    found = findings(fig)
    assert "truncated_bar_axis" not in found
    assert ("bar_mark_clipped" in found) == clipped


def test_non_bar_rectangles_are_not_classified_from_their_aspect_ratio():
    from matplotlib.patches import Rectangle

    fig, ax = plt.subplots()
    ax.add_patch(Rectangle((0, 10), 0.01, 0.02))
    ax.set_ylim(9, 11)
    assert not ({"bar_mark_clipped", "truncated_bar_axis"} & findings(fig))


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
@pytest.mark.parametrize("percent", [True, False])
def test_value_labels_preserve_sign_units_and_outward_position(tmp_path, orientation, percent):
    raw = spec(
        orientation, value_labels=True, y={"field": "value", "label": "Value", "percent": percent}
    )
    module = generated(tmp_path, raw)
    _fig, ax = plt.subplots()
    data = pd.DataFrame({"category": ["B", "01"], "value": [-0.02, 0.08]})
    module.draw_panel(ax, data)
    assert [t.get_text() for t in ax.texts] == (["-2%", "8%"] if percent else ["-0.02", "0.08"])
    for text, value in zip(ax.texts, [-0.02, 0.08], strict=True):
        location = text.get_position()[1 if orientation == "vertical" else 0]
        assert location < value if value < 0 else location > value
        alignment = (
            ("top" if value < 0 else "bottom")
            if orientation == "vertical"
            else ("right" if value < 0 else "left")
        )
        assert (text.get_va() if orientation == "vertical" else text.get_ha()) == alignment


def test_unclipped_artists_outside_the_axes_are_not_claimed_to_be_clipped():
    fig, ax = plt.subplots()
    ax.bar([0, 1], [2, 5], clip_on=False)
    ax.set_ylim(0, 3)
    assert "bar_mark_clipped" not in findings(fig)


@pytest.mark.parametrize("clipped", [True, False])
def test_actual_strict_exports_cannot_certify_clipped_negative_values(tmp_path, clipped):
    raw = spec(y={"field": "value", "label": "Value", **({"limits": [-3, 0]} if clipped else {})})
    module = generated(tmp_path, raw)
    pd.DataFrame({"category": ["B", "01"], "value": [-2, -5]}).to_csv(
        tmp_path / "data.csv", index=False, lineterminator="\n"
    )
    result = subprocess.run(
        [sys.executable, module.__file__, "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(result.stdout)
    assert report["outputs"] and report["inspection"]["checked"]
    assert report["status"] == ("failed" if clipped else "passed")
    assert result.returncode == (2 if clipped else 0)
    assert ("bar_mark_clipped" in {f["code"] for f in report["findings"]}) == clipped
