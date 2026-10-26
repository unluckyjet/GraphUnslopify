"""Known log-space parameters, real artists and explicit unavailable uncertainty."""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from graphunslopify import read_provenance
from graphunslopify.transport import local_request

BASE = {
    "kind": "scaling_fit",
    "x": {"field": "scale", "label": "Scale", "scale": "log"},
    "y": {"field": "loss", "label": "Loss", "scale": "log"},
    "legend": {"show": False},
    "output": {"stem": "scaling", "formats": ["png", "svg"], "dpi": 100},
}


def test_published_scaling_image_matches_committed_data_and_current_emitter():
    root = Path(__file__).resolve().parents[2]
    folder = root / "examples/references"
    spec = json.loads((folder / "scaling.figure.json").read_text())
    result = local_request("convert", spec)
    assert result["ok"], result
    evidence = read_provenance(root / "docs/seventh-pass-scaling-fit.png")
    assert (
        evidence["data_sha256_prefix"]
        == hashlib.sha256((folder / "scaling.csv").read_bytes()).hexdigest()[:16]
    )
    assert evidence["script_sha256"] == hashlib.sha256(result["code"].encode("utf8")).hexdigest()
    assert evidence["spec"]["interval"] == "t95"
    assert "12 observations" in evidence["alt_text"] and "Student-t" in evidence["alt_text"]


def sample():
    return pd.DataFrame({"scale": [1.0, 10, 100], "loss": [1.0, 10, 1000]})


def generated(folder, **extra):
    spec = {**BASE, "data": {"path": str(folder / "data.csv")}, **extra}
    if extra.get("group") and "legend" not in extra:
        spec["legend"] = {"position": "outside_bottom"}
    result = local_request("convert", spec)
    assert result.get("ok"), result
    path = folder / "scaling.py"
    path.write_text(result["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("scaling_reference", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module, path


@pytest.fixture(scope="module")
def emitted(tmp_path_factory):
    return generated(tmp_path_factory.mktemp("scaling-reference"), interval="none")[0]


def test_hand_log_parameters_errors_and_actual_curve_are_consistent(emitted):
    fit = emitted.scaling_estimate(sample())
    assert fit["observations"] == 3 and fit["df"] == 1
    assert fit["slope"] == pytest.approx(1.5, rel=0, abs=1e-12)
    assert fit["intercept"] == pytest.approx(-1 / 6, rel=0, abs=1e-12)
    assert fit["stderr"] == pytest.approx(math.sqrt(1 / 12), rel=0, abs=1e-12)
    assert fit["residual_se"] == pytest.approx(math.sqrt(1 / 6), rel=0, abs=1e-12)
    assert fit["interval"]["status"] == "not_requested"
    fig, ax = plt.subplots()
    try:
        emitted.draw_panel(ax, sample())
        points = np.asarray(ax.collections[0].get_offsets(), dtype=float)
        np.testing.assert_array_equal(points, sample().to_numpy())
        x, y = ax.lines[0].get_xdata(), ax.lines[0].get_ydata()
        assert len(x) == 100 and x[0] == 1 and x[-1] == 100
        np.testing.assert_allclose(np.log10(y), -1 / 6 + 1.5 * np.log10(x), rtol=0, atol=1e-12)
    finally:
        plt.close(fig)


def test_three_point_t_interval_matches_independent_cauchy_quantile(tmp_path):
    pytest.importorskip("scipy.stats")
    module, _ = generated(tmp_path)
    fit = module.scaling_estimate(sample())
    critical = math.tan(0.475 * math.pi)  # Student-t(df=1) is standard Cauchy.
    margin = critical * math.sqrt(1 / 12)
    assert fit["interval"]["method"] == "student_t" and fit["interval"]["level"] == 0.95
    np.testing.assert_allclose(
        [fit["interval"]["low"], fit["interval"]["high"]],
        [1.5 - margin, 1.5 + margin],
        rtol=0,
        atol=1e-10,
    )
    assert margin > 6 * 1.96 * fit["stderr"]


@pytest.mark.parametrize("size", [3, 5, 20])
def test_parameters_and_interval_match_independent_scipy_regression(tmp_path, size):
    stats = pytest.importorskip("scipy.stats")
    rng = np.random.default_rng(24)
    log_x = np.linspace(-2, 3, size)
    log_y = 0.3 - 0.7 * log_x + rng.normal(0, 0.1, size)
    reference = stats.linregress(log_x, log_y)
    module, _ = generated(tmp_path)
    fit = module.scaling_estimate(pd.DataFrame({"scale": 10**log_x, "loss": 10**log_y}))
    np.testing.assert_allclose(
        [fit["slope"], fit["intercept"], fit["stderr"]],
        [reference.slope, reference.intercept, reference.stderr],
        rtol=0,
        atol=1e-12,
    )
    margin = stats.t.ppf(0.975, size - 2) * reference.stderr
    np.testing.assert_allclose(
        [fit["interval"]["low"], fit["interval"]["high"]],
        [reference.slope - margin, reference.slope + margin],
        rtol=0,
        atol=1e-10,
    )


def test_row_permutations_preserve_parameters_and_leave_input_unchanged(emitted):
    rows = pd.DataFrame({"scale": [10.0, 1, 100, 1000], "loss": [10.0, 2, 50, 400]})
    before = rows.copy(deep=True)
    reference = emitted.scaling_estimate(rows)
    for order in itertools.permutations(range(4)):
        fit = emitted.scaling_estimate(rows.iloc[list(order)])
        assert [fit[key] for key in ["slope", "intercept", "stderr"]] == [
            reference[key] for key in ["slope", "intercept", "stderr"]
        ]
        np.testing.assert_array_equal(fit["grid_y"], reference["grid_y"])
    pd.testing.assert_frame_equal(rows, before)


@pytest.mark.parametrize(
    ("field", "value"),
    [(field, value) for field in ["scale", "loss"] for value in [0, -1, np.nan, np.inf, "bad"]],
)
def test_invalid_retained_values_fail_instead_of_being_silently_dropped(emitted, field, value):
    rows = sample().astype(object)
    rows.loc[0, field] = value
    with pytest.raises(ValueError, match="Scaling"):
        emitted.prepare(rows)
    fig, ax = plt.subplots()
    try:
        with pytest.raises(ValueError, match="Scaling"):
            emitted.draw_panel(ax, rows)
    finally:
        plt.close(fig)


@pytest.mark.parametrize(
    "rows",
    [
        pd.DataFrame({"scale": [], "loss": []}),
        sample().iloc[:1],
        sample().drop(columns="scale"),
        sample().assign(scale=1),
        pd.DataFrame({"scale": [1e300, np.nextafter(1e300, np.inf)], "loss": [1, 2]}),
    ],
)
def test_unidentifiable_or_unrepresentable_designs_have_no_fit(emitted, rows):
    with pytest.raises(ValueError, match="Scaling"):
        emitted.scaling_estimate(rows)


@pytest.mark.parametrize("values", [[1e308, 1e308, 1e308, 1e-308], [1e-308, 1e-308, 1e-308, 1e308]])
def test_overflow_or_underflow_of_fitted_values_is_explicit(emitted, values):
    with pytest.raises(ValueError, match="Scaling"):
        emitted.scaling_estimate(pd.DataFrame({"scale": [1, 10, 100, 1000], "loss": values}))


def test_constant_response_has_zero_slope_and_unknown_r_squared(emitted):
    fit = emitted.scaling_estimate(sample().assign(loss=3))
    assert fit["slope"] == 0 and fit["stderr"] == 0
    assert fit["r_squared"] is None and fit["constant_response"]
    np.testing.assert_allclose(fit["grid_y"], 3, rtol=0, atol=1e-12)
    assert "constant" in emitted.alt_text(sample().assign(loss=3)).lower()


def test_filtering_runs_before_positive_domain_validation(tmp_path):
    module, _ = generated(
        tmp_path, interval="none", filter=[{"field": "keep", "op": "eq", "value": 1}]
    )
    rows = pd.concat(
        [sample().assign(keep=1), pd.DataFrame({"scale": [-1], "loss": [100], "keep": [0]})]
    )
    prepared = module.prepare(rows)
    assert module.scaling_estimate(prepared)["observations"] == 3


def test_numeric_strings_and_supported_transform_are_validated_after_preparation(tmp_path):
    module, _ = generated(tmp_path, interval="none", transform={"kind": "cumulative"})
    rows = module.prepare(pd.DataFrame({"scale": ["1", "2", "4"], "loss": ["1", "1", "2"]}))
    np.testing.assert_array_equal(rows["loss"], [1, 2, 4])
    assert module.scaling_estimate(rows)["slope"] == pytest.approx(1, rel=0, abs=1e-12)


def test_transform_cannot_create_invalid_fit_values_silently(tmp_path):
    module, _ = generated(
        tmp_path,
        interval="none",
        group="model",
        transform={"kind": "delta_vs_baseline", "baseline": "base"},
    )
    rows = pd.concat(
        [sample().assign(model="base"), sample().assign(model="ours", loss=lambda f: f["loss"] / 2)]
    )
    with pytest.raises(ValueError, match="Scaling"):
        module.prepare(rows)


def rendered(folder, rows, block_scipy=False, **extra):
    _, path = generated(folder, **extra)
    rows.to_csv(folder / "data.csv", index=False)
    if block_scipy:
        driver = "import sys,runpy;sys.modules['scipy']=None;sys.modules['scipy.stats']=None;sys.argv=sys.argv[1:];runpy.run_path(sys.argv[0],run_name='__main__')"
        command = [sys.executable, "-c", driver, str(path), "--strict", "--json"]
    else:
        command = [sys.executable, str(path), "--strict", "--json"]
    process = subprocess.run(command, cwd=folder, capture_output=True, text=True, check=False)
    report = json.loads(process.stdout)
    assert report["exit_code"] == process.returncode, process.stderr
    return process, report


def test_two_points_draw_an_identified_curve_with_unknown_requested_interval(tmp_path):
    process, report = rendered(
        tmp_path, pd.DataFrame({"scale": [1, 2], "loss": [3, 6]}), show_points=False
    )
    assert process.returncode == 2 and report["status"] == "incomplete" and report["outputs"]
    fit = report["data"]["counts"]["scaling_fits"][0]
    assert fit["df"] == 0 and fit["stderr"] is None and fit["interval"]["low"] is None
    assert "interval unavailable" in report["alt_text"].lower()


def test_point_only_two_point_fit_is_available_without_scipy(tmp_path):
    process, report = rendered(
        tmp_path,
        pd.DataFrame({"scale": [1, 2], "loss": [3, 6]}),
        block_scipy=True,
        interval="none",
        show_points=False,
    )
    assert process.returncode == 0, process.stderr
    fit = report["data"]["counts"]["scaling_fits"][0]
    assert fit["slope"] == pytest.approx(1, rel=0, abs=1e-12)
    assert fit["interval"]["status"] == "not_requested" and fit["stderr"] is None
    assert report["outputs"] and "not requested" in report["alt_text"].lower()


def test_missing_statistics_dependency_makes_requested_interval_untested(tmp_path):
    process, report = rendered(tmp_path, sample(), block_scipy=True)
    assert process.returncode == 2 and report["status"] == "incomplete" and report["outputs"]
    interval = report["data"]["counts"]["scaling_fits"][0]["interval"]
    assert interval["low"] is None and interval["status"] == "unavailable"
    assert "statistics" in interval["reason"]
    assert any(f["code"] == "scaling_interval_unavailable" for f in report["findings"])


def test_invalid_domain_produces_failed_runtime_evidence_without_exports(tmp_path):
    process, report = rendered(tmp_path, sample().assign(scale=[-1, 10, 100]), interval="none")
    assert process.returncode == 1 and report["status"] == "failed" and not report["outputs"]


def test_fit_descriptions_and_exported_provenance_report_actual_parameters(tmp_path):
    process, report = rendered(tmp_path, sample(), interval="none")
    assert process.returncode == 0, process.stderr
    assert (
        "exponent is 1.5" in report["alt_text"].lower() and "3 observations" in report["alt_text"]
    )
    assert "follows a power law" not in report["alt_text"].lower()
    assert "raw mean" not in report["alt_text"].lower()
    for suffix in ["png", "svg"]:
        evidence = read_provenance(tmp_path / ("scaling." + suffix))
        assert evidence["alt_text"] == report["alt_text"]


@pytest.mark.parametrize(
    ("field", "value"), [("model", None), ("model", " "), ("model", np.inf), ("site", None)]
)
def test_invalid_series_or_panel_labels_fail_before_grouping(tmp_path, field, value):
    module, _ = generated(
        tmp_path, interval="none", group="model", facet={"by": "site", "columns": 2}
    )
    rows = sample().assign(model="base", site="first").astype(object)
    rows.iloc[0, rows.columns.get_loc(field)] = value
    with pytest.raises(ValueError, match="Scaling"):
        module.prepare(rows)


def test_faceted_fit_evidence_and_descriptions_remain_separate(tmp_path):
    rows = pd.concat(
        [
            sample().assign(site="first"),
            sample().assign(site="second", loss=lambda f: 1 / f["loss"]),
        ]
    )
    process, report = rendered(
        tmp_path,
        rows,
        interval="none",
        facet={"by": "site", "columns": 2},
        output={"stem": "scaling", "formats": ["png"], "size": "double_column", "dpi": 100},
    )
    assert process.returncode == 0, process.stderr
    fits = report["data"]["counts"]["scaling_fits"]
    assert [f["panel"] for f in fits] == [0, 1]
    np.testing.assert_allclose([f["slope"] for f in fits], [1.5, -1.5], rtol=0, atol=1e-12)
    assert "Panel first" in report["alt_text"] and "Panel second" in report["alt_text"]


def test_visible_point_claims_use_observations_instead_of_slope_or_fitted_endpoints(tmp_path):
    rows = pd.concat(
        [
            pd.DataFrame({"scale": [1, 10, 100], "loss": [1, 1, 100], "model": "base"}),
            pd.DataFrame({"scale": [1, 10, 100], "loss": [100, 100, 50], "model": "ours"}),
        ]
    )
    process, report = rendered(
        tmp_path,
        rows,
        interval="none",
        group="model",
        claims=[{"kind": "beats_at_end", "subject": "ours", "reference": "base"}],
    )
    assert process.returncode == 2 and report["claims"][0]["verdict"] == "fails"
    assert "-50" in report["claims"][0]["detail"]


def test_direct_label_attaches_to_actual_fitted_endpoint(tmp_path):
    module, _ = generated(tmp_path, interval="none", group="model", legend={"style": "direct"})
    rows = pd.DataFrame({"scale": [1, 10, 100], "loss": [1, 1, 100], "model": "base"})
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, rows)
        module.add_legend(fig, ax, rows)
        np.testing.assert_allclose(ax.texts[0].xy, [100, 10 ** (5 / 3)], rtol=0, atol=1e-10)
        assert ax.texts[0].xy[1] != 100
    finally:
        plt.close(fig)


@pytest.mark.parametrize(
    "extra",
    [
        {
            "show_points": False,
            "group": "model",
            "claims": [{"kind": "beats_at_end", "subject": "ours", "reference": "base"}],
        },
        {"show_points": False, "annotate": [{"at": "max", "text": "Observed maximum"}]},
        {"transform": {"kind": "normalize"}},
        {"x": {"field": "scale", "label": "Time", "temporal": True}},
    ],
)
def test_unsupported_claim_or_preparation_semantics_are_static_errors(extra):
    result = local_request("convert", {**BASE, **extra})
    assert not result["ok"]
    assert any(f["code"] == "unsupported_scaling_semantics" for f in result["findings"])


def test_point_only_series_have_named_distinguishable_curve_handles(tmp_path):
    module, _ = generated(tmp_path, interval="none", show_points=False, group="model")
    rows = pd.concat(
        [sample().assign(model="base"), sample().assign(model="ours", loss=lambda f: 2 * f["loss"])]
    )
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, rows)
        assert not ax.collections and len(ax.lines) == 2
        assert ax.get_legend_handles_labels()[1] == ["base", "ours"]
        assert ax.lines[0].get_linestyle() != ax.lines[1].get_linestyle()
    finally:
        plt.close(fig)


def test_small_nonzero_interval_is_not_rounded_to_identical_displayed_bounds(tmp_path):
    pytest.importorskip("scipy.stats")
    module, _ = generated(tmp_path)
    rows = pd.DataFrame({"scale": [1, 10, 100], "loss": 10.0 ** np.array([0, 1 + 1e-6, 2])})
    text = module.alt_text(rows)
    shown = float(re.search(r"plus or minus ([0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?)", text).group(1))
    expected = math.tan(0.475 * math.pi) * 1e-6 / math.sqrt(3)
    assert shown == pytest.approx(expected, rel=1e-4)


def test_positive_observation_claim_still_holds_with_fit_evidence(tmp_path):
    rows = pd.concat(
        [sample().assign(model="base"), sample().assign(model="ours", loss=lambda f: 2 * f["loss"])]
    )
    process, report = rendered(
        tmp_path,
        rows,
        interval="none",
        group="model",
        claims=[{"kind": "beats_everywhere", "subject": "ours", "reference": "base"}],
    )
    assert process.returncode == 0, process.stderr
    assert (
        report["claims"][0]["verdict"] == "holds"
        and len(report["data"]["counts"]["scaling_fits"]) == 2
    )


def test_runtime_t_interval_is_available_and_keeps_parameter_bounds_off_log_y(tmp_path):
    pytest.importorskip("scipy.stats")
    process, report = rendered(tmp_path, sample())
    assert process.returncode == 0, process.stderr
    interval = report["data"]["counts"]["scaling_fits"][0]["interval"]
    assert interval["status"] == "available" and interval["low"] < 0 < interval["high"]
    assert interval["margin"] > 3 and "conditional 95% student-t" in report["alt_text"].lower()


def test_each_cohort_needs_an_identifiable_fit(tmp_path):
    rows = pd.concat([sample().assign(model="base"), sample().iloc[:1].assign(model="ours")])
    process, report = rendered(tmp_path, rows, interval="none", group="model")
    assert process.returncode == 1 and report["status"] == "failed" and not report["outputs"]


def test_continuous_overlay_uses_actual_x_coordinates(tmp_path):
    module, _ = generated(
        tmp_path,
        interval="none",
        layers=[{"mark": "line", "y": "reference", "label": "External reference"}],
    )
    rows = sample().assign(reference=[2, 4, 8])
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, rows)
        module.draw_layers(ax, rows)
        np.testing.assert_array_equal(ax.lines[-1].get_xdata(), [1, 10, 100])
        np.testing.assert_array_equal(ax.lines[-1].get_ydata(), [2, 4, 8])
        assert ax.lines[-1].get_label() == "External reference"
    finally:
        plt.close(fig)


def test_direct_fitted_labels_are_attached_in_each_facet(tmp_path, monkeypatch):
    module, _ = generated(
        tmp_path,
        interval="none",
        show_points=False,
        group="model",
        legend={"style": "direct"},
        facet={"by": "site", "columns": 2},
        output={"stem": "scaling", "formats": ["png"], "size": "double_column", "dpi": 100},
    )
    first = pd.concat(
        [sample().assign(model="base"), sample().assign(model="ours", loss=lambda f: 2 * f["loss"])]
    )
    rows = pd.concat(
        [first.assign(site="first"), first.assign(site="second", loss=lambda f: f["loss"] * 10)]
    )
    rows.to_csv(tmp_path / "data.csv", index=False)
    captured = []
    close = plt.close
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(plt, "close", captured.append)
    try:
        module.main()
        assert [[text.get_text() for text in ax.texts] for ax in captured[-1].axes] == [
            ["base", "ours"],
            ["base", "ours"],
        ]
    finally:
        for fig in captured:
            close(fig)
