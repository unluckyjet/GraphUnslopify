"""Annotation evidence follows actual primary marks and refuses invented anchors."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from jsonschema import validate

from graphunslopify.transport import local_request

BASE = {
    "kind": "line",
    "x": {"field": "x", "label": "Input"},
    "y": {"field": "y", "label": "Score"},
    "legend": {"show": False},
    "output": {"formats": ["png", "svg"], "dpi": 300},
    "annotate": [{"at": "max", "text": "Peak"}],
}


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


def generated(folder, **extra):
    spec = {**BASE, "data": {"path": str(folder / "data.csv")}, **extra}
    result = local_request("convert", spec)
    assert result.get("ok"), result
    path = folder / "figure.py"
    path.write_text(result["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("annotation_reference", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module, path


def draw(module, frame):
    frame = module.prepare(frame)
    _, ax = plt.subplots()
    module.draw_panel(ax, frame)
    module.decorate_panel(ax, frame, None)
    return ax, module.RUN_REPORT["annotations"]


def rendered(path, frame, *args):
    frame.to_csv(path.parent / "data.csv", index=False)
    p = subprocess.run(
        [sys.executable, str(path), "--json", *args],
        cwd=path.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    result = json.loads(p.stdout)
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/runtime-report.schema.json").read_text()
    )
    validate(result, schema)
    return p, result


@pytest.mark.parametrize(("aggregation", "expected"), [("mean", (2, 70)), ("median", (2, 60))])
def test_summary_peak_is_an_actual_drawn_value_not_a_raw_outlier(tmp_path, aggregation, expected):
    module, _ = generated(tmp_path, aggregation=aggregation)
    data = pd.DataFrame({"x": [1, 1, 1, 2, 2, 2], "y": [0, 0, 100, 50, 60, 100]})
    ax, records = draw(module, data)
    if aggregation == "mean":
        expected = (2, 70)
    assert tuple(ax.texts[0].xy) == expected
    assert expected in list(zip(ax.lines[0].get_xdata(), ax.lines[0].get_ydata(), strict=True))
    assert records[0]["status"] == "resolved" and not records[0]["text_verified"]


def test_smoothing_uses_primary_curve_instead_of_the_faint_unsmoothed_trace(tmp_path):
    module, _ = generated(tmp_path, smooth={"kind": "rolling", "window": 2, "show_raw": True})
    data = pd.DataFrame({"x": [1, 2, 3], "y": [0, 100, 10]})
    ax, _ = draw(module, data)
    expected = max(
        zip(ax.lines[1].get_xdata(), ax.lines[1].get_ydata(), strict=True), key=lambda p: p[1]
    )
    assert tuple(ax.texts[0].xy) == expected
    assert ax.texts[0].xy[1] != 100


def test_unsorted_line_endpoints_follow_the_drawn_order(tmp_path):
    module, _ = generated(tmp_path, sort_x=False, annotate=[{"at": "first", "text": "Start"}])
    ax, _ = draw(module, pd.DataFrame({"x": [3, 1, 2], "y": [30, 10, 20]}))
    assert tuple(ax.texts[0].xy) == (3, 30)


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
def test_bar_order_and_orientation_match_actual_patch_endpoint(tmp_path, orientation):
    module, _ = generated(
        tmp_path,
        kind="bar",
        aggregation="mean",
        orientation=orientation,
        category_order=["B", "A"],
        annotate=[{"at": {"x": "A"}, "text": "A"}],
    )
    ax, records = draw(module, pd.DataFrame({"x": ["A", "A", "B", "B"], "y": [2, 4, 6, 8]}))
    patch = ax.containers[0].patches[1]
    expected = (
        (patch.get_x() + patch.get_width(), patch.get_y() + patch.get_height() / 2)
        if orientation == "horizontal"
        else (patch.get_x() + patch.get_width() / 2, patch.get_y() + patch.get_height())
    )
    np.testing.assert_allclose(ax.texts[-1].xy, expected)
    assert records[0]["resolved"]["key"] == "A" and records[0]["resolved"]["value"] == 3


def test_grouped_bar_anchor_contains_the_actual_group_offset(tmp_path):
    module, _ = generated(
        tmp_path,
        kind="bar",
        group="model",
        aggregation="mean",
        annotate=[{"at": "max", "series": "new", "text": "New"}],
    )
    ax, _ = draw(
        module,
        pd.DataFrame({"x": ["A", "A", "B", "B"], "y": [1, 2, 3, 8], "model": ["base", "new"] * 2}),
    )
    patch = next(c for c in ax.containers if c.get_label() == "new").patches[1]
    assert tuple(ax.texts[-1].xy) == (
        patch.get_x() + patch.get_width() / 2,
        patch.get_y() + patch.get_height(),
    )


def test_stacked_bar_value_and_physical_endpoint_are_separate(tmp_path):
    module, _ = generated(
        tmp_path,
        kind="bar",
        group="model",
        aggregation="mean",
        stacked=True,
        annotate=[{"at": "max", "series": "new", "text": "Contribution"}],
    )
    ax, records = draw(
        module, pd.DataFrame({"x": ["A", "A"], "y": [10, 3], "model": ["base", "new"]})
    )
    assert ax.texts[-1].xy[1] == 13
    assert records[0]["resolved"]["value"] == 3


def test_literal_category_named_max_is_not_treated_as_the_maximum_selector(tmp_path):
    module, _ = generated(
        tmp_path,
        kind="bar",
        aggregation="mean",
        annotate=[{"at": {"x": "max"}, "text": "Literal category"}],
    )
    _, records = draw(module, pd.DataFrame({"x": ["max", "other"], "y": [2, 99]}))
    assert records[0]["resolved"]["key"] == "max" and records[0]["resolved"]["value"] == 2


@pytest.mark.parametrize("target", [100, -100])
def test_out_of_domain_coordinates_are_incomplete_without_silent_extrapolation(tmp_path, target):
    _, path = generated(tmp_path, annotate=[{"at": {"x": target}, "text": "Requested"}])
    run, report = rendered(path, pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 3]}))
    assert run.returncode == 2 and report["status"] == "incomplete", report
    assert report["annotations"][0]["status"] == "untested"
    assert "outside the observed domain" in report["annotations"][0]["reason"]
    assert report["outputs"] and not any(f["code"] == "runtime_error" for f in report["findings"])


def test_nearest_unique_in_domain_point_is_disclosed_and_can_require_review(tmp_path):
    _, path = generated(tmp_path, annotate=[{"at": {"x": 1.1}, "text": "Nearby"}])
    data = pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 3]})
    run, report = rendered(path, data)
    assert run.returncode == 0, report
    assert report["annotations"][0]["snapped"]
    assert report["annotations"][0]["resolved"]["x"] == 1
    assert any(f["code"] == "annotation_snapped_to_observation" for f in report["findings"])
    assert rendered(path, data, "--fail-on-warning")[0].returncode == 2


def test_ambiguous_duplicate_x_is_not_arbitrarily_picked(tmp_path):
    _, path = generated(tmp_path, kind="scatter", annotate=[{"at": {"x": 1}, "text": "Which?"}])
    run, report = rendered(path, pd.DataFrame({"x": [1, 1, 2], "y": [1, 3, 2]}))
    assert run.returncode == 2 and report["status"] == "incomplete", report
    assert "multiple possible" in report["annotations"][0]["reason"]


def test_absent_series_in_a_facet_cannot_silently_drop_its_requested_label(tmp_path):
    _, path = generated(
        tmp_path,
        kind="scatter",
        group="model",
        facet={"by": "panel"},
        annotate=[{"at": "max", "series": "new", "text": "New"}],
    )
    data = pd.DataFrame(
        {
            "x": [1, 2, 1, 2],
            "y": [1, 2, 3, 4],
            "model": ["base"] * 2 + ["new"] * 2,
            "panel": ["A"] * 2 + ["B"] * 2,
        }
    )
    run, report = rendered(path, data)
    assert run.returncode == 2 and report["status"] == "incomplete", report
    assert {r["status"] for r in report["annotations"]} == {"resolved", "untested"}


def test_off_view_resolved_anchor_is_incomplete(tmp_path):
    _, path = generated(tmp_path, y={"field": "y", "label": "Score", "limits": [0, 5]})
    run, report = rendered(path, pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 50]}))
    assert run.returncode == 2 and report["status"] == "incomplete", report
    assert "outside this rendered view" in report["annotations"][0]["reason"]


def test_date_targets_use_actual_converted_coordinates_and_report_the_date(tmp_path):
    module, _ = generated(
        tmp_path,
        x={"field": "x", "label": "Date", "temporal": True},
        annotate=[{"at": {"x": "2026-10-02"}, "text": "Date"}],
    )
    ax, records = draw(
        module, pd.DataFrame({"x": pd.to_datetime(["2026-10-01", "2026-10-02"]), "y": [1, 2]})
    )
    assert ax.texts[-1].xy[0] == mdates.date2num(pd.Timestamp("2026-10-02"))
    assert records[0]["resolved"]["date"].startswith("2026-10-02")


def test_no_observed_crossover_does_not_fabricate_one_at_the_first_point(tmp_path):
    _, path = generated(
        tmp_path, group="model", annotate=[{"at": "crossover", "series": "new", "text": "Crosses"}]
    )
    data = pd.DataFrame({"x": [1, 2, 1, 2], "y": [1, 2, 3, 4], "model": ["base"] * 2 + ["new"] * 2})
    run, report = rendered(path, data)
    assert run.returncode == 2 and report["status"] == "incomplete", report
    assert "no observed transition" in report["annotations"][0]["reason"]


def test_real_crossover_uses_complete_rendered_series_values(tmp_path):
    module, _ = generated(
        tmp_path,
        group="model",
        aggregation="mean",
        annotate=[{"at": "crossover", "series": "new", "text": "Crosses"}],
    )
    ax, records = draw(
        module,
        pd.DataFrame({"x": [1, 2, 1, 2], "y": [3, 2, 1, 4], "model": ["base"] * 2 + ["new"] * 2}),
    )
    assert tuple(ax.texts[-1].xy) == (2, 4)
    assert records[0]["status"] == "resolved"


def test_keyword_series_names_do_not_confuse_faint_and_primary_curves(tmp_path):
    module, _ = generated(
        tmp_path,
        group="model",
        smooth={"kind": "rolling", "window": 2},
        annotate=[{"at": "max", "series": "_child0", "text": "Primary"}],
    )
    ax, record = draw(
        module, pd.DataFrame({"x": [1, 2, 3], "y": [0, 100, 10], "model": ["_child0"] * 3})
    )
    assert ax.texts[-1].xy[1] < 100
    assert record[0]["resolved"]["basis"] == "rendered_curve"


def test_one_visible_axis_break_region_satisfies_the_requested_anchor(tmp_path):
    _, path = generated(tmp_path, axis_break={"axis": "y", "from": 5, "to": 20})
    run, report = rendered(path, pd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 30]}))
    assert run.returncode == 0, report
    assert any(r["status"] == "resolved" for r in report["annotations"])
    assert not any(f["code"] == "annotation_unavailable" for f in report["findings"])


def test_matrix_maximum_uses_the_actual_cell_value_and_remains_readable(tmp_path):
    _, path = generated(
        tmp_path, kind="heatmap", value="weight", value_label="Count", annotate_cells=False
    )
    run, report = rendered(
        path,
        pd.DataFrame(
            {"x": ["A", "A", "B", "B"], "y": ["R1", "R2", "R1", "R2"], "weight": [1, 9, 2, 3]}
        ),
    )
    assert run.returncode == 0, report
    point = report["annotations"][0]["resolved"]
    assert (point["x"], point["y"], point["value"]) == (0, 1, 9)
    assert point["basis"] == "rendered_cell_value"


def test_confusion_matrix_anchors_report_normalized_instead_of_raw_counts(tmp_path):
    module, _ = generated(
        tmp_path, kind="confusion_matrix", value="weight", normalize="row", annotate_cells=False
    )
    ax, records = draw(
        module,
        pd.DataFrame(
            {"x": ["A", "B", "A", "B"], "y": ["A", "A", "B", "B"], "weight": [90, 10, 1, 9]}
        ),
    )
    point = records[0]["resolved"]
    assert point["value"] == pytest.approx(0.9)
    assert ax.images[0].get_array()[int(point["y"]), int(point["x"])] == point["value"]


def test_forest_peak_uses_the_center_and_physical_category_row(tmp_path):
    module, _ = generated(tmp_path, kind="forest", aggregation="mean", uncertainty={"kind": "sem"})
    ax, records = draw(module, pd.DataFrame({"x": ["A", "A", "B", "B"], "y": [1, 3, 4, 8]}))
    assert tuple(ax.texts[-1].xy) == (6, 0)
    assert records[0]["resolved"]["key"] == "B"


def test_paired_peak_uses_matched_differences_instead_of_raw_scores(tmp_path):
    module, _ = generated(tmp_path, kind="paired_difference", pair="unit", baseline="base")
    ax, records = draw(
        module,
        pd.DataFrame(
            {"unit": ["A", "A", "B", "B"], "x": ["base", "new"] * 2, "y": [10, 14, 20, 26]}
        ),
    )
    expected = max(ax.collections[0].get_offsets(), key=lambda point: point[1])
    np.testing.assert_allclose(ax.texts[-1].xy, expected)
    assert records[0]["resolved"]["key"] == "new"
    assert records[0]["resolved"]["value"] == 6


def test_waterfall_signed_contribution_and_running_endpoint_are_distinct(tmp_path):
    module, _ = generated(
        tmp_path,
        kind="waterfall",
        start=10,
        category_order=["add", "remove"],
        annotate=[{"at": {"x": "remove"}, "text": "Removed"}],
    )
    ax, records = draw(module, pd.DataFrame({"x": ["add", "remove"], "y": [4, -3]}))
    assert tuple(ax.texts[-1].xy) == (1, 11)
    assert records[0]["resolved"]["value"] == -3


def test_sparkline_anchor_belongs_to_the_requested_child_axes(tmp_path):
    module, _ = generated(
        tmp_path,
        kind="sparkline_grid",
        group="model",
        annotate=[{"at": "max", "series": "new", "text": "New"}],
    )
    ax, records = draw(
        module,
        pd.DataFrame({"x": [1, 2, 1, 2], "y": [1, 2, 3, 8], "model": ["base"] * 2 + ["new"] * 2}),
    )
    assert not ax.texts
    assert tuple(ax.child_axes[1].texts[-1].xy) == (2, 8)
    assert records[0]["status"] == "resolved"


def test_scaling_peak_uses_displayed_observations_instead_of_fitted_values(tmp_path):
    module, _ = generated(
        tmp_path,
        kind="scaling_fit",
        show_points=True,
        interval="none",
        x={"field": "x", "label": "Scale", "scale": "log"},
        y={"field": "y", "label": "Response", "scale": "log"},
    )
    ax, records = draw(module, pd.DataFrame({"x": [1, 10, 100], "y": [1, 10, 1000]}))
    expected = max(ax.collections[0].get_offsets(), key=lambda p: p[1])
    np.testing.assert_allclose(ax.texts[-1].xy, expected)
    assert records[0]["resolved"]["basis"] == "rendered_observation"
    assert records[0]["resolved"]["value"] == 1000


def test_category_with_multiple_distribution_anchors_does_not_pick_an_arbitrary_endpoint(tmp_path):
    _, path = generated(tmp_path, kind="box", annotate=[{"at": "first", "text": "Which?"}])
    run, report = rendered(path, pd.DataFrame({"x": ["A"] * 4, "y": [1, 2, 3, 4]}))
    assert run.returncode == 2 and report["status"] == "incomplete", report
    assert "multiple possible" in report["annotations"][0]["reason"]


def test_an_equidistant_nearest_point_is_ambiguous(tmp_path):
    _, path = generated(tmp_path, annotate=[{"at": {"x": 1.5}, "text": "Between"}])
    run, report = rendered(path, pd.DataFrame({"x": [1, 2], "y": [1, 2]}))
    assert run.returncode == 2 and report["status"] == "incomplete", report
    assert "multiple possible" in report["annotations"][0]["reason"]


def test_hidden_category_tick_labels_do_not_erase_the_logical_anchor(tmp_path):
    module, _ = generated(
        tmp_path, kind="bar", aggregation="mean", annotate=[{"at": {"x": "B"}, "text": "B"}]
    )
    frame = module.prepare(pd.DataFrame({"x": ["A", "B"], "y": [1, 3]}))
    _, ax = plt.subplots()
    ax.tick_params(axis="x", labelbottom=False)
    module.draw_panel(ax, frame)
    module.decorate_panel(ax, frame, None, show_x=False)
    assert not ax.get_xticklabels()
    point = module.RUN_REPORT["annotations"][0]["resolved"]
    assert (point["x"], point["key"], point["value"]) == (1, "B", 3)
