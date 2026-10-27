"""Independent known quantities for the remaining fifteen scientific presentations.

The six specialized estimator suites remain the references for KM/calibration/paired/
QQ/scaling/ridgeline. These tests inspect numerical artists, not generated source text.
"""

from __future__ import annotations

import importlib.util
import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.collections import PolyCollection
from scipy.stats import gaussian_kde

from graphunslopify.transport import local_request


def spec(kind, **extra):
    raw = {
        "kind": kind,
        "data": {"path": "data.csv"},
        "x": {"field": "category", "label": "Category"},
        "y": {"field": "value", "label": "Value"},
        "legend": {"show": False},
        "output": {"stem": "reference", "formats": ["png"], "size": "double_column"},
        **extra,
    }
    if kind in ["slope", "dumbbell", "sparkline_grid"]:
        raw.setdefault("group", "method")
    if kind == "forest":
        raw.setdefault("uncertainty", {"kind": "sem"})
    if kind == "waterfall":
        raw.update(start=10, category_order=["add", "remove"])
    if kind == "confusion_matrix":
        raw.update(normalize="none", value="weight")
    if kind == "heatmap":
        raw.update(value="weight", value_label="Weight")
    return raw


def generated(tmp_path, raw):
    r = local_request("convert", raw)
    assert r["ok"], r
    p = tmp_path / "reference.py"
    p.write_text(r["code"], encoding="utf8")
    d = importlib.util.spec_from_file_location("core_reference", p)
    m = importlib.util.module_from_spec(d)
    d.loader.exec_module(m)
    return m


def draw(tmp_path, kind, data, **extra):
    m = generated(tmp_path, spec(kind, **extra))
    fig, ax = plt.subplots()
    frame = m.prepare(data)
    m.draw_panel(ax, frame)
    return m, fig, ax, frame


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


def test_line_means_and_gap_coordinates_are_observed_values(tmp_path):
    data = pd.DataFrame({"category": [1, 1, 2, 3, 3], "value": [1, 3, np.nan, 5, 9]})
    _, _, ax, _ = draw(tmp_path, "line", data, aggregation="mean")
    line = ax.lines[0]
    np.testing.assert_array_equal(line.get_xdata(), [1, 2, 3])
    np.testing.assert_allclose(line.get_ydata(), [2, np.nan, 7], equal_nan=True)


def test_scatter_retains_observed_pairs_without_aggregation(tmp_path):
    data = pd.DataFrame({"category": [2, 1, 1, 3], "value": [7, 2, 4, np.nan]})
    _, _, ax, _ = draw(tmp_path, "scatter", data)
    offsets = ax.collections[0].get_offsets()
    assert np.ma.getmaskarray(offsets)[-1].all()
    points = np.asarray(offsets[~np.ma.getmaskarray(offsets).any(axis=1)])
    np.testing.assert_array_equal(points, [[2, 7], [1, 2], [1, 4]])


@pytest.mark.parametrize(
    "aggregation,expected", [("mean", 4), ("median", 2), ("sum", 12), ("count", 3)]
)
@pytest.mark.parametrize("kind", ["bar", "table"])
def test_known_summary_quantities_reach_bar_artists_and_table_cells(
    tmp_path, kind, aggregation, expected
):
    m = generated(tmp_path, spec(kind, aggregation=aggregation))
    data = m.prepare(pd.DataFrame({"category": ["A"] * 3, "value": [1, 2, 9]}))
    if kind == "bar":
        _, ax = plt.subplots()
        m.draw_panel(ax, data)
        assert ax.patches[0].get_height() == expected
    else:
        table, low, high = m.build_table(data)
        assert table.iloc[0, 0] == expected
        assert m.table_cell(table, low, high, table.index[0], table.columns[0]) == f"{expected:.2f}"


def test_tukey_box_quartiles_whiskers_and_outlier_are_independent(tmp_path):
    _, _, ax, _ = draw(
        tmp_path, "box", pd.DataFrame({"category": ["A"] * 5, "value": [1, 2, 3, 4, 100]})
    )
    np.testing.assert_array_equal(np.unique(ax.patches[0].get_path().vertices[:, 1]), [2, 4])
    np.testing.assert_array_equal(ax.lines[0].get_ydata(), [2, 1])
    np.testing.assert_array_equal(ax.lines[1].get_ydata(), [4, 4])
    np.testing.assert_array_equal(ax.lines[4].get_ydata(), [3, 3])
    np.testing.assert_array_equal(ax.lines[5].get_ydata(), [100])


@pytest.mark.parametrize("kind,center,width", [("violin", 0, 0.35), ("raincloud", 0.08, 0.275)])
def test_gaussian_violin_shape_matches_independent_scipy_scott_reference(
    tmp_path, kind, center, width
):
    values = np.array([1.0, 2, 3, 4, 8])
    _, _, ax, _ = draw(tmp_path, kind, pd.DataFrame({"category": ["A"] * 5, "value": values}))
    vertices = ax.collections[0].get_paths()[0].vertices
    grid = np.unique(vertices[:, 1])
    expected = gaussian_kde(values, bw_method="scott")(grid)
    expected = width * expected / expected.max()
    actual = np.array([vertices[vertices[:, 1] == y, 0].max() - center for y in grid])
    np.testing.assert_allclose(actual, expected, rtol=1e-11, atol=1e-12)
    if kind == "raincloud":
        np.testing.assert_array_equal(ax.collections[-1].get_offsets()[:, 1], values)


@pytest.mark.parametrize("kind", ["box", "violin", "raincloud"])
@pytest.mark.parametrize("values", [[5.0], [5.0, 5.0, 5.0]])
def test_singleton_and_constant_distributions_do_not_invent_measurement_spread(
    tmp_path, kind, values
):
    _, _, ax, _ = draw(
        tmp_path, kind, pd.DataFrame({"category": ["A"] * len(values), "value": values})
    )
    # A visible median/box and optional raw points retain the empirical point mass.
    assert any(np.all(np.asarray(line.get_ydata()) == 5) for line in ax.lines)
    assert all(np.all(p.get_path().vertices[:, 1] == 5) for p in ax.patches)
    for collection in ax.collections:
        if isinstance(collection, PolyCollection):
            for path in collection.get_paths():
                assert np.all(path.vertices[:, 1] == 5)


@pytest.mark.parametrize("complementary", [False, True])
@pytest.mark.parametrize("values", [[1.0, 1.0, 3.0], [5.0]])
def test_ecdf_ties_singleton_and_complement_have_exact_step_endpoints(
    tmp_path, complementary, values
):
    m, _, ax, frame = draw(
        tmp_path, "ecdf", pd.DataFrame({"category": values}), complementary=complementary
    )
    line = ax.lines[0]
    expected = np.array([0, 1 / 3, 2 / 3, 1]) if len(values) == 3 else np.array([0, 1])
    np.testing.assert_array_equal(line.get_xdata(), [values[0], *values])
    np.testing.assert_allclose(line.get_ydata(), 1 - expected if complementary else expected)
    assert line.get_drawstyle() == "steps-post"
    assert f"over {len(values)} observations" in m.describe_figure(frame)


def test_forest_draws_detached_quartiles_and_estimate_without_reflection(tmp_path):
    _, _, ax, _ = draw(
        tmp_path,
        "forest",
        pd.DataFrame({"category": ["A"] * 5, "value": [0, 0, 0, 0, 100]}),
        aggregation="mean",
        uncertainty={"kind": "iqr"},
    )
    centre = next(line for line in ax.lines if line.get_marker() == "o")
    assert centre.get_xdata()[0] == 20
    np.testing.assert_array_equal(ax.lines[0].get_xdata(), [0, 0])
    np.testing.assert_array_equal(ax.lines[0].get_ydata(), [0, 0])


def test_slope_means_do_not_bridge_a_missing_middle_condition(tmp_path):
    data = pd.DataFrame(
        {
            "category": ["first", "first", "last", "middle"],
            "method": ["a", "a", "a", "b"],
            "value": [1, 3, 9, 5],
        }
    )
    _, _, ax, _ = draw(tmp_path, "slope", data, category_order=["first", "middle", "last"])
    lines = {line.get_label(): line for line in ax.lines}
    np.testing.assert_array_equal(lines["a"].get_xdata(), [0, 1, 2])
    np.testing.assert_allclose(lines["a"].get_ydata(), [2, np.nan, 9], equal_nan=True)
    np.testing.assert_allclose(lines["b"].get_ydata(), [np.nan, 5, np.nan], equal_nan=True)


def test_dumbbell_actual_group_means_and_missing_group_do_not_invent_a_dot(tmp_path):
    data = pd.DataFrame(
        {"category": ["A", "A", "A", "B"], "method": ["a", "a", "b", "b"], "value": [1, 3, 7, 9]}
    )
    _, _, ax, _ = draw(tmp_path, "dumbbell", data)
    dots = [
        (float(line.get_xdata()[0]), float(line.get_ydata()[0]))
        for line in ax.lines
        if line.get_marker() == "o"
    ]
    assert dots == [(2, 1), (7, 1), (9, 0)]
    np.testing.assert_array_equal(ax.lines[0].get_xdata(), [2, 7])
    assert len(ax.lines) == 4


@pytest.mark.parametrize(
    "sort,expected",
    [
        ({"by": "value", "direction": "desc"}, ["A", "B"]),
        ({"by": "category", "direction": "asc"}, ["A", "B"]),
    ],
)
def test_dumbbell_requested_sort_controls_actual_rows(tmp_path, sort, expected):
    data = pd.DataFrame(
        {"category": ["B", "B", "A", "A"], "method": ["a", "b", "a", "b"], "value": [1, 2, 8, 9]}
    )
    m, _, ax, frame = draw(tmp_path, "dumbbell", data, sort=sort)
    assert m.category_order(frame) == expected
    assert [t.get_text() for t in ax.get_yticklabels()] == list(reversed(expected))


@pytest.mark.parametrize(
    "normalize,expected",
    [
        ("none", [[3, 1], [2, 4]]),
        ("row", [[0.75, 0.25], [1 / 3, 2 / 3]]),
        ("column", [[0.6, 0.2], [0.4, 0.8]]),
    ],
)
def test_full_confusion_matrix_cells_match_hand_counts_and_normalizations(
    tmp_path, normalize, expected
):
    data = pd.DataFrame(
        {
            "category": ["A", "A", "B", "A", "B"],
            "value": ["A", "A", "A", "B", "B"],
            "weight": [1, 2, 1, 2, 4],
        }
    )
    raw = spec("confusion_matrix")
    raw["normalize"] = normalize
    m = generated(tmp_path, raw)
    _, ax = plt.subplots()
    frame = m.prepare(data)
    m.draw_panel(ax, frame)
    np.testing.assert_allclose(ax.images[0].get_array(), expected)
    assert "70.0% of 10 cases" in m.describe_figure(frame)


def test_waterfall_uses_summed_steps_prefixes_and_final_total_in_description(tmp_path):
    m, _, ax, frame = draw(
        tmp_path,
        "waterfall",
        pd.DataFrame({"category": ["add", "add", "remove"], "value": [2, 3, -1]}),
    )
    np.testing.assert_array_equal([p.get_y() for p in ax.patches], [10, 14, 10])
    np.testing.assert_array_equal([p.get_height() for p in ax.patches], [5, 1, 4])
    description = m.describe_figure(frame).lower()
    assert (
        "start 10" in description
        and "final total 14" in description
        and "add: +5" in description
        and "remove: -1" in description
    )
    assert "mean is" not in description


def test_unknown_waterfall_contribution_is_not_zero(tmp_path):
    m = generated(tmp_path, spec("waterfall"))
    _, ax = plt.subplots()
    with pytest.raises(ValueError, match=r"finite.*contribution"):
        m.draw_panel(
            ax, m.prepare(pd.DataFrame({"category": ["add", "remove"], "value": [3, np.nan]}))
        )


@pytest.mark.parametrize(
    "aggregation,expected",
    [
        ("mean", [[2, 5], [7, np.nan]]),
        ("median", [[2, 5], [7, np.nan]]),
        ("sum", [[4, 5], [7, np.nan]]),
        ("count", [[2, 1], [1, np.nan]]),
    ],
)
def test_heatmap_actual_aggregation_and_unobserved_cell_mask(tmp_path, aggregation, expected):
    data = pd.DataFrame(
        {
            "category": ["A", "A", "B", "A"],
            "value": ["first", "first", "first", "second"],
            "weight": [1, 3, 5, 7],
        }
    )
    raw = spec("heatmap")
    raw["aggregation"] = aggregation
    m = generated(tmp_path, raw)
    _, ax = plt.subplots()
    m.draw_panel(ax, m.prepare(data))
    np.testing.assert_allclose(
        np.ma.filled(ax.images[0].get_array(), np.nan), expected, equal_nan=True
    )
    assert np.ma.getmaskarray(ax.images[0].get_array())[1, 1]


@pytest.mark.parametrize("aggregation", ["sum", "count", "mean", "median"])
def test_unobserved_categorical_levels_never_become_phantom_summary_rows(tmp_path, aggregation):
    m = generated(tmp_path, spec("bar", aggregation=aggregation))
    data = m.prepare(
        pd.DataFrame({"category": pd.Categorical(["A"], categories=["A", "unused"]), "value": [3]})
    )
    summary = m.summarise(data)
    assert summary["category"].tolist() == ["A"]
    assert summary["value"].iloc[0] == (1 if aggregation == "count" else 3)


@pytest.mark.parametrize("kind", ["bar", "table"])
def test_all_missing_sum_is_unknown_while_an_observed_zero_remains_zero(tmp_path, kind):
    m = generated(tmp_path, spec(kind, aggregation="sum"))
    data = m.prepare(pd.DataFrame({"category": ["missing", "zero"], "value": [np.nan, 0]}))
    rows = m.summarise(data).set_index("category")
    assert math.isnan(rows.loc["missing", "value"]) and rows.loc["zero", "value"] == 0


@pytest.mark.parametrize("scale", ["linear", "log"])
def test_sparklines_share_both_actual_axes_and_respect_requested_scale(tmp_path, scale):
    data = pd.DataFrame(
        {"category": [1, 2, 10, 20], "method": ["a", "a", "b", "b"], "value": [1, 2, 10, 20]}
    )
    m, _, ax, frame = draw(
        tmp_path,
        "sparkline_grid",
        data,
        x={"field": "category", "label": "Category", "scale": scale},
        y={"field": "value", "label": "Value", "scale": scale},
    )
    m.decorate_panel(ax, frame, None, True, True)
    first, second = ax.child_axes
    np.testing.assert_array_equal(first.lines[0].get_xdata(), [1, 2])
    np.testing.assert_array_equal(second.lines[0].get_ydata(), [10, 20])
    np.testing.assert_array_equal(first.get_xlim(), second.get_xlim())
    np.testing.assert_array_equal(first.get_ylim(), second.get_ylim())
    assert (
        first.get_xscale() == second.get_xscale() == scale
        and first.get_yscale() == second.get_yscale() == scale
    )
    assert min(first.get_xlim()) <= 1 and max(first.get_xlim()) >= 20
    assert len(first.get_xticks()) == len(second.get_yticks()) == 0
    assert ax.axison and ax.get_xlabel() == "Category" and ax.get_ylabel() == "Value"


@pytest.mark.parametrize(
    "kind",
    [
        "line",
        "scatter",
        "bar",
        "box",
        "violin",
        "ecdf",
        "raincloud",
        "forest",
        "slope",
        "dumbbell",
        "waterfall",
        "sparkline_grid",
        "heatmap",
        "table",
    ],
)
@pytest.mark.parametrize("bad", [float("inf"), "not a measurement"])
def test_invalid_retained_numeric_domains_fail_before_drawing(tmp_path, kind, bad):
    raw = spec(kind)
    if kind in ["bar", "forest", "table"]:
        raw["aggregation"] = "mean"
    m = generated(tmp_path, raw)
    data = pd.DataFrame(
        {
            "category": ["add" if kind == "waterfall" else 1],
            "value": [bad],
            "weight": [bad],
            "method": ["a"],
        }
    )
    if kind == "ecdf":
        data["category"] = [bad]
    if kind in ["heatmap"]:
        data["value"] = ["row"]
    if kind in ["bar", "forest", "table"]:
        # Existing mean/median policy excludes nonfinite values with explicit counts.
        frame = m.prepare(data)
        assert m.summarise(frame)["value"].isna().all()
        m.report_counts(frame)
        assert m.ROW_COUNTS["finite"] == 0
    else:
        with pytest.raises(ValueError, match=r"numeric|finite"):
            m.prepare(data)


@pytest.mark.parametrize("share_x", [False, True])
@pytest.mark.parametrize("share_y", [False, True])
def test_sparkline_child_axes_honor_requested_sharing_across_actual_facets(
    tmp_path, monkeypatch, share_x, share_y
):
    raw = spec(
        "sparkline_grid", facet={"by": "site", "columns": 2, "share_x": share_x, "share_y": share_y}
    )
    m = generated(tmp_path, raw)
    pd.DataFrame(
        {
            "category": [1, 2, 10, 20],
            "value": [1, 2, 10, 20],
            "method": ["a", "a", "b", "b"],
            "site": ["first", "first", "second", "second"],
        }
    ).to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    captured = []
    close = plt.close
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(plt, "close", captured.append)
    try:
        m.main()
        fig = captured[-1]
        first, second = [parent.child_axes[0] for parent in fig.axes]
        assert (first.get_xlim() == second.get_xlim()) == share_x
        assert (first.get_ylim() == second.get_ylim()) == share_y
        for child in [first, second]:
            line = child.lines[0]
            assert min(child.get_xlim()) <= min(line.get_xdata()) and max(child.get_xlim()) >= max(
                line.get_xdata()
            )
            assert min(child.get_ylim()) <= min(line.get_ydata()) and max(child.get_ylim()) >= max(
                line.get_ydata()
            )
    finally:
        monkeypatch.setattr(plt, "close", close)
        for fig in captured:
            if hasattr(fig, "axes"):
                close(fig)


def test_sparkline_requested_explicit_limits_apply_to_actual_children(tmp_path):
    m, _, ax, frame = draw(
        tmp_path,
        "sparkline_grid",
        pd.DataFrame({"category": [1, 2], "value": [2, 3], "method": ["a", "b"]}),
        x={"field": "category", "label": "Category", "limits": [0, 10]},
        y={"field": "value", "label": "Value", "limits": [0, 20]},
    )
    m.decorate_panel(ax, frame, None, True, True)
    for child in ax.child_axes:
        assert child.get_xlim() == (0, 10) and child.get_ylim() == (0, 20)


def test_grouped_table_keeps_observed_all_missing_rows_as_unknown(tmp_path):
    m = generated(tmp_path, spec("table", group="method", aggregation="sum"))
    frame = m.prepare(
        pd.DataFrame(
            {
                "category": ["missing", "zero", "zero"],
                "method": ["a", "a", "b"],
                "value": [np.nan, 0, 2],
            }
        )
    )
    table, low, high = m.build_table(frame)
    assert list(table.index) == ["missing", "zero"] and math.isnan(table.loc["missing", "a"])
    assert m.table_cell(table, low, high, "missing", "a") == "-" and table.loc["zero", "a"] == 0


def test_heatmap_unknown_sum_stays_masked_instead_of_becoming_zero(tmp_path):
    raw = spec("heatmap")
    raw["aggregation"] = "sum"
    m = generated(tmp_path, raw)
    _, ax = plt.subplots()
    frame = m.prepare(
        pd.DataFrame({"category": ["A", "B"], "value": ["row", "row"], "weight": [np.nan, 0]})
    )
    m.draw_panel(ax, frame)
    matrix = m.heatmap_matrix(frame)
    assert math.isnan(matrix.loc["row", "A"]) and matrix.loc["row", "B"] == 0
    assert np.ma.getmaskarray(ax.images[0].get_array()).tolist() == [[True, False]]
    assert "Values run from 0 to 0" in m.describe_figure(frame)


def test_ecdf_missing_values_are_counted_in_actual_x_measurements(tmp_path):
    m, _, ax, frame = draw(tmp_path, "ecdf", pd.DataFrame({"category": [1.0, 2.0, np.nan]}))
    m.report_counts(frame)
    assert m.ROW_COUNTS["measurements"]["category"] == {"finite": 2, "nonfinite": 1}
    np.testing.assert_array_equal(ax.lines[0].get_ydata(), [0, 0.5, 1])
    assert "over 2 observations" in m.describe_figure(frame)


@pytest.mark.parametrize(
    "kind",
    [
        "line",
        "scatter",
        "bar",
        "box",
        "violin",
        "ecdf",
        "raincloud",
        "forest",
        "slope",
        "dumbbell",
        "waterfall",
        "sparkline_grid",
        "heatmap",
        "table",
    ],
)
def test_explicit_filters_run_before_numeric_domain_checks(tmp_path, kind):
    raw = spec(kind, filter=[{"field": "keep", "op": "eq", "value": 1}])
    m = generated(tmp_path, raw)
    data = pd.DataFrame(
        {
            "category": [1, 2],
            "value": [1, "bad"],
            "weight": [1, "bad"],
            "method": ["a", "a"],
            "keep": [1, 0],
        }
    )
    if kind == "ecdf":
        data["category"] = [1, "bad"]
    if kind == "heatmap":
        data["value"] = ["row", "row"]
    assert len(m.prepare(data)) == 1


@pytest.mark.parametrize("kind", ["line", "bar", "forest", "table"])
def test_mean_summary_retains_finite_cleanup_with_independent_sem_and_counts(tmp_path, kind):
    m = generated(tmp_path, spec(kind, aggregation="mean", uncertainty={"kind": "sem"}))
    data = pd.DataFrame({"category": [1] * 3, "value": [float("inf"), 1, 3]})
    frame = m.prepare(data)
    row = m.summarise(frame).iloc[0]
    assert row["value"] == 2 and row["_low"] == 1 and row["_high"] == 3
    m.report_counts(frame)
    assert m.ROW_COUNTS["nonfinite"] == 1 and m.ROW_COUNTS["sample_sizes"] == [2]


@pytest.mark.parametrize("unknown", [np.nan, "absent"])
def test_stacked_means_cannot_treat_unknown_contributions_as_zero(tmp_path, unknown):
    m = generated(tmp_path, spec("bar", aggregation="mean", stacked=True, group="method"))
    _, ax = plt.subplots()
    data = pd.DataFrame(
        {
            "category": ["A", "A", "B", "B"],
            "value": [1, 2, 3, np.nan],
            "method": ["a", "b", "a", "b"],
        }
    )
    if unknown == "absent":
        data = data.iloc[:3]
    with pytest.raises(ValueError, match="known contributions"):
        m.draw_panel(ax, m.prepare(data))


def test_numeric_x_domain_cannot_be_hidden_by_a_shared_mean_y_column(tmp_path):
    m = generated(
        tmp_path, spec("line", aggregation="mean", x={"field": "value", "label": "Value"})
    )
    with pytest.raises(ValueError, match="finite numeric"):
        m.prepare(pd.DataFrame({"value": [float("inf"), 1, 3]}))


@pytest.mark.parametrize("kind", ["line", "bar", "forest", "table", "ecdf"])
def test_strict_all_unknown_numeric_evidence_cannot_pass(tmp_path, kind):
    import json
    import subprocess
    import sys

    raw = spec(kind)
    if kind in ["line", "bar", "forest", "table"]:
        raw["aggregation"] = "mean"
    m = generated(tmp_path, raw)
    data = pd.DataFrame({"category": [np.nan] if kind == "ecdf" else [1], "value": [np.nan]})
    data.to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    process = subprocess.run(
        [sys.executable, m.__file__, "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(process.stdout)
    assert process.returncode in [1, 2] and report["status"] != "passed" and not report["ok"]
    assert report["untested"] or any(f["severity"] == "error" for f in report["findings"])


def test_public_sparkline_reference_matches_input_and_current_emitter():
    import hashlib
    import json
    from pathlib import Path

    from graphunslopify import read_provenance

    root = Path(__file__).resolve().parents[2]
    folder = root / "examples/references"
    raw = json.loads((folder / "sparklines.figure.json").read_text())
    r = local_request("convert", raw)
    assert r["ok"]
    evidence = read_provenance(root / "docs/sparkline-shared-scales.png")
    assert (
        evidence["data_sha256_prefix"]
        == hashlib.sha256((folder / "sparklines.csv").read_bytes()).hexdigest()[:16]
    )
    assert evidence["script_sha256"] == hashlib.sha256(r["code"].encode()).hexdigest()
