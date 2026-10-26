"""Independent matched-unit answers, real artists and explicit exclusions."""

from __future__ import annotations

import importlib.util
import itertools
import json
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from graphunslopify import read_provenance
from graphunslopify.transport import local_request

BASE = {
    "kind": "paired_difference",
    "x": {"field": "condition", "label": "Condition"},
    "y": {"field": "score", "label": "Score"},
    "pair": "unit",
    "baseline": "base",
    "legend": {"show": False},
    "output": {"stem": "paired", "formats": ["png", "svg"], "dpi": 100},
}


def sample():
    # The raw condition means are deliberately unlike the matched difference mean 5.
    return pd.DataFrame(
        {
            "unit": ["A", "A", "B", "B", "C", "D"],
            "condition": ["base", "new", "base", "new", "base", "new"],
            "score": [10, 14, 20, 26, 100, 1000],
        }
    )


def generated(folder, **extra):
    spec = {**BASE, "data": {"path": str(folder / "data.csv")}, **extra}
    result = local_request("convert", spec)
    assert result.get("ok"), result
    path = folder / "paired.py"
    path.write_text(result["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("paired_reference", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module, path


@pytest.fixture(scope="module")
def emitted(tmp_path_factory):
    return generated(tmp_path_factory.mktemp("paired-reference"))[0]


def test_actual_points_center_interval_and_tick_count_match_hand_answers(emitted):
    fig, ax = plt.subplots()
    try:
        emitted.draw_panel(ax, sample())
        np.testing.assert_allclose(
            ax.collections[0].get_offsets()[:, 1], [4, 6], rtol=0, atol=1e-12
        )
        centers = [line for line in ax.lines if line.get_marker() == "o"]
        assert len(centers) == 1
        assert list(centers[0].get_ydata()) == [5]
        assert list(ax.lines[0].get_ydata()) == [4, 6]
        assert "n=2" in ax.get_xticklabels()[0].get_text()
    finally:
        plt.close(fig)


def test_pairing_and_intervals_are_invariant_under_row_permutations(emitted):
    rows = sample().iloc[:4]
    for order in itertools.permutations(range(4)):
        estimate = emitted.paired_estimates(rows.iloc[list(order)])[0]
        np.testing.assert_allclose(estimate["values"], [4, 6], rtol=0, atol=1e-12)
        assert estimate["mean"] == 5
        assert (estimate["low"], estimate["high"]) == (4, 6)


def test_skewed_mean_interval_and_actual_artist_match_independent_scipy(emitted):
    # random_state supports the statistics extra's minimum SciPy 1.11 API.
    stats = pytest.importorskip("scipy.stats")
    differences = np.array([1, 2, 4, 8, 16.0])
    reference = stats.bootstrap(
        (differences,),
        np.mean,
        method="percentile",
        n_resamples=2000,
        random_state=np.random.default_rng(20260903),
    ).confidence_interval
    rows = pd.DataFrame(
        {
            "unit": np.repeat(list("ABCDE"), 2),
            "condition": ["base", "new"] * 5,
            "score": np.column_stack([np.full(5, 10), 10 + differences]).ravel(),
        }
    )
    estimate = emitted.paired_estimates(rows)[0]
    assert estimate["mean"] == pytest.approx(6.2, rel=0, abs=1e-12)
    np.testing.assert_allclose([estimate["low"], estimate["high"]], reference, rtol=0, atol=1e-12)
    fig, ax = plt.subplots()
    try:
        emitted.draw_panel(ax, rows)
        np.testing.assert_allclose(ax.lines[0].get_ydata(), reference, rtol=0, atol=1e-12)
    finally:
        plt.close(fig)


def test_technical_repeats_are_averaged_before_equal_unit_differences(emitted):
    rows = pd.DataFrame(
        {
            "unit": ["A", "A", "A", "A", "B", "B"],
            "condition": ["base", "base", "new", "new", "base", "new"],
            "score": [8, 12, 12, 16, 20, 26],
        }
    )
    estimate = emitted.paired_estimates(rows)[0]
    assert estimate["mean"] == 5
    assert estimate["n"] == 2 and estimate["technical_repeats"] == 2
    np.testing.assert_array_equal(estimate["values"], [4, 6])
    assert "averaged" in emitted.alt_text(rows).lower()


def test_unmatched_units_are_counted_without_changing_paired_estimate(emitted):
    estimate = emitted.paired_estimates(sample())[0]
    assert estimate["units"] == 4 and estimate["n"] == 2
    assert estimate["baseline_only"] == 1 and estimate["candidate_only"] == 1
    assert estimate["neither"] == 0


def test_missing_measurements_have_comparison_specific_exclusion_counts(emitted):
    rows = pd.DataFrame(
        {
            "unit": ["A", "A", "B", "B", "C", "C", "D", "D"],
            "condition": ["base", "new"] * 4,
            "score": [10, 14, 20, np.nan, np.nan, 30, np.nan, np.nan],
        }
    )
    estimate = emitted.paired_estimates(rows)[0]
    assert estimate["n"] == 1 and estimate["mean"] == 4
    assert [estimate[key] for key in ["baseline_only", "candidate_only", "neither"]] == [1, 1, 1]
    assert estimate["missing_measurements"] == 4
    assert np.isnan(estimate["low"]) and np.isnan(estimate["high"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("unit", None),
        ("condition", None),
        ("unit", " "),
        ("unit", np.inf),
        ("condition", ""),
        ("score", np.inf),
        ("score", -np.inf),
        ("score", "invalid"),
    ],
)
def test_invalid_identifiers_or_nonmissing_measurements_fail_before_pivoting(emitted, field, value):
    rows = sample().astype(object)
    rows.loc[0, field] = value
    with pytest.raises(ValueError, match="Paired"):
        emitted.prepare(rows)
    fig, ax = plt.subplots()
    try:
        with pytest.raises(ValueError, match="Paired"):
            emitted.draw_panel(ax, rows)
    finally:
        plt.close(fig)


@pytest.mark.parametrize(
    "rows",
    [
        pd.DataFrame({"unit": [], "condition": [], "score": []}),
        sample().drop(columns="unit"),
        sample().query('condition == "new"'),
        sample().query('condition == "base"'),
        pd.DataFrame({"unit": ["A", "B"], "condition": ["base", "new"], "score": [1, 2]}),
    ],
)
def test_empty_missing_baseline_alternative_or_pairs_cannot_verify_a_plot(emitted, rows):
    with pytest.raises(ValueError, match="Paired"):
        emitted.paired_estimates(rows)


def test_description_summarizes_actual_differences_and_discloses_exclusions(emitted):
    text = emitted.alt_text(sample()).lower()
    assert "mean difference is 5" in text and "2 matched pairs" in text
    assert "1 baseline-only" in text and "1 candidate-only" in text
    assert "95%" in text and "4" in text and "6" in text
    assert "1e+03" not in text and "mean is 195" not in text


def test_numeric_baseline_matches_its_unique_representation(tmp_path):
    module, _ = generated(tmp_path, baseline="0")
    rows = sample().iloc[:4].replace({"condition": {"base": 0, "new": 1}})
    estimate = module.paired_estimates(rows)[0]
    assert estimate["condition"] == "1" and estimate["baseline"] == "0"
    np.testing.assert_array_equal(estimate["values"], [4, 6])


def test_ambiguous_baseline_representations_are_not_merged(tmp_path):
    module, _ = generated(tmp_path, baseline="0")
    rows = pd.DataFrame({"unit": ["A", "A", "A"], "condition": [0, "0", "new"], "score": [1, 2, 3]})
    with pytest.raises(ValueError, match="ambiguous"):
        module.paired_estimates(rows)


def test_author_filters_run_before_identifier_and_measurement_validation(tmp_path):
    module, _ = generated(tmp_path, filter=[{"field": "keep", "op": "eq", "value": 1}])
    rows = sample().assign(keep=1)
    bad = pd.DataFrame({"unit": [None], "condition": [None], "score": [np.inf], "keep": [0]})
    prepared = module.prepare(pd.concat([bad, rows]))
    assert module.paired_estimates(prepared)[0]["mean"] == 5


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


def test_runtime_pair_evidence_and_provenance_agree_with_displayed_differences(tmp_path):
    process, report = rendered(tmp_path, sample())
    assert process.returncode == 0, process.stderr
    pairing = report["data"]["counts"]["pairing"]
    assert len(pairing) == 1 and pairing[0]["panel"] == 0 and pairing[0]["n"] == 2
    assert pairing[0]["mean"] == 5 and pairing[0]["baseline_only"] == 1
    assert pairing[0]["interval"] == {
        "method": "percentile_bootstrap_mean",
        "level": 0.95,
        "resamples": 2000,
        "seed": 20260903,
    }
    assert any(f["code"] == "paired_units_excluded" for f in report["findings"])
    for suffix in ["png", "svg"]:
        evidence = read_provenance(tmp_path / ("paired." + suffix))
        assert evidence["alt_text"] == report["alt_text"]


def test_singleton_has_unknown_interval_visible_count_and_incomplete_strict_report(tmp_path):
    process, report = rendered(tmp_path, sample().iloc[:2])
    assert process.returncode == 2 and report["status"] == "incomplete"
    assert "interval unavailable" in report["alt_text"].lower()
    assert report["data"]["counts"]["pairing"][0]["low"] is None
    assert any("paired" in item.lower() for item in report["untested"])
    assert report["outputs"]


def test_facets_pair_only_within_their_own_panel(tmp_path):
    first = sample().iloc[:4].assign(site="first")
    second = first.assign(site="second", score=[100, 90, 200, 180])
    process, report = rendered(
        tmp_path,
        pd.concat([first, second]),
        facet={"by": "site", "columns": 2},
        output={"stem": "paired", "formats": ["png"], "size": "double_column", "dpi": 100},
    )
    assert process.returncode == 0, process.stderr
    assert [
        (item["panel"], item["n"], item["mean"]) for item in report["data"]["counts"]["pairing"]
    ] == [(0, 2, 5), (1, 2, -15)]
    assert "Panel first" in report["alt_text"] and "Panel second" in report["alt_text"]


@pytest.mark.parametrize(
    "extra",
    [
        {"group": "model"},
        {"transform": {"kind": "normalize"}},
        {"pair": "score"},
        {
            "group": "model",
            "claims": [{"kind": "beats_at_end", "subject": "new", "reference": "base"}],
        },
        {"layers": [{"mark": "line", "y": "other"}]},
        {"y": {"field": "score", "label": "Score", "scale": "log"}},
    ],
)
def test_unsupported_raw_series_or_transform_semantics_are_static_errors(extra):
    result = local_request("convert", {**BASE, **extra})
    assert not result["ok"]
    assert any(
        f["severity"] == "error"
        and f["code"] in ["unsupported_paired_semantics", "paired_difference_group_ignored"]
        for f in result["findings"]
    )


@pytest.mark.parametrize(
    "scores", [[1e308, -1e308, 0, 1], [0, 1e308, 0, 1e308], [0, -1e308, 0, 1e308]]
)
def test_overflow_in_differences_means_or_bootstrap_cannot_verify_nonfinite_derived_values(
    emitted, scores
):
    rows = sample().iloc[:4].assign(score=scores)
    with pytest.raises(ValueError, match="Paired"):
        emitted.paired_estimates(rows)


def test_an_unmatched_comparison_stays_visible_and_makes_strict_verification_incomplete(tmp_path):
    rows = pd.concat(
        [sample().iloc[:4], pd.DataFrame({"unit": ["C"], "condition": ["orphan"], "score": [1000]})]
    )
    process, report = rendered(tmp_path, rows)
    assert process.returncode == 2 and report["status"] == "incomplete"
    pairing = report["data"]["counts"]["pairing"]
    assert [(item["condition"], item["n"]) for item in pairing] == [("new", 2), ("orphan", 0)]
    assert pairing[1]["mean"] is None and pairing[1]["low"] is None
    assert "orphan minus base: no complete pairs" in report["alt_text"].lower()
    assert report["outputs"]


def test_estimation_does_not_mutate_author_rows(emitted):
    rows = sample()
    original = rows.copy(deep=True)
    emitted.paired_estimates(rows)
    pd.testing.assert_frame_equal(rows, original)


def test_missing_panel_identifiers_fail_before_facet_assignment(tmp_path):
    module, _ = generated(tmp_path, facet={"by": "site", "columns": 2})
    rows = sample().assign(site="first").astype(object)
    rows.loc[0, "site"] = None
    with pytest.raises(ValueError, match="Paired"):
        module.prepare(rows)


def test_description_matches_difference_units_and_pair_identity(tmp_path):
    module, _ = generated(tmp_path, y={"field": "score", "label": "Accuracy", "unit": "%"})
    text = module.alt_text(sample())
    assert "percentage points" in text and "paired by unit with baseline base" in text
    assert "mean difference is 5" in text
