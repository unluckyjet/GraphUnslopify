"""Hand-calculated binned probabilities/rates must own calibration evidence."""

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
    "kind": "calibration",
    "x": {"field": "prob", "label": "Predicted probability"},
    "y": {"field": "frequency", "label": "Observed frequency"},
    "outcome": "flag",
    "bins": 3,
    "legend": {"show": False},
    "output": {"stem": "calibration", "formats": ["png", "svg"], "dpi": 100},
}


def generated(folder, **extra):
    spec = {**BASE, "data": {"path": str(folder / "data.csv")}, **extra}
    if extra.get("group") and "legend" not in extra:
        spec["legend"] = {"position": "outside_bottom"}
    result = local_request("convert", spec)
    assert result.get("ok"), result
    path = folder / "calibration.py"
    path.write_text(result["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("calibration_reference", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module, path


@pytest.fixture(scope="module")
def emitted(tmp_path_factory):
    return generated(tmp_path_factory.mktemp("calibration-reference"))[0]


def plotted(module, frame):
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, frame)
        return [
            (
                np.asarray(line.get_xdata(), dtype=float),
                np.asarray(line.get_ydata(), dtype=float),
                line.get_label(),
            )
            for line in ax.lines
        ]
    finally:
        plt.close(fig)


@pytest.mark.parametrize(
    ("bins", "prob", "flag", "means", "rates", "counts", "ece"),
    [
        (3, [0.1, 0.2, 0.6, 0.9], [0, 1, 1, 0], [0.15, 0.6, 0.9], [0.5, 1, 0], [2, 1, 1], 0.5),
        (
            4,
            [0, 0.25, 0.5, 0.75, 1],
            [0, 1, 0, 1, 1],
            [0.125, 0.5, 0.75, 1],
            [0.5, 0, 1, 1],
            [2, 1, 1, 1],
            0.3,
        ),
        (5, [0.05, 0.1, 0.95], [0, 0, 1], [0.075, 0.95], [0, 1], [2, 1], 1 / 15),
        (3, [0, 1], [0, 1], [0, 1], [0, 1], [1, 1], 0),
    ],
)
def test_actual_points_counts_and_ece_match_hand_answers(
    tmp_path, bins, prob, flag, means, rates, counts, ece
):
    module, _ = generated(tmp_path, bins=bins)
    frame = pd.DataFrame({"prob": prob, "flag": flag})
    curve = module.calibration_estimate(frame)
    np.testing.assert_allclose(curve["probability"], means, rtol=0, atol=1e-12)
    np.testing.assert_allclose(curve["frequency"], rates, rtol=0, atol=1e-12)
    assert list(curve["counts"]) == counts
    assert curve["ece"] == pytest.approx(ece, rel=0, abs=1e-12)
    lines = plotted(module, frame)
    assert len(lines) == 2
    np.testing.assert_allclose(lines[0][0], means, rtol=0, atol=1e-12)
    np.testing.assert_allclose(lines[0][1], rates, rtol=0, atol=1e-12)
    np.testing.assert_array_equal(lines[1][0], [0, 1])
    np.testing.assert_array_equal(lines[1][1], [0, 1])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("prob", -0.01),
        ("prob", 1.01),
        ("prob", np.nan),
        ("prob", np.inf),
        ("prob", "invalid"),
        ("flag", -1),
        ("flag", 0.5),
        ("flag", 2),
        ("flag", np.nan),
        ("flag", np.inf),
    ],
)
def test_invalid_probability_or_binary_outcome_fails_without_clipping_or_dropping(
    emitted, field, value
):
    frame = pd.DataFrame({"prob": [0.1, 0.2, 0.6, 0.9], "flag": [0, 1, 1, 0]}).astype(object)
    frame.loc[0, field] = value
    with pytest.raises(ValueError, match="Calibration"):
        emitted.prepare(frame)
    with pytest.raises(ValueError, match="Calibration"):
        plotted(emitted, frame)


def test_permuting_rows_preserves_the_binned_estimate(emitted):
    frame = pd.DataFrame({"prob": [0.1, 0.2, 0.6, 0.9], "flag": [0, 1, 1, 0]})
    for order in itertools.permutations(range(4)):
        curve = emitted.calibration_estimate(frame.iloc[list(order)])
        np.testing.assert_allclose(curve["probability"], [0.15, 0.6, 0.9], rtol=0, atol=1e-12)
        np.testing.assert_allclose(curve["frequency"], [0.5, 1, 0], rtol=0, atol=1e-12)
        assert curve["ece"] == pytest.approx(0.5, rel=0, abs=1e-12)


def test_description_uses_binned_error_observations_and_occupancy(emitted):
    text = emitted.alt_text(pd.DataFrame({"prob": [0.1, 0.2, 0.6, 0.9], "flag": [0, 1, 1, 0]}))
    assert "expected calibration error is 0.5" in text.lower()
    assert "4 observations" in text and "3 of 3 bins" in text
    assert "median" not in text.lower()
    assert "0.15" in text and "0.9" in text


def test_tiny_nonzero_error_does_not_display_as_perfect_calibration(tmp_path):
    module, _ = generated(tmp_path, group="model")
    frame = pd.DataFrame({"prob": [0.00001], "flag": [0], "model": ["tiny"]})
    lines = plotted(module, frame)
    assert "1e-05" in lines[0][2]
    assert "1e-05" in module.alt_text(frame)


def test_empty_input_has_no_valid_calibration_estimate(emitted):
    with pytest.raises(ValueError, match="Calibration"):
        emitted.prepare(pd.DataFrame({"prob": [], "flag": []}))


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


def cohorts(first, second):
    return pd.concat(
        [
            pd.DataFrame({"prob": [0.1, 0.2, 0.7, 0.8], "flag": first, "model": "baseline"}),
            pd.DataFrame({"prob": [0.1, 0.2, 0.7, 0.8], "flag": second, "model": "candidate"}),
        ]
    )


def test_claim_uses_plotted_bin_frequencies_not_raw_last_event(tmp_path):
    process, report = rendered(
        tmp_path,
        cohorts([1, 0, 1, 0], [0, 1, 0, 1]),
        group="model",
        y={"field": "flag", "label": "Observed frequency"},
        claims=[{"kind": "beats_at_end", "subject": "candidate", "reference": "baseline"}],
    )
    assert process.returncode == 2 and report["claims"][0]["verdict"] == "fails"
    assert report["claims"][0]["detail"].endswith("+0")
    assert report["outputs"]


def test_aligned_derived_claims_and_provenance_match_actual_calibration(tmp_path):
    process, report = rendered(
        tmp_path,
        cohorts([0, 0, 0, 0], [1, 1, 1, 1]),
        group="model",
        claims=[{"kind": "beats_at_end", "subject": "candidate", "reference": "baseline"}],
    )
    assert process.returncode == 0, process.stderr
    assert report["claims"][0]["verdict"] == "holds"
    assert "expected calibration error" in report["alt_text"].lower()
    for suffix in ["png", "svg"]:
        evidence = read_provenance(tmp_path / ("calibration." + suffix))
        assert (
            evidence["alt_text"] == report["alt_text"]
            and evidence["spec_hash"] == report["spec_hash"]
        )


@pytest.mark.parametrize("shift", [0.01, 2e-12])
def test_different_plotted_x_means_are_not_interpolated_into_comparable_points(tmp_path, shift):
    rows = pd.concat(
        [
            pd.DataFrame({"prob": [0.1, 0.2], "flag": [0, 0], "model": "baseline"}),
            pd.DataFrame(
                {"prob": [0.1 + shift, 0.2 + shift], "flag": [1, 1], "model": "candidate"}
            ),
        ]
    )
    process, report = rendered(
        tmp_path,
        rows,
        group="model",
        claims=[{"kind": "beats_at_end", "subject": "candidate", "reference": "baseline"}],
    )
    assert process.returncode == 2 and report["claims"][0]["verdict"] == "untested"
    assert report["outputs"] and not any(f["code"] == "runtime_error" for f in report["findings"])


def test_invalid_domain_has_failed_report_and_no_artifacts(tmp_path):
    process, report = rendered(tmp_path, pd.DataFrame({"prob": [-0.1, 0.9], "flag": [0, 1]}))
    assert process.returncode == 1 and report["status"] == "failed" and not report["outputs"]
    assert any("Calibration" in f["message"] for f in report["findings"])


def test_filter_runs_before_domain_validation(tmp_path):
    module, _ = generated(tmp_path, filter=[{"field": "keep", "op": "eq", "value": 1}])
    retained = module.prepare(pd.DataFrame({"prob": [-1, 0.2], "flag": [0.5, 1], "keep": [0, 1]}))
    assert module.calibration_estimate(retained)["observations"] == 1


def test_missing_series_label_is_not_silently_omitted(tmp_path):
    module, _ = generated(tmp_path, group="model")
    with pytest.raises(ValueError, match="identifier model"):
        module.prepare(pd.DataFrame({"prob": [0.1, 0.2], "flag": [0, 1], "model": ["A", None]}))


@pytest.mark.parametrize(
    "extra",
    [
        {"transform": {"kind": "normalize"}},
        {
            "group": "model",
            "y": {"field": "prob", "label": "Frequency"},
            "claims": [{"kind": "monotone_increasing", "subject": "A"}],
        },
    ],
)
def test_undefined_transform_or_ambiguous_claim_roles_are_static_errors(extra):
    result = local_request("convert", {**BASE, **extra})
    assert result["status"] == "translated" and not result["ok"]
    assert any(f["code"] == "unsupported_calibration_semantics" for f in result["findings"])


def test_faceted_calibration_claims_and_descriptions_are_panel_scoped(tmp_path):
    first = cohorts([0, 0, 0, 0], [1, 1, 1, 1])
    second = cohorts([1, 1, 1, 1], [0, 0, 0, 0])
    rows = pd.concat([first.assign(site="first"), second.assign(site="second")])
    process, report = rendered(
        tmp_path,
        rows,
        group="model",
        facet={"by": "site", "columns": 2},
        output={"stem": "calibration", "formats": ["png"], "size": "double_column", "dpi": 100},
        claims=[{"kind": "beats_at_end", "subject": "candidate", "reference": "baseline"}],
    )
    assert process.returncode == 2
    assert [(c["panel"], c["verdict"]) for c in report["claims"]] == [(0, "holds"), (1, "fails")]
    assert report["data"]["counts"]["read"] == 16
    assert "Panel first" in report["alt_text"] and "Panel second" in report["alt_text"]
    assert report["outputs"]


def test_claim_alignment_tolerates_only_roundoff_from_row_permutation(tmp_path):
    first = pd.DataFrame({"prob": [0.1, 0.2, 0.3, 0.4], "flag": 0, "model": "baseline"})
    second = pd.DataFrame({"prob": [0.4, 0.3, 0.2, 0.1], "flag": 1, "model": "candidate"})
    process, report = rendered(
        tmp_path,
        pd.concat([first, second]),
        group="model",
        claims=[{"kind": "beats_at_end", "subject": "candidate", "reference": "baseline"}],
    )
    assert process.returncode == 0, process.stderr
    assert report["claims"][0]["verdict"] == "holds"


def test_actual_faceted_legends_use_each_panels_error(tmp_path, monkeypatch):
    module, _ = generated(
        tmp_path,
        group="model",
        facet={"by": "site", "columns": 2},
        output={"stem": "calibration", "formats": ["png"], "size": "double_column", "dpi": 100},
    )
    rows = pd.concat(
        [
            cohorts([0, 0, 0, 0], [1, 1, 1, 1]).assign(site="first"),
            cohorts([1, 1, 1, 1], [0, 0, 0, 0]).assign(site="second"),
        ]
    )
    rows.to_csv(tmp_path / "data.csv", index=False)
    captured = []
    close = plt.close
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(plt, "close", captured.append)
    try:
        module.main()
        fig = captured[-1]
        actual = [[text.get_text() for text in ax.get_legend().get_texts()] for ax in fig.axes]
        assert actual == [
            ["baseline (ECE 0.45)", "candidate (ECE 0.55)"],
            ["baseline (ECE 0.55)", "candidate (ECE 0.45)"],
        ]
        fig.canvas.draw()
        boxes = [ax.get_legend().get_window_extent(fig.canvas.get_renderer()) for ax in fig.axes]
        assert not boxes[0].overlaps(boxes[1])
        assert (tmp_path / "calibration.png").is_file()
    finally:
        for fig in captured:
            close(fig)


def test_direct_labels_use_derived_endpoints_and_error_without_a_raw_y_column(tmp_path):
    module, _ = generated(tmp_path, group="model", legend={"style": "direct"})
    rows = cohorts([0, 0, 0, 0], [1, 1, 1, 1])
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, rows)
        module.add_legend(fig, ax, rows)
        assert [text.get_text() for text in ax.texts] == [
            "baseline (ECE 0.45)",
            "candidate (ECE 0.55)",
        ]
        np.testing.assert_allclose(
            [text.xy for text in ax.texts], [[0.75, 0], [0.75, 1]], rtol=0, atol=1e-12
        )
    finally:
        plt.close(fig)
