"""Every shared bar panel must retain its actual value/interval extents."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.container import BarContainer

from graphunslopify.transport import local_request


def fixture(layout, *, sign=1, shared=True, limits=None, intervals=False, stacked=False):
    horizontal = layout == "facet-horizontal"
    repeated = layout == "repeat-vertical"
    small = [1, 2, 2, 3] if intervals else [1, 2]
    large = [3, 5, 4, 6] if intervals else [2, 4]
    categories = ["A", "A", "B", "B"] if intervals else ["A", "B"]
    if repeated:
        frame = pd.DataFrame(
            {
                "category": categories,
                "small": np.array(small) * sign,
                "large": np.array(large) * sign,
            }
        )
    else:
        frame = pd.DataFrame(
            {
                "category": categories * 2,
                "condition": ["one"] * len(small) + ["two"] * len(large),
                "value": np.array(small + large) * sign,
            }
        )
    spec = {
        "kind": "bar",
        "x": {"field": "category", "label": "Category"},
        "y": {"field": "small" if repeated else "value", "label": "Value"},
        "data": {"path": "data.csv"},
        "aggregation": "mean",
        "orientation": "horizontal" if horizontal else "vertical",
        "legend": {"show": False},
        "output": {"stem": "range", "formats": ["png"], "size": "double_column"},
    }
    if limits is not None:
        spec["y"]["limits"] = limits
    if intervals:
        spec["uncertainty"] = {"kind": "range"}
    if repeated:
        spec["repeat"] = {"fields": ["small", "large"], "share_x": True, "share_y": shared}
    else:
        spec["facet"] = {
            "by": "condition",
            "columns": 2,
            "share_x": shared if horizontal else True,
            "share_y": True if horizontal else shared,
        }
    if stacked:
        assert not repeated
        frame = pd.concat(
            [frame.assign(series="first"), frame.assign(series="second")], ignore_index=True
        )
        spec.update({"group": "series", "stacked": True, "aggregation": "sum"})
    return spec, frame


def rendered(tmp_path, monkeypatch, layout, **options):
    spec, frame = fixture(layout, **options)
    translated = local_request("convert", spec)
    assert translated["ok"], translated
    script = tmp_path / "range.py"
    script.write_text(translated["code"], encoding="utf8")
    frame.to_csv(tmp_path / "data.csv", index=False)
    run = subprocess.run(
        [sys.executable, str(script), "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    report = json.loads(run.stdout)
    definition = importlib.util.spec_from_file_location("shared_bar_range", script)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    with patch.object(plt, "close"), contextlib.redirect_stdout(io.StringIO()):
        module.main()
    return run, report, plt.gcf().axes


def value_limits(ax, layout):
    return sorted(ax.get_xlim() if layout == "facet-horizontal" else ax.get_ylim())


def ends(ax, layout):
    horizontal = layout == "facet-horizontal"
    return [
        (bar.get_x(), bar.get_x() + bar.get_width())
        if horizontal
        else (bar.get_y(), bar.get_y() + bar.get_height())
        for bar in ax.patches
    ]


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize("layout", ["repeat-vertical", "facet-vertical", "facet-horizontal"])
@pytest.mark.parametrize("sign", [1, -1])
def test_shared_automatic_range_contains_all_panels(tmp_path, monkeypatch, layout, sign):
    run, report, axes = rendered(tmp_path, monkeypatch, layout, sign=sign)
    assert run.returncode == 0 and report["status"] == "passed", report
    assert len(axes) == 2
    for ax, expected in zip(axes, [[1, 2], [2, 4]], strict=True):
        np.testing.assert_allclose(
            [pair[1] for pair in ends(ax, layout)], np.array(expected) * sign
        )
    bounds = [value_limits(ax, layout) for ax in axes]
    np.testing.assert_allclose(bounds[0], bounds[1])
    for ax, (low, high) in zip(axes, bounds, strict=True):
        assert low <= 0 <= high
        assert all(low <= value <= high for pair in ends(ax, layout) for value in pair)
    assert min(bounds[0]) <= sign * 4 <= max(bounds[0])
    assert "bar_mark_clipped" not in {item["code"] for item in report["findings"]}


@pytest.mark.parametrize("layout", ["repeat-vertical", "facet-vertical", "facet-horizontal"])
def test_unshared_panels_keep_their_independent_ranges(tmp_path, monkeypatch, layout):
    run, report, axes = rendered(tmp_path, monkeypatch, layout, shared=False)
    assert run.returncode == 0 and report["status"] == "passed", report
    assert value_limits(axes[0], layout)[1] < 4 < value_limits(axes[1], layout)[1]


@pytest.mark.parametrize("layout", ["repeat-vertical", "facet-vertical", "facet-horizontal"])
def test_explicit_limits_still_clip_and_fail_strictly(tmp_path, monkeypatch, layout):
    run, report, axes = rendered(tmp_path, monkeypatch, layout, limits=[0, 3])
    assert run.returncode == 2 and report["status"] == "failed"
    assert "bar_mark_clipped" in {item["code"] for item in report["findings"]}
    assert all(value_limits(ax, layout) == [0, 3] for ax in axes)
    assert any(value == 4 for pair in ends(axes[1], layout) for value in pair)


@pytest.mark.parametrize("layout", ["repeat-vertical", "facet-vertical", "facet-horizontal"])
def test_shared_range_contains_actual_uncertainty_endpoints(tmp_path, monkeypatch, layout):
    run, report, axes = rendered(tmp_path, monkeypatch, layout, intervals=True)
    assert run.returncode == 0 and report["status"] == "passed", report
    np.testing.assert_allclose(value_limits(axes[0], layout), value_limits(axes[1], layout))
    coordinate = 0 if layout == "facet-horizontal" else 1
    for ax, expected in zip(axes, [[[1, 2], [2, 3]], [[3, 5], [4, 6]]], strict=True):
        low, high = value_limits(ax, layout)
        intervals = [
            segment
            for container in ax.containers
            if isinstance(container, BarContainer) and container.errorbar
            for line in container.errorbar.lines[2]
            for segment in line.get_segments()
        ]
        assert intervals
        np.testing.assert_allclose(np.asarray(intervals)[:, :, coordinate], expected)
        assert all(low <= point[coordinate] <= high for segment in intervals for point in segment)
    assert value_limits(axes[1], layout)[1] >= 6
    assert not {"bar_mark_clipped", "bar_interval_clipped"} & {
        item["code"] for item in report["findings"]
    }


@pytest.mark.parametrize("layout", ["facet-vertical", "facet-horizontal"])
def test_stacked_panel_range_contains_totals_not_just_segment_heights(
    tmp_path, monkeypatch, layout
):
    run, report, axes = rendered(tmp_path, monkeypatch, layout, stacked=True)
    assert run.returncode == 0 and report["status"] == "passed", report
    for ax in axes:
        low, high = value_limits(ax, layout)
        assert all(low <= value <= high for pair in ends(ax, layout) for value in pair)
    assert value_limits(axes[1], layout)[1] >= 8
    np.testing.assert_allclose(sorted(pair[1] for pair in ends(axes[1], layout)), [2, 4, 4, 8])
