"""Design-aware comparisons: independent numerical references and actual CLI evidence."""

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
from scipy import stats

from graphunslopify.transport import local_request

BASE = {
    "kind": "bar",
    "x": {"field": "condition", "label": "Condition"},
    "y": {"field": "score", "label": "Score"},
    "aggregation": "mean",
    "uncertainty": {"kind": "sem", "over": "unit", "display": "bar"},
    "legend": {"show": False},
    "output": {"stem": "design", "formats": ["png", "svg"], "dpi": 100},
}


def generated(folder, method="bootstrap", design="paired", **extra):
    significance = {
        "method": method,
        "design": design,
        "pairs": [["base", "new"]],
        **({"pair_by": "unit"} if design == "paired" else {}),
    }
    spec = {
        **BASE,
        "data": {"path": str(folder / "data.csv")},
        "significance": significance,
        **extra,
    }
    result = local_request("convert", spec)
    assert result.get("ok"), result
    path = folder / "figure.py"
    path.write_text(result["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("design_reference", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module, path


def data():
    rows = []
    for unit, base, difference in zip(
        ["01", "1", "B", "C"], [10, 20, 30, 40], [1, 4, 2, 6], strict=True
    ):
        for condition, center in [("base", base), ("new", base + difference)]:
            for offset in [-1, 1]:
                rows.append((condition, center + offset, unit))
    return pd.DataFrame(rows, columns=["condition", "score", "unit"]).sample(
        frac=1, random_state=32
    )


def test_paired_t_matches_independent_scipy_reference_and_actual_bar_centers(tmp_path):
    module, _ = generated(tmp_path, method="ttest")
    data().to_csv(tmp_path / "data.csv", index=False)
    frame = module.prepare(module.load())
    module.RUN_REPORT = module.new_report()
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, frame)
        observed = module.RUN_REPORT["significance"][0]
        assert observed["raw_p"] == pytest.approx(
            stats.ttest_rel([10, 20, 30, 40], [11, 24, 32, 46]).pvalue
        )
        # Differences 1/4/2/6 have mean13/4 and sample variance59/12.
        hand_t = (13 / 4) / np.sqrt((59 / 12) / 4)
        assert observed["raw_p"] == pytest.approx(2 * stats.t.sf(hand_t, df=3))
        assert observed["sample_sizes"] == [4, 4]
        assert observed["matched_pairs"] == 4
        assert not observed["assumptions_verified"]
        assert sorted(patch.get_height() for patch in ax.patches) == [25, 28.25]
        assert observed["design"] == "paired" and observed["pair_by"] == "unit"
        assert "paired differences" in observed["null_hypothesis"]
    finally:
        plt.close(fig)


def test_sign_flips_match_hand_enumeration_and_do_not_depend_on_row_order(tmp_path):
    module, _ = generated(tmp_path)
    differences = [1, 4, 2, 6]
    tail = (
        sum(
            abs(sum(a * b for a, b in zip(differences, signs, strict=True)))
            >= abs(sum(differences))
            for signs in itertools.product([-1, 1], repeat=4)
        )
        / 16
    )
    assert tail == 2 / 16
    for order in [data(), data().iloc[::-1]]:
        frame = module.prepare(order)
        a, b, details = module.comparison_input(module.summary_input(frame, "score"), "base", "new")
        assert module.compare(a, b) == tail
        assert details["matched_pairs"] == 4


def test_incomplete_pairs_are_excluded_by_id_not_array_position(tmp_path):
    module, _ = generated(tmp_path)
    frame = pd.DataFrame(
        {
            "condition": ["base"] * 4 + ["new"] * 4,
            "unit": ["A", "B", "C", "D", "C", "A", "D", "E"],
            "score": [10, 20, 30, 40, 32, 11, np.nan, 1000],
        }
    )
    a, b, details = module.comparison_input(module.summary_input(frame, "score"), "base", "new")
    assert list(a) == [10, 30] and list(b) == [11, 32]
    assert details["matched_pairs"] == 2
    assert details["left_only_units"] == details["right_only_units"] == 1
    assert details["nonfinite_pairs"] == 1
    assert module.compare(a, b) == 0.5


def test_paired_compare_uses_joint_finite_mask_and_requires_equal_lengths(tmp_path):
    module, _ = generated(tmp_path)
    assert module.compare([1, np.nan, 4], [2, 8, 9]) == module.compare([1, 4], [2, 9])
    with pytest.raises(ValueError, match="equal lengths"):
        module.compare([1, 2], [1, 2, 3])
    assert module.compare([1, np.nan], [2, 3]) is None


def test_paired_monte_carlo_is_repeatable_and_nonzero(tmp_path):
    module, _ = generated(tmp_path)
    left = np.arange(14)
    result = module.compare(left, left + 100)
    assert result == 1 / 2001
    assert module.compare(left, left + 100) == result
    assert module.compare(left, left) == 1


@pytest.mark.parametrize("method", ["ttest", "mannwhitney", "bootstrap"])
def test_independent_reference_results_and_sampling_scope_are_retained(tmp_path, method):
    module, _ = generated(tmp_path, method=method, design="independent")
    a, b = [1, 2, 3, 4], [2, 3, 4, 5]
    expected = {
        "ttest": stats.ttest_ind(a, b, equal_var=False).pvalue,
        "mannwhitney": stats.mannwhitneyu(a, b, alternative="two-sided").pvalue,
        "bootstrap": 32 / 70,
    }
    assert module.compare(a, b) == pytest.approx(expected[method])
    frame = module.summary_input(data(), "score")
    _, _, details = module.comparison_input(frame, "base", "new")
    assert details["shared_unit_ids"] == 4
    assert any(item["code"] == "possibly_paired_samples" for item in module.RUN_REPORT["findings"])
    assert not details["assumptions_verified"]
    if method == "mannwhitney":
        assert "not median equality" in details["null_hypothesis"]


@pytest.mark.parametrize("correction", ["holm", "benjamini_hochberg"])
def test_unavailable_tests_do_not_shrink_declared_correction_family(tmp_path, correction):
    module, _ = generated(
        tmp_path,
        design="independent",
        significance={
            "method": "bootstrap",
            "pairs": [["base", "new"], ["base", "absent"], ["new", "absent"]],
            "correction": correction,
        },
    )
    module.compare = lambda a, b: 0.02
    module.RUN_REPORT = module.new_report()
    fig, ax = plt.subplots()
    try:
        module.mark_significance(ax, data(), ["base", "new"], [0, 1])
        records = module.RUN_REPORT["significance"]
        tested = next(item for item in records if item["status"] == "tested")
        assert tested["raw_p"] == 0.02 and tested["adjusted_p"] == pytest.approx(0.06)
        assert tested["family_size"] == 3 and tested["tested_family_size"] == 1
        assert sum(item["status"] == "untested" for item in records) == 2
        assert ax.texts[0].get_text() == "n.s."
    finally:
        plt.close(fig)


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
def test_actual_strict_cli_preserves_design_and_exports(tmp_path, orientation):
    _, path = generated(tmp_path, orientation=orientation)
    data().to_csv(tmp_path / "data.csv", index=False)
    run = subprocess.run(
        [sys.executable, str(path), "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(run.stdout)
    assert run.returncode == 0, report
    assert report["status"] == "passed" and report["policy"]["strict"]
    assert report["significance"][0]["raw_p"] == 2 / 16
    assert report["significance"][0]["matched_pairs"] == 4
    assert {item["format"] for item in report["outputs"]} == {"png", "svg"}


def test_single_complete_pair_is_strict_incomplete_not_significant(tmp_path):
    _, path = generated(tmp_path)
    pd.DataFrame(
        {
            "condition": ["base", "base", "new", "new"],
            "unit": ["A", "B", "A", "C"],
            "score": [10, 20, 12, 35],
        }
    ).to_csv(tmp_path / "data.csv", index=False)
    run = subprocess.run(
        [sys.executable, str(path), "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(run.stdout)
    assert run.returncode == 2 and report["status"] == "incomplete", report
    assert report["significance"][0]["matched_pairs"] == 1
    assert report["significance"][0]["status"] == "untested"


def test_missing_pair_ids_are_counted_in_actual_cli(tmp_path):
    _, path = generated(tmp_path)
    frame = pd.concat([data(), pd.DataFrame([{"condition": "new", "score": 1000, "unit": None}])])
    frame.to_csv(tmp_path / "data.csv", index=False)
    run = subprocess.run(
        [sys.executable, str(path), "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(run.stdout)
    assert run.returncode == 0, report
    assert report["significance"][0]["missing_pair_ids"] == 1
    assert report["significance"][0]["raw_p"] == 2 / 16
