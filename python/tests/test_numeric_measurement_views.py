"""Numeric roles must reach native artists as numbers, not category strings."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from graphunslopify.transport import local_request


def spec(kind="line", **extra):
    raw = {
        "kind": kind,
        "data": {"path": "data.parquet", "format": "parquet"},
        "x": {"field": "step", "label": "Step"},
        "y": {"field": "value", "label": "Value"},
        "legend": {"show": False},
        "output": {"stem": "numeric", "formats": ["png"], "size": "double_column"},
        **extra,
    }
    if kind == "sparkline_grid":
        raw["group"] = "method"
    if kind == "waterfall":
        raw.update(start=10, category_order=["add", "remove"])
    if kind == "heatmap":
        raw.update(value="weight", value_label="Weight", aggregation="sum")
    return raw


def generated(tmp_path, raw):
    r = local_request("convert", raw)
    assert r["ok"], r
    path = tmp_path / "numeric.py"
    path.write_text(r["code"], encoding="utf8")
    d = importlib.util.spec_from_file_location("numeric_reference", path)
    m = importlib.util.module_from_spec(d)
    d.loader.exec_module(m)
    return m


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize("kind", ["line", "scatter", "sparkline_grid"])
def test_numeric_string_coordinates_use_real_nonuniform_units(tmp_path, kind):
    m = generated(tmp_path, spec(kind))
    frame = m.prepare(
        pd.DataFrame({"step": ["1", "2", "10"], "value": ["3", "11", "7"], "method": ["a"] * 3})
    )
    _, ax = plt.subplots()
    m.draw_panel(ax, frame)
    if kind == "scatter":
        np.testing.assert_array_equal(ax.collections[0].get_offsets(), [[1, 3], [2, 11], [10, 7]])
    else:
        line = (ax.child_axes[0] if kind == "sparkline_grid" else ax).lines[0]
        np.testing.assert_array_equal(line.get_xdata(orig=False), [1, 2, 10])
        np.testing.assert_array_equal(line.get_ydata(orig=False), [3, 11, 7])


@pytest.mark.parametrize("kind", ["bar", "table"])
def test_numeric_string_sums_add_without_concatenation_or_integer_precision_loss(tmp_path, kind):
    m = generated(tmp_path, spec(kind, aggregation="sum"))
    value = 2**53 + 1
    frame = m.prepare(pd.DataFrame({"step": ["01", "01"], "value": [str(value), "1"]}))
    row = m.summarise(frame).iloc[0]
    assert row["step"] == "01" and row["value"] == value + 1
    if kind == "table":
        assert m.build_table(frame)[0].iloc[0, 0] == value + 1


def test_string_waterfall_contributions_use_numeric_sums_and_totals(tmp_path):
    m = generated(tmp_path, spec("waterfall"))
    frame = m.prepare(pd.DataFrame({"step": ["add", "add", "remove"], "value": ["2", "3", "-1"]}))
    np.testing.assert_array_equal(m.waterfall_estimate(frame)[2], [10, 15, 14])
    assert "final total 14" in m.describe_figure(frame).lower()


def test_string_heatmap_values_use_numeric_sum(tmp_path):
    m = generated(tmp_path, spec("heatmap"))
    frame = m.prepare(
        pd.DataFrame({"step": ["01", "01"], "value": ["row", "row"], "weight": ["2", "3"]})
    )
    assert m.heatmap_matrix(frame).loc["row", "01"] == 5


def test_raw_string_filter_runs_before_numeric_coercion_and_preserves_lexical_ids(tmp_path):
    m = generated(
        tmp_path, spec(group="method", filter=[{"field": "step", "op": "eq", "value": "01"}])
    )
    frame = m.prepare(
        pd.DataFrame({"step": ["01", "1"], "value": ["2", "7"], "method": ["01", "1"]})
    )
    assert (
        frame["step"].tolist() == [1]
        and frame["value"].tolist() == [2]
        and frame["method"].tolist() == ["01"]
    )


@pytest.mark.parametrize("field", ["step", "value"])
def test_nullable_string_measurements_become_numeric_missing_values_not_marker_labels(
    tmp_path, field
):
    data = pd.DataFrame(
        {
            "step": pd.Series(["1", "2", "10"], dtype="string"),
            "value": pd.Series(["3", "11", "7"], dtype="string"),
        }
    )
    data.loc[1, field] = pd.NA
    m = generated(tmp_path, spec())
    frame = m.prepare(data)
    _, ax = plt.subplots()
    m.draw_panel(ax, frame)
    line = ax.lines[0]
    if field == "step":
        np.testing.assert_allclose(line.get_xdata(orig=False), [1, 10, np.nan], equal_nan=True)
        np.testing.assert_array_equal(line.get_ydata(orig=False), [3, 7, 11])
    else:
        np.testing.assert_allclose(line.get_ydata(orig=False), [3, np.nan, 7], equal_nan=True)


def test_actual_parquet_load_and_strict_export_preserve_numeric_geometry(tmp_path, monkeypatch):
    pytest.importorskip("pyarrow")
    m = generated(tmp_path, spec())
    pd.DataFrame({"step": ["1", "2", "10"], "value": [1, 2, 10]}).to_parquet(
        tmp_path / "data.parquet", index=False
    )
    captured = []
    close = plt.close
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(plt, "close", captured.append)
    try:
        m.main()
        line = captured[-1].axes[0].lines[0]
        np.testing.assert_array_equal(line.get_xdata(orig=False), [1, 2, 10])
        np.testing.assert_array_equal(line.get_ydata(orig=False), [1, 2, 10])
    finally:
        monkeypatch.setattr(plt, "close", close)
        for fig in captured:
            if hasattr(fig, "axes"):
                close(fig)
    process = subprocess.run(
        [sys.executable, m.__file__, "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(process.stdout)
    assert (
        process.returncode == 0 and report["status"] == "passed" and report["inspection"]["checked"]
    )
