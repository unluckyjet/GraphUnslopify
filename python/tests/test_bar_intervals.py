"""Bar uncertainty endpoints cannot be reflected, omitted, or clipped cleanly."""

from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.container import BarContainer

from graphunslopify.inspect import inspect_figure
from graphunslopify.transport import local_request


def spec(orientation="vertical", **extra):
    return {
        "kind": "bar",
        "data": {"path": "data.csv"},
        "x": {"field": "category", "label": "Category"},
        "y": {"field": "value", "label": "Value"},
        "aggregation": "mean",
        "uncertainty": {"kind": "iqr"},
        "orientation": orientation,
        "legend": {"show": False},
        "output": {"stem": "bounds", "formats": ["png"], "size": "double_column"},
        **extra,
    }


def generated(tmp_path, raw, allow_errors=False):
    r = local_request("convert", raw)
    assert r["ok"] or allow_errors, r
    p = tmp_path / "bounds.py"
    p.write_text(r["code"], encoding="utf8")
    d = importlib.util.spec_from_file_location("bounds_reference", p)
    m = importlib.util.module_from_spec(d)
    d.loader.exec_module(m)
    return m


def codes(fig):
    return {f.code for f in inspect_figure(fig).findings}


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
@pytest.mark.parametrize("scale", [1.0, 1e-16, 1e16])
@pytest.mark.parametrize("sign", [1, -1])
def test_detached_bounds_are_refused_instead_of_reflected(tmp_path, orientation, scale, sign):
    m = generated(tmp_path, spec(orientation))
    _, ax = plt.subplots()
    data = pd.DataFrame(
        {"category": ["A"] * 5, "value": np.array([0, 0, 0, 0, 100]) * scale * sign}
    )
    summary = m.summarise(data)
    assert summary["_low"].iloc[0] == summary["_high"].iloc[0] == 0
    with pytest.raises(ValueError, match=r"Bar interval.*estimate"):
        m.draw_panel(ax, data)


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
def test_valid_asymmetric_interval_uses_exact_declared_endpoints(tmp_path, orientation):
    m = generated(tmp_path, spec(orientation, aggregation="median", uncertainty={"kind": "ci"}))
    _, ax = plt.subplots()
    m.draw_panel(ax, pd.DataFrame({"category": ["A"] * 3, "value": [1, 2, 9]}))
    bar = next(c for c in ax.containers if isinstance(c, BarContainer))
    segments = bar.errorbar.lines[2][0].get_segments()[0]
    np.testing.assert_array_equal(segments[:, 1 if orientation == "vertical" else 0], [1, 9])
    assert (
        bar.patches[0].get_height() if orientation == "vertical" else bar.patches[0].get_width()
    ) == 2


def test_rounding_tolerance_does_not_create_a_false_detached_interval(tmp_path):
    m = generated(tmp_path, spec())
    center = np.nextafter(0.05, math.inf)
    frame = pd.DataFrame({"value": [center], "_low": [0.05], "_high": [0.05]})
    error = m.error_pair(frame)
    assert (error >= 0).all() and np.max(error) < 1e-15


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
@pytest.mark.parametrize(
    "center,low,high,limits", [(2, 1, 9, (0, 5)), (-2, -9, -1, (-5, 0)), (0, -9, 9, (-5, 5))]
)
@pytest.mark.parametrize("clipped", [True, False])
def test_inspector_detects_actual_bar_interval_clipping(
    orientation, center, low, high, limits, clipped
):
    fig, ax = plt.subplots()
    error = np.array([[center - low], [high - center]])
    if orientation == "vertical":
        ax.bar([0], [center], yerr=error)
    else:
        ax.barh([0], [center], xerr=error)
    if not clipped:
        limits = (min(0, low) - 1, max(0, high) + 1)
    (ax.set_ylim if orientation == "vertical" else ax.set_xlim)(*limits)
    found = codes(fig)
    assert "bar_mark_clipped" not in found
    assert ("bar_interval_clipped" in found) == clipped


@pytest.mark.parametrize("kind", ["sem", "std", "ci", "range", "iqr"])
def test_stacked_uncertainty_is_explicitly_unsupported(kind):
    r = local_request("convert", spec(stacked=True, group="method", uncertainty={"kind": kind}))
    assert not r["ok"] and any(
        f["code"] == "stacked_uncertainty_unsupported" for f in r["findings"]
    )


def test_stacked_refusal_also_applies_to_direct_generated_drawing(tmp_path):
    m = generated(tmp_path, spec(stacked=True, group="method"), allow_errors=True)
    _, ax = plt.subplots()
    with pytest.raises(ValueError, match=r"Stacked.*uncertainty"):
        m.draw_panel(
            ax, pd.DataFrame({"category": ["A", "A"], "value": [1, 2], "method": ["a", "b"]})
        )


def test_unavailable_bounds_remain_unavailable(tmp_path):
    m = generated(tmp_path, spec(uncertainty={"kind": "sem"}))
    frame = m.summarise(pd.DataFrame({"category": ["A"], "value": [2]}))
    assert np.isnan(m.error_pair(frame)).all()


def test_stacked_bars_without_uncertainty_remain_supported(tmp_path):
    raw = spec(stacked=True, group="method")
    raw.pop("uncertainty")
    m = generated(tmp_path, raw)
    _, ax = plt.subplots()
    m.draw_panel(ax, pd.DataFrame({"category": ["A", "A"], "value": [1, 2], "method": ["a", "b"]}))
    assert [p.get_height() for p in ax.patches] == [1, 2]
    assert [p.get_y() for p in ax.patches] == [0, 1]


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
def test_inverted_value_axis_still_detects_clipped_interval(orientation):
    fig, ax = plt.subplots()
    if orientation == "vertical":
        ax.bar([0], [2], yerr=[[1], [7]])
        ax.set_ylim(5, 0)
    else:
        ax.barh([0], [2], xerr=[[1], [7]])
        ax.set_xlim(5, 0)
    assert "bar_interval_clipped" in codes(fig)


def test_interval_with_clipping_disabled_is_not_claimed_clipped():
    fig, ax = plt.subplots()
    ax.bar([0], [2], yerr=[[1], [7]], error_kw={"clip_on": False})
    ax.set_ylim(0, 5)
    assert "bar_interval_clipped" not in codes(fig)


@pytest.mark.parametrize("case", ["detached", "clipped", "valid"])
def test_actual_strict_exports_do_not_certify_wrong_or_hidden_bounds(tmp_path, case):
    raw = spec(
        uncertainty={"kind": "iqr"} if case == "detached" else {"kind": "ci"},
        aggregation="mean" if case == "detached" else "median",
    )
    if case == "clipped":
        raw["y"]["limits"] = [0, 5]
    m = generated(tmp_path, raw)
    values = [0, 0, 0, 0, 100] if case == "detached" else [1, 2, 9]
    pd.DataFrame({"category": ["A"] * len(values), "value": values}).to_csv(
        tmp_path / "data.csv", index=False, lineterminator="\n"
    )
    result = subprocess.run(
        [sys.executable, m.__file__, "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(result.stdout)
    assert report["status"] == ("passed" if case == "valid" else "failed")
    assert result.returncode == ({"valid": 0, "detached": 1, "clipped": 2}[case])
    if case == "clipped":
        assert report["outputs"] and any(
            f["code"] == "bar_interval_clipped" for f in report["findings"]
        )
