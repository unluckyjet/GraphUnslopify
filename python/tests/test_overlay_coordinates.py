"""Known category/value associations checked on actual converted overlay artists."""

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


def spec(kind="bar", mark="line", **extra):
    layer = {"mark": mark, "label": "Reference"}
    if mark in {"line", "scatter", "band"}:
        layer["y"] = "reference"
    if mark == "band":
        layer["y2"] = "upper"
    if mark == "rug":
        layer["filter"] = [{"field": "category", "op": "eq", "value": "01"}]
    if mark == "rule":
        layer["value"] = 5
    return {
        "kind": kind,
        "data": {"path": "data.csv"},
        "x": {"field": "category", "label": "Category"},
        "y": {"field": "value", "label": "Value"},
        "category_order": ["B", "01", "1"],
        "legend": {"show": False},
        "layers": [layer],
        "output": {"stem": "overlay", "formats": ["png", "svg"], "dpi": 150},
        **({"aggregation": "mean"} if kind == "bar" else {}),
        **({"uncertainty": {"kind": "sem"}} if kind == "forest" else {}),
        **({"normalize": "none"} if kind == "confusion_matrix" else {}),
        **({"start": 0} if kind == "waterfall" else {}),
        **({"group": "series"} if kind == "slope" else {}),
        **extra,
    }


def generated(tmp_path, raw, *, allow_errors=False):
    result = local_request("convert", raw)
    assert result["ok"] or allow_errors, result
    path = tmp_path / "overlay.py"
    path.write_text(result["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("overlay_reference", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module


def rows():
    return pd.DataFrame(
        [
            {
                "category": name,
                "value": value,
                "reference": reference,
                "upper": reference + 2,
                "series": "first",
            }
            for name, reference in [("01", 10), ("1", 20), ("B", 30)]
            for value in [1, 2, 4]
        ]
    )


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize("kind", ["bar", "box", "violin", "raincloud", "slope"])
@pytest.mark.parametrize("mark", ["line", "scatter", "rug", "band"])
def test_overlay_uses_actual_category_positions_and_preserves_rows(tmp_path, kind, mark):
    module = generated(tmp_path, spec(kind, mark))
    data = module.prepare(rows())
    before = data.copy(deep=True)
    fig, ax = plt.subplots()
    module.draw_panel(ax, data)
    module.draw_layers(ax, data)
    fig.canvas.draw()
    assert [t.get_text() for t in ax.get_xticklabels()] == ["B", "01", "1"]
    pd.testing.assert_frame_equal(before, data)
    if mark in {"line", "rug"}:
        actual = ax.lines[-1]
        if mark == "rug":
            np.testing.assert_array_equal(actual.get_xdata(orig=False), [1, 1, 1])
            np.testing.assert_allclose(actual.get_ydata(orig=False), [0.01] * 3)
        else:
            np.testing.assert_array_equal(actual.get_xdata(orig=False), [0] * 3 + [1] * 3 + [2] * 3)
            np.testing.assert_array_equal(actual.get_ydata(), [30] * 3 + [10] * 3 + [20] * 3)
    elif mark == "scatter":
        actual = ax.collections[-1].get_offsets()
        np.testing.assert_array_equal(actual[:, 0], [0] * 3 + [1] * 3 + [2] * 3)
        np.testing.assert_array_equal(actual[:, 1], [30] * 3 + [10] * 3 + [20] * 3)
    else:
        vertices = ax.collections[-1].get_paths()[0].vertices
        assert set(map(tuple, vertices)) == {(0, 30), (0, 32), (1, 10), (1, 12), (2, 20), (2, 22)}


def test_grouped_bars_overlay_category_centres_in_filtered_subset(tmp_path):
    raw = spec(group="series")
    raw["layers"][0]["filter"] = [{"field": "category", "op": "eq", "value": "01"}]
    module = generated(tmp_path, raw)
    data = pd.concat([rows(), rows().assign(series="second", value=lambda f: f.value + 2)])
    _, ax = plt.subplots()
    module.draw_panel(ax, module.prepare(data))
    module.draw_layers(ax, module.prepare(data))
    np.testing.assert_array_equal(ax.lines[-1].get_xdata(orig=False), [1] * 6)
    np.testing.assert_array_equal(ax.lines[-1].get_ydata(), [10] * 6)
    assert len(ax.patches) == 6


def test_facets_use_their_own_actual_category_order(tmp_path):
    raw = spec(facet={"by": "site", "columns": 2})
    raw.pop("category_order")
    module = generated(tmp_path, raw)
    _, axes = plt.subplots(1, 2)
    first = rows().iloc[[6, 7, 8, 0, 1, 2]].assign(site="first")
    second = rows().iloc[[3, 4, 5, 0, 1, 2]].assign(site="second")
    for ax, data, expected in zip(
        axes, [first, second], [[30] * 3 + [10] * 3, [20] * 3 + [10] * 3], strict=True
    ):
        prepared = module.prepare(data)
        module.draw_panel(ax, prepared)
        module.draw_layers(ax, prepared)
        np.testing.assert_array_equal(ax.lines[-1].get_xdata(orig=False), [0] * 3 + [1] * 3)
        np.testing.assert_array_equal(ax.lines[-1].get_ydata(), expected)


def test_unknown_category_cannot_be_silently_drawn_or_dropped(tmp_path):
    module = generated(tmp_path, spec())
    _, ax = plt.subplots()
    data = module.prepare(rows())
    module.draw_panel(ax, data)
    with pytest.raises(ValueError, match="categor"):
        module.draw_layers(ax, data.assign(category="not drawn"))


def test_continuous_layers_keep_actual_numeric_coordinates(tmp_path):
    raw = spec(kind="line")
    raw.pop("category_order")
    module = generated(tmp_path, raw)
    data = pd.DataFrame({"category": [100, 1, 10], "value": [3, 1, 2], "reference": [30, 10, 20]})
    _, ax = plt.subplots()
    prepared = module.prepare(data)
    module.draw_panel(ax, prepared)
    module.draw_layers(ax, prepared)
    np.testing.assert_array_equal(ax.lines[-1].get_xdata(orig=False), [1, 10, 100])
    np.testing.assert_array_equal(ax.lines[-1].get_ydata(), [10, 20, 30])


def test_qq_horizontal_rule_needs_no_unused_raw_x_column(tmp_path):
    raw = spec(kind="qq", mark="rule")
    raw.pop("category_order")
    module = generated(tmp_path, raw)
    _, ax = plt.subplots()
    module.draw_panel(ax, pd.DataFrame({"value": [1, 2, 3, 4]}))
    module.draw_layers(ax, pd.DataFrame({"value": [1, 2, 3, 4]}))
    np.testing.assert_array_equal(ax.lines[-1].get_ydata(), [5, 5])


def test_ambiguous_base_category_labels_cannot_silently_merge_overlay_positions(tmp_path):
    module = generated(tmp_path, spec())
    _, ax = plt.subplots()
    data = module.prepare(rows())
    module.draw_panel(ax, data)
    ax.set_xticklabels(["same"] * 3)
    with pytest.raises(ValueError, match="unique plotted categor"):
        module.draw_layers(ax, data)


def test_unsupported_coordinates_also_fail_if_generated_code_is_run_directly(tmp_path):
    module = generated(tmp_path, spec(orientation="horizontal"), allow_errors=True)
    _, ax = plt.subplots()
    with pytest.raises(ValueError, match="Unsupported overlay coordinates"):
        module.draw_layers(ax, rows())


@pytest.mark.parametrize(
    ("kind", "extra"),
    [("ecdf", {}), ("calibration", {"outcome": "outcome"}), ("kaplan_meier", {"event": "event"})],
)
def test_derived_y_requires_an_explicit_overlay_measurement(kind, extra):
    raw = spec(kind, **extra)
    raw.pop("category_order")
    raw["y"]["field"] = "derived"
    assert local_request("convert", raw)["ok"]  # Explicit reference column.
    raw["layers"][0].pop("y")
    result = local_request("convert", raw)
    assert not result["ok"]
    assert any(f["code"] == "unsupported_layer_coordinates" for f in result["findings"])


def test_actual_categorical_overlay_exports_with_strict_inspection(tmp_path):
    module = generated(tmp_path, spec())
    rows().to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    completed = subprocess.run(
        [sys.executable, module.__file__, "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(completed.stdout)
    assert completed.returncode == 0 and report["status"] == "passed", completed.stderr
    assert report["data"]["counts"]["read"] == 9 and len(report["outputs"]) == 2


def test_actual_shared_x_facets_keep_global_categories_and_hidden_tick_mapping(
    tmp_path, monkeypatch
):
    raw = spec(
        facet={"by": "site", "columns": 1, "share_x": True},
        output={"stem": "shared", "formats": ["png"], "size": "double_column", "dpi": 100},
    )
    raw.pop("category_order")
    module = generated(tmp_path, raw)
    first = rows().iloc[[6, 7, 8, 0, 1, 2]].assign(site="first")
    second = rows().iloc[[3, 4, 5, 0, 1, 2]].assign(site="second")
    pd.concat([first, second]).to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    captured = []
    close = plt.close
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(plt, "close", captured.append)
    try:
        module.main()
        top, bottom = captured[-1].axes
        assert not top.get_xticklabels()  # Shared axes legitimately hide this row's labels.
        assert [t.get_text() for t in bottom.get_xticklabels()] == ["B", "01", "1"]
        np.testing.assert_array_equal(top.lines[-1].get_xdata(orig=False), [0] * 3 + [1] * 3)
        np.testing.assert_array_equal(top.lines[-1].get_ydata(), [30] * 3 + [10] * 3)
        np.testing.assert_array_equal(bottom.lines[-1].get_xdata(orig=False), [1] * 3 + [2] * 3)
        np.testing.assert_array_equal(bottom.lines[-1].get_ydata(), [10] * 3 + [20] * 3)
        assert not [f for f in module.RUN_REPORT["findings"] if f["severity"] == "error"]
    finally:
        for fig in captured:
            close(fig)


@pytest.mark.parametrize(
    ("kind", "extra", "mark"),
    [
        ("bar", {"orientation": "horizontal"}, "line"),
        ("bar", {"orientation": "horizontal"}, "rule"),
        ("forest", {}, "line"),
        ("forest", {}, "rule"),
        ("ridgeline", {}, "line"),
        ("dumbbell", {"group": "series"}, "line"),
        ("heatmap", {"value": "reference", "value_label": "Value"}, "line"),
        ("confusion_matrix", {}, "line"),
        ("sparkline_grid", {"group": "series"}, "line"),
        ("waterfall", {}, "line"),
        ("qq", {}, "line"),
    ],
)
def test_undefined_overlay_coordinate_systems_are_explicit_errors(kind, extra, mark):
    raw = spec(kind, mark, **extra)
    if kind in {"heatmap", "confusion_matrix", "sparkline_grid", "qq"}:
        raw.pop("category_order")
    result = local_request("convert", raw)
    assert not result["ok"], result
    assert any(
        f["code"] == "unsupported_layer_coordinates" and f["severity"] == "error"
        for f in result["findings"]
    )


def test_repeated_metrics_use_the_same_category_mapping_in_hidden_tick_panels(
    tmp_path, monkeypatch
):
    raw = spec(
        repeat={"fields": ["value", "upper"], "columns": 1, "share_x": True},
        output={"stem": "repeat", "formats": ["png"], "size": "double_column", "dpi": 100},
    )
    module = generated(tmp_path, raw)
    rows().to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    captured = []
    close = plt.close
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(plt, "close", captured.append)
    try:
        module.main()
        assert len(captured[-1].axes) == 2
        for ax in captured[-1].axes:
            np.testing.assert_array_equal(
                ax.lines[-1].get_xdata(orig=False), [0] * 3 + [1] * 3 + [2] * 3
            )
            np.testing.assert_array_equal(ax.lines[-1].get_ydata(), [30] * 3 + [10] * 3 + [20] * 3)
    finally:
        for fig in captured:
            close(fig)
