"""Independent normal/uniform quantiles, quartile lines and sample evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
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
    "kind": "qq",
    "x": {"field": "theory", "label": "Theoretical quantile"},
    "y": {"field": "value", "label": "Sample quantile"},
    "legend": {"show": False},
    "output": {"stem": "qq", "formats": ["png", "svg"], "dpi": 100},
}


def generated(folder, **extra):
    spec = {**BASE, "data": {"path": str(folder / "data.csv")}, **extra}
    if extra.get("group") and "legend" not in extra:
        spec["legend"] = {"position": "outside_bottom"}
    result = local_request("convert", spec)
    assert result.get("ok"), result
    path = folder / "qq.py"
    path.write_text(result["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("qq_reference", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module, path


@pytest.fixture(scope="module")
def emitted(tmp_path_factory):
    return generated(tmp_path_factory.mktemp("qq-reference"))[0]


@pytest.mark.parametrize("size", [2, 3, 4, 100, 10000])
def test_actual_normal_quantiles_match_independent_scipy_at_blom_positions(emitted, size):
    stats = pytest.importorskip("scipy.stats")
    values = np.arange(size, dtype=float)
    expected = stats.norm.ppf((np.arange(1, size + 1) - 0.375) / (size + 0.25))
    fig, ax = plt.subplots()
    try:
        emitted.draw_panel(ax, pd.DataFrame({"value": values[::-1]}))
        points = np.asarray(ax.collections[0].get_offsets(), dtype=float)
        np.testing.assert_allclose(points[:, 0], expected, rtol=0, atol=1e-12)
        np.testing.assert_array_equal(points[:, 1], values)
    finally:
        plt.close(fig)


def test_uniform_positions_and_population_quartile_line_match_hand_answers(tmp_path):
    module, _ = generated(tmp_path, distribution="uniform")
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, pd.DataFrame({"value": [4, 1, 3, 2]}))
        points = np.asarray(ax.collections[0].get_offsets(), dtype=float)
        # Blom positions are 5/34,13/34,21/34,29/34. Observed quartiles 1.75/3.25
        # match population U(0,1) quartiles .25/.75, so the reference is y=1+3x.
        np.testing.assert_allclose(points[:, 0], np.array([5, 13, 21, 29]) / 34, rtol=0, atol=1e-12)
        np.testing.assert_array_equal(points[:, 1], [1, 2, 3, 4])
        np.testing.assert_allclose(
            ax.lines[0].get_ydata(), 1 + 3 * ax.lines[0].get_xdata(), rtol=0, atol=1e-12
        )
    finally:
        plt.close(fig)


def test_normal_reference_line_matches_independent_population_quartiles(emitted):
    stats = pytest.importorskip("scipy.stats")
    fig, ax = plt.subplots()
    try:
        emitted.draw_panel(ax, pd.DataFrame({"value": [-2, 0, 2, 4]}))
        q = stats.norm.ppf([0.25, 0.75])
        slope = 3 / (q[1] - q[0])
        np.testing.assert_allclose(
            ax.lines[0].get_ydata(), 1 + slope * ax.lines[0].get_xdata(), rtol=0, atol=1e-12
        )
    finally:
        plt.close(fig)


def test_extreme_probabilities_are_not_clipped_or_approximated(emitted):
    stats = pytest.importorskip("scipy.stats")
    probabilities = np.array([1e-14, 1e-10, 0.5, 1 - 1e-10, 1 - 1e-14])
    np.testing.assert_allclose(
        emitted.qq_quantiles(probabilities), stats.norm.ppf(probabilities), rtol=0, atol=1e-12
    )


def test_estimates_are_invariant_to_row_permutation_without_mutating_rows(emitted):
    rows = pd.DataFrame({"value": [4.0, 1, 3, 2]})
    original = rows.copy(deep=True)
    for order in itertools.permutations(range(4)):
        curve = emitted.qq_estimate(rows.iloc[list(order)])
        np.testing.assert_array_equal(curve["observed"], [1, 2, 3, 4])
        assert curve["median"] == 2.5 and curve["observations"] == 4
    pd.testing.assert_frame_equal(rows, original)


@pytest.mark.parametrize(
    "values",
    [[], [1], [np.nan, 1], [np.nan, np.nan], [1, 2, np.inf], [1, 2, -np.inf], [1, 2, "bad"]],
)
def test_empty_small_or_invalid_samples_cannot_render_a_verified_empty_plot(emitted, values):
    rows = pd.DataFrame({"value": values})
    with pytest.raises(ValueError, match="Q-Q"):
        emitted.prepare(rows)
    fig, ax = plt.subplots()
    try:
        with pytest.raises(ValueError, match="Q-Q"):
            emitted.draw_panel(ax, rows)
    finally:
        plt.close(fig)


def test_missing_measurements_are_disclosed_and_numeric_strings_are_converted(emitted):
    rows = emitted.prepare(pd.DataFrame({"value": ["1", "2", None, "3"]}))
    curve = emitted.qq_estimate(rows)
    assert curve["observations"] == 3 and curve["missing"] == 1
    text = emitted.alt_text(rows).lower()
    assert "3 observations" in text and "1 missing" in text and "normal" in text
    assert "quartile" in text and "not a normality test" in text


def test_constant_samples_remain_visible_with_explicit_shape_warning(emitted):
    fig, ax = plt.subplots()
    try:
        emitted.draw_panel(ax, pd.DataFrame({"value": [2, 2, 2]}))
        np.testing.assert_array_equal(ax.collections[0].get_offsets()[:, 1], [2, 2, 2])
        assert "constant sample" in emitted.alt_text(pd.DataFrame({"value": [2, 2, 2]})).lower()
        assert any(f["code"] == "qq_constant_sample" for f in emitted.RUN_REPORT["findings"])
    finally:
        plt.close(fig)


def test_author_filters_run_before_domain_checks(tmp_path):
    module, _ = generated(tmp_path, filter=[{"field": "keep", "op": "eq", "value": 1}])
    rows = module.prepare(pd.DataFrame({"value": [np.inf, 1, 2], "keep": [0, 1, 1]}))
    assert module.qq_estimate(rows)["observations"] == 2


def test_normalization_is_preserved_on_observed_values_and_disclosed_as_unitless(tmp_path):
    module, _ = generated(
        tmp_path,
        transform={"kind": "normalize"},
        y={"field": "value", "label": "Score", "unit": "%"},
    )
    rows = module.prepare(pd.DataFrame({"value": ["2", "4", "6", "8"]}))
    np.testing.assert_allclose(
        module.qq_estimate(rows)["observed"], [0, 1 / 3, 2 / 3, 1], rtol=0, atol=1e-12
    )
    text = module.alt_text(rows).lower()
    assert "normalized" in text and "unitless" in text and "score in %" not in text
    fig, ax = plt.subplots()
    try:
        module.decorate_panel(ax, rows, None)
        assert "Normalized Score" in ax.get_ylabel() and "(%)" not in ax.get_ylabel()
    finally:
        plt.close(fig)


def rendered(folder, rows, **extra):
    _, path = generated(folder, **extra)
    rows.to_csv(folder / "data.csv", index=False)
    process = subprocess.run(
        [sys.executable, str(path), "--strict", "--json"],
        cwd=folder,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(process.stdout)
    assert report["exit_code"] == process.returncode, process.stderr
    return process, report


def cohorts(first=(1, 2, 3, 4), second=(2, 3, 4, 5)):
    return pd.concat(
        [
            pd.DataFrame({"value": first, "model": "base"}),
            pd.DataFrame({"value": second, "model": "ours"}),
        ]
    )


def test_claims_and_provenance_use_actual_quantiles_without_raw_x(tmp_path):
    process, report = rendered(
        tmp_path,
        cohorts(),
        group="model",
        claims=[{"kind": "beats_everywhere", "subject": "ours", "reference": "base"}],
    )
    assert process.returncode == 0, process.stderr
    assert report["claims"][0]["verdict"] == "holds"
    assert report["data"]["counts"]["qq"][0]["observations"] == 4
    assert "quartile" in report["alt_text"].lower()
    for suffix in ["png", "svg"]:
        evidence = read_provenance(tmp_path / ("qq." + suffix))
        assert evidence["alt_text"] == report["alt_text"]


def test_raw_x_order_cannot_certify_a_false_quantile_claim(tmp_path):
    rows = cohorts(first=(1, 2, 3, 10), second=(5, 6, 7, 8))
    rows["theory"] = [1, 2, 3, 0, 0, 1, 2, 3]
    process, report = rendered(
        tmp_path,
        rows,
        group="model",
        claims=[{"kind": "beats_at_end", "subject": "ours", "reference": "base"}],
    )
    assert process.returncode == 2 and report["claims"][0]["verdict"] == "fails"
    assert "-2" in report["claims"][0]["detail"] and report["outputs"]


def test_different_quantile_grids_are_untested_instead_of_interpolated(tmp_path):
    process, report = rendered(
        tmp_path,
        cohorts(second=(2, 3, 4)),
        group="model",
        claims=[{"kind": "beats_at_end", "subject": "ours", "reference": "base"}],
    )
    assert process.returncode == 2 and report["claims"][0]["verdict"] == "untested"
    assert report["outputs"] and not any(f["code"] == "runtime_error" for f in report["findings"])


def test_singleton_has_failed_runtime_evidence_and_no_plot(tmp_path):
    process, report = rendered(tmp_path, pd.DataFrame({"value": [2]}))
    assert process.returncode == 1 and report["status"] == "failed" and not report["outputs"]
    assert any("Q-Q" in f["message"] for f in report["findings"])


@pytest.mark.parametrize(
    ("field", "value"), [("model", None), ("model", " "), ("model", np.inf), ("site", None)]
)
def test_missing_or_invalid_labels_fail_before_grouping(tmp_path, field, value):
    module, _ = generated(tmp_path, group="model", facet={"by": "site", "columns": 2})
    rows = cohorts().assign(site="first").astype(object)
    rows.iloc[0, rows.columns.get_loc(field)] = value
    with pytest.raises(ValueError, match=rf"[Ii]dentifier.*{field}"):
        module.prepare(rows)


def test_each_group_needs_two_observations_even_when_pooled_sample_is_larger(tmp_path):
    process, report = rendered(tmp_path, cohorts(second=(2,)), group="model")
    assert process.returncode == 1 and report["status"] == "failed" and not report["outputs"]


def test_faceted_claims_and_sample_counts_are_panel_scoped(tmp_path):
    rows = pd.concat(
        [cohorts().assign(site="first"), cohorts(second=(-2, -1, 0, 1)).assign(site="second")]
    )
    process, report = rendered(
        tmp_path,
        rows,
        group="model",
        facet={"by": "site", "columns": 2},
        output={"stem": "qq", "formats": ["png"], "size": "double_column", "dpi": 100},
        claims=[{"kind": "beats_everywhere", "subject": "ours", "reference": "base"}],
    )
    assert process.returncode == 2
    assert [(c["panel"], c["verdict"]) for c in report["claims"]] == [(0, "holds"), (1, "fails")]
    assert [(c["panel"], c["observations"]) for c in report["data"]["counts"]["qq"]] == [
        (0, 4),
        (0, 4),
        (1, 4),
        (1, 4),
    ]


def test_direct_labels_and_annotations_use_derived_coordinates_without_raw_x(tmp_path):
    module, _ = generated(
        tmp_path,
        distribution="uniform",
        group="model",
        legend={"style": "direct"},
        annotate=[{"at": "max", "series": "ours", "text": "Maximum"}],
    )
    rows = cohorts()
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, rows)
        module.decorate_panel(ax, rows, None)
        module.add_legend(fig, ax, rows)
        found = {text.get_text(): text.xy for text in ax.texts}
        np.testing.assert_allclose(found["Maximum"], [29 / 34, 5], rtol=0, atol=1e-12)
        np.testing.assert_allclose(found["ours"], [29 / 34, 5], rtol=0, atol=1e-12)
    finally:
        plt.close(fig)


@pytest.mark.parametrize(
    "extra",
    [
        {"transform": {"kind": "cumulative"}},
        {"group": "model", "transform": {"kind": "delta_vs_baseline", "baseline": "base"}},
        {"layers": [{"mark": "line", "y": "raw"}]},
        {
            "distribution": "normal",
            "x": {"field": "theory", "label": "Theoretical", "scale": "log"},
        },
        {
            "group": "model",
            "y": {"field": "theory", "label": "Sample"},
            "claims": [{"kind": "monotone_increasing", "subject": "ours"}],
        },
    ],
)
def test_undefined_raw_x_or_ambiguous_semantics_are_explicit_static_errors(extra):
    result = local_request("convert", {**BASE, **extra})
    assert not result["ok"]
    assert any(f["code"] == "unsupported_qq_semantics" for f in result["findings"])


def test_supported_log_scales_sample_the_reference_curve_and_validate_positive_domain(tmp_path):
    module, _ = generated(
        tmp_path,
        distribution="uniform",
        x={"field": "theory", "label": "Theory", "scale": "log"},
        y={"field": "value", "label": "Sample", "scale": "log"},
    )
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, pd.DataFrame({"value": [1, 2, 3, 4]}))
        assert len(ax.lines[0].get_xdata()) >= 100
        np.testing.assert_allclose(
            ax.lines[0].get_ydata(), 1 + 3 * ax.lines[0].get_xdata(), rtol=0, atol=1e-12
        )
        with pytest.raises(ValueError, match="Q-Q"):
            module.qq_estimate(pd.DataFrame({"value": [-1, 2, 3, 4]}))
    finally:
        plt.close(fig)


@pytest.mark.parametrize("probability", [0, 1, np.nan])
def test_invalid_plotting_probabilities_are_refused_instead_of_clipped(emitted, probability):
    with pytest.raises(ValueError, match="Q-Q"):
        emitted.qq_quantiles([probability])


def test_missing_sample_counts_are_preserved_in_runtime_evidence(tmp_path):
    process, report = rendered(tmp_path, pd.DataFrame({"value": [1, 2, np.nan, 3]}))
    assert process.returncode == 0, process.stderr
    assert report["data"]["counts"]["qq"][0]["observations"] == 3
    assert report["data"]["counts"]["qq"][0]["missing"] == 1
    assert "1 missing" in report["alt_text"].lower()
    assert any(f["code"] == "nonfinite_measurements" for f in report["findings"])


def test_nonfinite_derived_quartiles_or_reference_line_cannot_pass(emitted):
    with pytest.raises(ValueError, match="Q-Q"):
        emitted.qq_estimate(pd.DataFrame({"value": [-1e308, 1e308]}))


def test_normalization_remains_per_series_with_known_unitless_quartiles(tmp_path):
    module, _ = generated(tmp_path, group="model", transform={"kind": "normalize"})
    rows = module.prepare(cohorts(first=(10, 20, 30, 40), second=(100, 200, 300, 400)))
    for name in ["base", "ours"]:
        curve = module.qq_estimate(rows[rows["model"] == name])
        np.testing.assert_allclose(
            [curve["q1"], curve["median"], curve["q3"]], [0.25, 0.5, 0.75], rtol=0, atol=1e-12
        )


def test_each_facet_receives_its_own_direct_quantile_labels(tmp_path, monkeypatch):
    module, _ = generated(
        tmp_path,
        group="model",
        legend={"style": "direct"},
        facet={"by": "site", "columns": 2},
        output={"stem": "qq", "formats": ["png"], "size": "double_column", "dpi": 100},
    )
    rows = pd.concat(
        [
            cohorts().assign(site="first"),
            cohorts().assign(site="second", value=lambda f: f["value"] + 10),
        ]
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


def test_crossover_annotation_uses_the_first_aligned_derived_quantile(tmp_path):
    module, _ = generated(
        tmp_path,
        group="model",
        distribution="uniform",
        annotate=[{"at": "crossover", "series": "ours", "text": "Crosses"}],
    )
    rows = cohorts(second=(0, 1, 4, 5))
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, rows)
        module.decorate_panel(ax, rows, None)
        np.testing.assert_allclose(ax.texts[0].xy, [21 / 34, 4], rtol=0, atol=1e-12)
    finally:
        plt.close(fig)


def test_crossover_cannot_infer_complete_order_from_unequal_grids(tmp_path):
    process, report = rendered(
        tmp_path,
        cohorts(first=(1, 2, 3, 4, 5), second=(4, 5, 6)),
        group="model",
        annotate=[{"at": "crossover", "series": "ours", "text": "Crosses"}],
    )
    assert process.returncode == 2 and report["status"] == "incomplete"
    assert any(f["code"] == "qq_annotation_unavailable" for f in report["findings"])
    assert report["outputs"] and not any(f["code"] == "runtime_error" for f in report["findings"])


def test_log_y_does_not_hide_a_negative_reference_line(tmp_path):
    module, _ = generated(tmp_path, y={"field": "value", "label": "Sample", "scale": "log"})
    with pytest.raises(ValueError, match="Q-Q log y"):
        module.qq_estimate(pd.DataFrame({"value": [1, 2, 3, 1000]}))


def test_published_qq_image_matches_its_committed_data_and_current_canonical_emitter():
    root = Path(__file__).resolve().parents[2]
    folder = root / "examples/references"
    spec = json.loads((folder / "qq.figure.json").read_text())
    result = local_request("convert", spec)
    assert result["ok"], result
    evidence = read_provenance(root / "docs/seventh-pass-qq.png")
    assert (
        evidence["data_sha256_prefix"]
        == hashlib.sha256((folder / "qq.csv").read_bytes()).hexdigest()[:16]
    )
    assert evidence["script_sha256"] == hashlib.sha256(result["code"].encode("utf8")).hexdigest()
    assert evidence["spec"]["series_order"] == spec["series_order"]
    assert (
        "80 observations" in evidence["alt_text"]
        and "population-quartile line" in evidence["alt_text"]
    )
