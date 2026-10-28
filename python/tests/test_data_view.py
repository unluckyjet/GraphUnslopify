"""Real artist/view measurements and source-selection evidence, not inferred intent."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from types import SimpleNamespace

import matplotlib.pyplot as plt
import numpy as np
import pytest

from graphunslopify import inspect_figure, read_provenance
from graphunslopify.transport import local_request


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


def view(ax):
    report = inspect_figure(ax.figure)
    return report, report.measurements["data_view"][0]


@pytest.mark.parametrize("mark", ["line", "scatter"])
@pytest.mark.parametrize("axis", ["x", "y"])
def test_nonpositive_log_coordinates_are_errors_with_physical_axis_counts(mark, axis):
    _, ax = plt.subplots()
    a, b = [-1, 0, 1, 2], [1, 2, 3, 4]
    xs, ys = (a, b) if axis == "x" else (b, a)
    (ax.plot if mark == "line" else ax.scatter)(xs, ys)
    getattr(ax, f"set_{axis}scale")("log")
    report, measured = view(ax)
    errors = [item for item in report.findings if item.code == "log_domain_hidden"]
    assert len(errors) == 1 and errors[0].severity == "error"
    assert measured["artists"][0][f"nonpositive_{axis}"] == 2
    assert measured["artists"][0]["finite_coordinates"] == 4


@pytest.mark.parametrize("mark", ["line", "scatter"])
@pytest.mark.parametrize("inverted", [False, True])
def test_explicit_cropping_reports_coordinates_without_inventing_lost_sample_counts(mark, inverted):
    _, ax = plt.subplots()
    (ax.plot if mark == "line" else ax.scatter)([1, 2, 3], [1, 2, 50])
    ax.set_ylim((4, 0) if inverted else (0, 4))
    report, measured = view(ax)
    assert any(
        item.code == "data_outside_view" and item.severity == "warning" for item in report.findings
    )
    assert measured["artists"][0]["outside_axes"] == 1
    assert measured["basis"] == "artist_coordinates_not_source_sample_sizes"
    assert measured["y_limits"] == ([4, 0] if inverted else [0, 4])


def test_masked_scatter_rows_are_unavailable_not_observed_outside_points():
    _, ax = plt.subplots()
    ax.scatter([1, 2, 3], [1, np.nan, 2])
    ax.set_ylim(0, 3)
    report, measured = view(ax)
    assert measured["artists"][0]["finite_coordinates"] == 2
    assert measured["artists"][0]["unavailable_coordinates"] == 1
    assert not any(item.code == "data_outside_view" for item in report.findings)


def test_nan_line_gaps_do_not_become_log_domain_errors():
    _, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, np.nan, 3])
    ax.set_yscale("log")
    report, measured = view(ax)
    assert measured["artists"][0]["finite_coordinates"] == 2
    assert not any(item.code == "log_domain_hidden" for item in report.findings)


def test_symlog_keeps_zero_and_negative_values_representable():
    _, ax = plt.subplots()
    ax.plot([-2, 0, 2], [-2, 0, 2])
    ax.set_xscale("symlog")
    ax.set_yscale("symlog")
    report, _ = view(ax)
    assert not any(
        item.code in ("log_domain_hidden", "data_outside_view") for item in report.findings
    )


def test_clip_disabled_data_has_no_axes_clipping_claim():
    _, ax = plt.subplots()
    ax.scatter([1, 2, 3], [1, 2, 50], clip_on=False)
    ax.set_ylim(0, 4)
    report, measured = view(ax)
    assert not measured["artists"][0]["clip_on"]
    assert not any(item.code == "data_outside_view" for item in report.findings)


def test_blended_transform_reference_lines_are_not_counted_as_source_data():
    _, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 2, 3])
    ax.axhline(500)
    ax.set_ylim(0, 4)
    report, measured = view(ax)
    assert len(measured["artists"]) == 1
    assert not any(item.code == "data_outside_view" for item in report.findings)


def test_disclosed_axis_break_keeps_outside_counts_without_treating_each_half_as_censorship():
    _, ax = plt.subplots()
    ax.set_label("<axis-break>")
    ax.plot([1, 2, 3], [1, 2, 50])
    ax.set_ylim(0, 4)
    report, measured = view(ax)
    assert measured["scope"] == "intentional_axis_break"
    assert measured["artists"][0]["outside_axes"] == 1
    assert not any(item.code == "data_outside_view" for item in report.findings)


def test_log_uncertainty_polygon_cannot_hide_nonpositive_endpoints():
    _, ax = plt.subplots()
    ax.plot([1, 2], [1, 2])
    ax.fill_between([1, 2], [-1, 0.5], [2, 3])
    ax.set_yscale("log")
    report, measured = view(ax)
    assert any(item["kind"] == "polygon" and item["nonpositive_y"] for item in measured["artists"])
    assert any(item.code == "log_domain_hidden" for item in report.findings)


def test_errorbar_segment_endpoints_are_checked_not_only_the_center():
    _, ax = plt.subplots()
    ax.errorbar([1, 2], [1, 2], yerr=[2, 0.1])
    ax.set_yscale("log")
    report, measured = view(ax)
    assert any(item["kind"] == "segments" and item["nonpositive_y"] for item in measured["artists"])
    assert any(item.code == "log_domain_hidden" for item in report.findings)


def generated(folder, csv="x,y,cohort\n1,1,a\n2,2,b\n3,50,a\n4,4,b\n", **extra):
    (folder / "data.csv").write_text(csv)
    spec = {
        "kind": "scatter",
        "data": {"path": str(folder / "data.csv")},
        "x": {"field": "x", "label": "Input"},
        "y": {"field": "y", "label": "Value"},
        "legend": {"show": False},
        "output": {"formats": ["png", "svg"], "dpi": 300},
        **extra,
    }
    result = local_request("convert", spec)
    assert result.get("ok"), result
    path = folder / "figure.py"
    path.write_text(result["code"])
    return path


def run(path, *flags):
    result = subprocess.run(
        [sys.executable, str(path), "--json", *flags],
        cwd=path.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, json.loads(result.stdout)


def test_real_strict_log_figure_rejects_the_previous_silent_hidden_value(tmp_path):
    path = generated(
        tmp_path, csv="x,y\n1,-1\n2,1\n3,2\n", y={"field": "y", "label": "Value", "scale": "log"}
    )
    code, report = run(path)
    assert code == 2 and report["status"] == "failed", report
    assert any(item["code"] == "log_domain_hidden" for item in report["findings"])
    assert {item["format"] for item in report["outputs"]} == {"png", "svg"}


def test_real_crop_warns_and_fail_on_warning_can_require_review(tmp_path):
    path = generated(tmp_path, y={"field": "y", "label": "Value", "limits": [0, 5]})
    code, report = run(path)
    assert code == 0 and report["status"] == "passed", report
    assert any(item["code"] == "data_outside_view" for item in report["findings"])
    assert report["inspection"]["measurements"]["data_view"][0]["artists"][0]["outside_axes"] == 1
    assert run(path, "--fail-on-warning")[0] == 2
    assert "Value view is limited to 0 through 5" in report["alt_text"]
    assert "summary statistics describe retained data" in report["alt_text"]
    assert read_provenance(tmp_path / "figure.png")["alt_text"] == report["alt_text"]


def test_each_declared_filter_has_counts_and_alt_text_discloses_total_selection(tmp_path):
    path = generated(
        tmp_path,
        filter=[
            {"field": "cohort", "op": "eq", "value": "a"},
            {"field": "y", "op": "lt", "value": 10},
        ],
    )
    code, report = run(path)
    assert code == 0, report
    selection = report["data"]["counts"]["filtering"]
    assert (selection["source_rows"], selection["retained_rows"], selection["removed_rows"]) == (
        4,
        1,
        3,
    )
    assert [(item["before"], item["after"], item["removed"]) for item in selection["steps"]] == [
        (4, 2, 2),
        (2, 1, 1),
    ]
    assert "Selected 1 of 4 source rows; 3 excluded by declared filters." in report["alt_text"]
    assert not any(item["code"] == "data_outside_view" for item in report["findings"])


def test_zero_retained_rows_preserve_selection_evidence_and_fail(tmp_path):
    path = generated(tmp_path, filter=[{"field": "y", "op": "gt", "value": 1000}])
    code, report = run(path)
    assert code == 1 and report["status"] == "failed", report
    assert report["data"]["counts"]["filtering"]["removed_rows"] == 4
    assert not report["outputs"]


def test_noop_filter_does_not_invent_excluded_rows(tmp_path):
    path = generated(tmp_path, filter=[{"field": "y", "op": "gt", "value": 0}])
    code, report = run(path)
    assert code == 0, report
    assert report["data"]["counts"]["filtering"]["removed_rows"] == 0
    assert "excluded by declared filters" not in report["alt_text"]


def test_new_program_does_not_certify_visibility_using_an_older_export_width_checker(
    tmp_path, monkeypatch
):
    path = generated(tmp_path)
    definition = importlib.util.spec_from_file_location("old_visibility_check", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    fake = SimpleNamespace(measurements={"basis": "exports"}, ok=True, findings=[])
    monkeypatch.setattr("graphunslopify.inspect_figure", lambda *args, **kwargs: fake)
    assert not module.check(plt.figure())
    assert not module.RUN_REPORT["inspection"]["checked"]
    assert any(item["code"] == "inspection_outdated" for item in module.RUN_REPORT["findings"])


def test_unused_polygon_closing_vertex_is_not_an_observed_log_coordinate():
    from matplotlib.collections import PolyCollection

    _, ax = plt.subplots()
    polygon = PolyCollection([[(1, 1), (2, 2), (3, 1)]])
    polygon.get_paths()[0].vertices[-1] = [0, 0]  # CLOSEPOLY ignores this placeholder.
    ax.add_collection(polygon)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(0.8, 4)
    ax.set_ylim(0.8, 3)
    report, measured = view(ax)
    assert measured["artists"][0]["finite_coordinates"] == 3
    assert not any(item.code == "log_domain_hidden" for item in report.findings)


@pytest.mark.parametrize("mark", ["line", "scatter"])
def test_fully_transparent_artist_is_not_counted_as_visible_data(mark):
    _, ax = plt.subplots()
    (ax.plot if mark == "line" else ax.scatter)([-1, 1], [1, 2], alpha=0)
    ax.set_xscale("log")
    report, measured = view(ax)
    assert not measured["artists"]
    assert not any(item.code == "log_domain_hidden" for item in report.findings)


def test_masked_rows_do_not_invent_dense_marker_ink():
    _, ax = plt.subplots()
    ax.scatter(np.arange(1000), [1, 2] + [np.nan] * 998, s=400)
    report, _ = view(ax)
    assert not any(item.code == "overplotting" for item in report.findings)


def test_off_view_centers_do_not_invent_visible_overplotting():
    _, ax = plt.subplots()
    ax.scatter([0.5] + [1000] * 999, [0.5] + [1000] * 999, s=400)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    report, _ = view(ax)
    assert any(item.code == "data_outside_view" for item in report.findings)
    assert not any(item.code == "overplotting" for item in report.findings)


def test_multi_panel_filter_disclosure_uses_one_source_denominator(tmp_path):
    path = generated(
        tmp_path, filter=[{"field": "y", "op": "lt", "value": 10}], facet={"by": "cohort"}
    )
    code, report = run(path)
    assert code == 0, report
    assert report["alt_text"].count("Selected 3 of 4 source rows; 1 excluded") == 1
    assert len(report["panels"]) == 2


def test_continuous_x_zoom_receives_the_same_review_as_a_y_zoom():
    _, ax = plt.subplots()
    ax.plot([99.90, 99.93, 99.95], [1, 2, 3])
    ax.set_xlim(99.89, 99.96)
    report, _ = view(ax)
    assert any(
        item.code == "axis_exaggeration" and "the x axis" in item.message
        for item in report.findings
    )


def test_calendar_origin_is_not_used_to_claim_x_zoom_exaggeration():
    from datetime import datetime, timedelta

    _, ax = plt.subplots()
    dates = [datetime(2026, 10, 1) + timedelta(days=n) for n in range(3)]
    ax.plot(dates, [1, 2, 3])
    report, _ = view(ax)
    assert not any(
        item.code == "axis_exaggeration" and "the x axis" in item.message
        for item in report.findings
    )
