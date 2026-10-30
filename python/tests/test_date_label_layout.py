"""Actual date tick fitting preserves observations, bounds and strict failures."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
from itertools import pairwise
from unittest.mock import patch

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from PIL import Image

from graphunslopify.transport import local_request


def render(tmp_path, monkeypatch, *, layout="single", years=False, limits=False, negative=False):
    dates = (
        ["2020-01-01", "2024-01-01", "2028-01-01"]
        if years
        else ["2024-01-01", "2024-01-02", "2024-01-03"]
    )
    values = [-1, 2, 3] if negative else [1, 2, 3]
    frame = pd.DataFrame({"date": dates, "value": values, "other": [2, 4, 6]})
    spec = {
        "kind": "scatter" if layout == "scatter" else "line",
        "title": "Observed dates",
        "data": {"path": "data.csv"},
        "x": {"field": "date", "label": "Date", "temporal": True},
        "y": {"field": "value", "label": "Value", "scale": "log" if negative else "linear"},
        "legend": {"show": False},
        "output": {"stem": "dates", "formats": ["png", "svg", "pdf"]},
    }
    if years:
        spec["output"]["size"] = "double_column"
    if limits:
        spec["y"]["limits"] = [0, 4]
    if layout == "facet":
        frame = pd.concat([frame.assign(panel="A"), frame.assign(panel="B")], ignore_index=True)
        spec["facet"] = {"by": "panel", "columns": 2, "share_x": True}
    elif layout == "repeat":
        spec["repeat"] = {"fields": ["value", "other"], "share_x": True}
    original = frame.to_csv(index=False).encode()
    (tmp_path / "data.csv").write_bytes(original)
    translated = local_request("convert", spec)
    assert translated["ok"], translated
    program = tmp_path / "dates.py"
    program.write_text(translated["code"])
    run = subprocess.run(
        [sys.executable, str(program), "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    report = json.loads(run.stdout)
    assert (tmp_path / "data.csv").read_bytes() == original
    definition = importlib.util.spec_from_file_location("date_layout", program)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    with patch.object(plt, "close"), contextlib.redirect_stdout(io.StringIO()):
        module.main()
    return run, report, plt.gcf(), module, spec, frame


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize("layout", ["single", "scatter", "facet", "repeat"])
def test_three_day_dates_fit_without_changing_actual_observations(tmp_path, monkeypatch, layout):
    run, report, fig, module, spec, frame = render(tmp_path, monkeypatch, layout=layout)
    assert run.returncode == 0 and report["status"] == "passed", report
    assert "tick_labels_collide" not in {f["code"] for f in report["findings"]}
    expected_x = mdates.date2num(pd.to_datetime(frame.date.iloc[:3]))
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for index, ax in enumerate(fig.axes):
        low, high = sorted(ax.get_xlim())
        labels = [
            t
            for t in ax.get_xticklabels()
            if t.get_visible() and t.get_text().strip() and low <= t.get_position()[0] <= high
        ]
        boxes = sorted([t.get_window_extent(renderer) for t in labels], key=lambda b: b.x0)
        assert all(not a.overlaps(b) for a, b in pairwise(boxes))
        points = (
            ax.collections[0].get_offsets()
            if layout == "scatter"
            else np.column_stack(
                (ax.lines[0].get_xdata(orig=False), ax.lines[0].get_ydata(orig=False))
            )
        )
        np.testing.assert_allclose(points[:, 0], expected_x)
        np.testing.assert_allclose(
            points[:, 1], [2, 4, 6] if layout == "repeat" and index else [1, 2, 3]
        )
        assert ax.get_xscale() == "linear" and ax.get_xlabel() in ["Date", ""]
    assert all((tmp_path / f"dates.{ext}").stat().st_size > 100 for ext in ["png", "svg", "pdf"])
    before = [(ax.get_xlim(), ax.get_ylim(), ax.xaxis.get_major_locator()) for ax in fig.axes]
    module.fit_date_labels(fig, fig.axes)
    assert before == [
        (ax.get_xlim(), ax.get_ylim(), ax.xaxis.get_major_locator()) for ax in fig.axes
    ]
    assert report["spec"]["x"]["field"] == spec["x"]["field"]


def test_authored_value_limits_are_preserved(tmp_path, monkeypatch):
    run, report, fig, _, spec, _ = render(tmp_path, monkeypatch, limits=True)
    assert run.returncode == 0 and report["status"] == "passed", report
    np.testing.assert_allclose(fig.axes[0].get_ylim(), spec["y"]["limits"])


def test_uncrowded_date_export_keeps_original_pixels_and_locator(tmp_path, monkeypatch):
    run, report, fig, module, _, _ = render(tmp_path, monkeypatch, years=True)
    assert run.returncode == 0 and report["status"] == "passed", report
    before = Image.open(tmp_path / "dates.png").convert("RGBA")
    locator = fig.axes[0].xaxis.get_major_locator()
    assert isinstance(locator.maxticks, dict)  # Original native defaults survived.
    # Execute the same real export with fitting disabled to test the conditional path.
    with patch.object(module, "fit_date_labels"), contextlib.redirect_stdout(io.StringIO()):
        module.main()
    after = Image.open(tmp_path / "dates.png").convert("RGBA")
    assert before.size == after.size and before.tobytes() == after.tobytes()


def test_fitted_dates_still_fail_for_hidden_negative_log_observation(tmp_path, monkeypatch):
    run, report, fig, _, _, _ = render(tmp_path, monkeypatch, negative=True)
    assert run.returncode == 2 and report["status"] == "failed", report
    assert any(
        f["code"] == "log_domain_hidden" and f["severity"] == "error" for f in report["findings"]
    )
    np.testing.assert_allclose(fig.axes[0].lines[0].get_ydata(orig=False), [-1, 2, 3])


def test_unsupported_numeric_date_limits_still_refused():
    result = local_request(
        "convert",
        {
            "kind": "line",
            "x": {"field": "date", "label": "Date", "temporal": True, "limits": [19723, 19725]},
            "y": {"field": "value", "label": "Value"},
        },
    )
    assert not result["ok"]
    assert any(f["code"] == "temporal_axis_limits" for f in result["findings"])
