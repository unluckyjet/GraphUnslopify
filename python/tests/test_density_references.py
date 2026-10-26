"""Known Gaussian quantities and visible observations for unavailable ridgeline fits."""

from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from graphunslopify.transport import local_request


def spec(**extra):
    return {
        "kind": "ridgeline",
        "data": {"path": "data.csv"},
        "x": {"field": "category", "label": "Category"},
        "y": {"field": "value", "label": "Measurement"},
        "legend": {"show": False},
        "output": {"stem": "ridge", "formats": ["png"], "size": "double_column"},
        **extra,
    }


def generated(tmp_path, **extra):
    r = local_request("convert", spec(**extra))
    assert r["ok"], r
    path = tmp_path / "ridge.py"
    path.write_text(r["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("density_reference", path)
    m = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(m)
    return m


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.mark.parametrize(
    "values", [[], [5], [5, 5, 5], [0.05, 0.05, 0.05], [np.nan], [np.inf, -np.inf]]
)
def test_unavailable_bandwidth_is_not_a_zero_density(tmp_path, values):
    m = generated(tmp_path)
    grid = np.array([4.0, 5.0, 6.0])
    sample = np.array(values, dtype=float)
    assert m._density_bandwidth(sample) is None
    assert np.isnan(m._gaussian_density(sample, grid)).all()


def test_hand_gaussian_reference_and_actual_peak_normalized_profile(tmp_path):
    m = generated(tmp_path)
    values = np.array([0.0, 1.0, 2.0])
    grid = np.array([-0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5])
    # Hand sample sd=1, IQR=1 for [0,1,2], with the documented normal-IQR rule.
    h = 0.9 / 1.349 * 3 ** (-1 / 5)
    expected = [
        sum(math.exp(-0.5 * ((x - v) / h) ** 2) for v in [0, 1, 2])
        / (3 * h * math.sqrt(2 * math.pi))
        for x in grid
    ]
    assert m._density_bandwidth(values) == pytest.approx(h, rel=1e-14)
    np.testing.assert_allclose(m._gaussian_density(values, grid), expected, rtol=1e-14)
    _, ax = plt.subplots()
    m.draw_panel(ax, pd.DataFrame({"category": ["01"] * 3, "value": values}))
    line = ax.lines[0]
    xs = np.asarray(line.get_xdata())
    oracle = np.array(
        [
            sum(math.exp(-0.5 * ((x - v) / h) ** 2) for v in [0, 1, 2])
            / (3 * h * math.sqrt(2 * math.pi))
            for x in xs
        ]
    )
    np.testing.assert_allclose(
        line.get_ydata(), 0.92 * oracle / oracle.max(), rtol=1e-12, atol=1e-14
    )
    record = m.ROW_COUNTS["densities"][0]
    assert record["category"] == "01" and record["n"] == 3 and record["status"] == "available"
    assert record["bandwidth"] == pytest.approx(h) and record["peak_normalized"] is True


def test_independent_scipy_density_reference(tmp_path):
    stats = pytest.importorskip("scipy.stats")
    m = generated(tmp_path)
    sample = np.array([0.0, 1.0, 2.0, 4.0])
    grid = np.linspace(-2, 6, 41)
    sd = math.sqrt(35 / 12)
    h = 0.9 * min(sd, 1.75 / 1.349) * 4 ** (-1 / 5)
    expected = stats.gaussian_kde(sample, bw_method=h / sd)(grid)
    np.testing.assert_allclose(m._gaussian_density(sample, grid), expected, rtol=2e-14, atol=1e-15)


@pytest.mark.parametrize("values", [[5], [5, 5, 5], [0, 0, 0], [-5, -5, -5]])
def test_unavailable_density_retains_actual_values_and_visible_context(tmp_path, values):
    m = generated(tmp_path)
    _, ax = plt.subplots()
    m.draw_panel(ax, pd.DataFrame({"category": ["01"] * len(values), "value": values}))
    assert any(
        line.get_marker() == "|" and set(line.get_xdata()) == set(values) for line in ax.lines
    )
    assert min(ax.get_xlim()) <= min(values) <= max(ax.get_xlim())
    assert any("density unavailable" in t.get_text().lower() for t in ax.texts)
    assert any(f["code"] == "density_unavailable" for f in m.RUN_REPORT["findings"])
    assert m.RUN_REPORT["untested"]
    record = m.ROW_COUNTS["densities"][0]
    assert (
        record["n"] == len(values)
        and record["bandwidth"] is None
        and record["status"] == "unavailable"
    )


def test_nonfinite_measurements_do_not_create_a_fake_density_or_domain(tmp_path):
    m = generated(tmp_path)
    _, ax = plt.subplots()
    m.draw_panel(ax, pd.DataFrame({"category": ["A"] * 4, "value": [5, np.inf, np.nan, -np.inf]}))
    record = m.ROW_COUNTS["densities"][0]
    assert record["n"] == 1 and record["nonfinite"] == 3
    assert any(line.get_marker() == "|" and list(line.get_xdata()) == [5] for line in ax.lines)
    assert all(np.isfinite(ax.get_xlim()))


def test_all_nonfinite_values_fail_clearly(tmp_path):
    m = generated(tmp_path)
    _, ax = plt.subplots()
    with pytest.raises(ValueError, match="finite measurement"):
        m.draw_panel(ax, pd.DataFrame({"category": ["A", "A"], "value": [np.nan, np.inf]}))


def test_absent_shared_slots_do_not_become_unavailable_observations(tmp_path):
    m = generated(
        tmp_path, category_order=["B", "01", "unused"], facet={"by": "site", "share_y": True}
    )
    _, ax = plt.subplots()
    m.draw_panel(ax, pd.DataFrame({"category": ["01"] * 3, "value": [0, 1, 2]}))
    assert [r["category"] for r in m.ROW_COUNTS["densities"]] == ["01"]
    assert not m.RUN_REPORT["untested"]


@pytest.mark.parametrize(
    "values,status,code",
    [([5, 5, 5], "incomplete", 2), ([5], "incomplete", 2), ([0, 1, 2], "passed", 0)],
)
def test_actual_strict_export_reports_density_evidence(tmp_path, values, status, code):
    m = generated(tmp_path)
    pd.DataFrame({"category": ["A"] * len(values), "value": values}).to_csv(
        tmp_path / "data.csv", index=False, lineterminator="\n"
    )
    result = subprocess.run(
        [sys.executable, m.__file__, "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    r = json.loads(result.stdout)
    assert result.returncode == code and r["status"] == status
    assert r["outputs"] and r["inspection"]["checked"]
    assert r["data"]["counts"]["densities"][0]["n"] == len(values)
    assert ("density unavailable" in r["alt_text"].lower()) == (status == "incomplete")


def test_zero_iqr_uses_positive_sample_spread_without_inventing_a_constant_bandwidth(tmp_path):
    m = generated(tmp_path)
    sample = np.array([0.0, 0.0, 0.0, 0.0, 10.0])
    assert m._density_bandwidth(sample) == pytest.approx(0.9 * math.sqrt(20) * 5 ** (-1 / 5))


@pytest.mark.parametrize("scale", [-2.0, 1000.0])
def test_density_respects_affine_measurement_units(tmp_path, scale):
    m = generated(tmp_path)
    sample = np.array([0.0, 1.0, 2.0])
    grid = np.linspace(-1, 3, 31)
    np.testing.assert_allclose(
        m._gaussian_density(scale * sample + 10, scale * grid + 10),
        m._gaussian_density(sample, grid) / abs(scale),
        rtol=1e-12,
        atol=1e-14,
    )
    assert m._density_bandwidth(scale * sample + 10) == pytest.approx(
        abs(scale) * m._density_bandwidth(sample)
    )


def test_observed_invalid_category_stays_unavailable_and_input_is_unchanged(tmp_path):
    m = generated(tmp_path)
    _, ax = plt.subplots()
    df = pd.DataFrame({"category": ["A", "A", "B", "B", "B"], "value": ["bad", np.nan, 0, 1, 2]})
    original = df.copy(deep=True)
    m.draw_panel(ax, df)
    records = {r["category"]: r for r in m.ROW_COUNTS["densities"]}
    assert (
        records["A"]["status"] == "unavailable"
        and records["A"]["n"] == 0
        and records["A"]["nonfinite"] == 2
    )
    assert records["B"]["status"] == "available" and records["B"]["n"] == 3
    assert any("no finite observations" in t.get_text() for t in ax.texts)
    pd.testing.assert_frame_equal(df, original)


def test_percent_descriptions_match_the_visible_observation_units(tmp_path):
    m = generated(tmp_path, y={"field": "value", "label": "Accuracy", "unit": "%", "percent": True})
    df = pd.DataFrame({"category": ["A"] * 3, "value": [0.05] * 3})
    _, ax = plt.subplots()
    m.draw_panel(ax, df)
    assert "observations range from 5% to 5%" in m.describe_figure(df).lower()
    assert m.ROW_COUNTS["densities"][0]["bandwidth"] is None


def test_scoped_profiles_and_descriptions_match_each_actual_facet(tmp_path, monkeypatch):
    m = generated(tmp_path, facet={"by": "site", "columns": 2, "share_x": False, "share_y": True})
    data = pd.DataFrame(
        {
            "category": ["01"] * 6,
            "value": [0, 1, 2, 5, 5, 5],
            "site": ["normal"] * 3 + ["constant"] * 3,
        }
    )
    data.to_csv(tmp_path / "data.csv", index=False, lineterminator="\n")
    monkeypatch.chdir(tmp_path)
    m.main()
    records = m.ROW_COUNTS["densities"]
    assert {(r["panel"], r["category"], r["status"]) for r in records} == {
        (0, "01", "available"),
        (1, "01", "unavailable"),
    }
    normal, constant = m.ALT_TEXT.lower().split("panel constant:")
    assert "gaussian density" in normal and "density unavailable" not in normal
    assert "density unavailable" in constant and "observations range from 5 to 5" in constant


def test_published_density_example_has_committed_inputs_and_current_fingerprints():
    import hashlib
    from pathlib import Path

    from graphunslopify import read_provenance

    root = Path(__file__).resolve().parents[2]
    folder = root / "examples/references"
    raw = json.loads((folder / "density.figure.json").read_text())
    r = local_request("convert", raw)
    assert r["ok"]
    data = (folder / "density.csv").read_bytes()
    assert b"\r" not in data
    evidence = read_provenance(root / "docs/density-evidence.png")
    assert evidence["data_sha256_prefix"] == hashlib.sha256(data).hexdigest()[:16]
    assert evidence["script_sha256"] == hashlib.sha256(r["code"].encode()).hexdigest()
    assert (
        "density unavailable" in evidence["alt_text"].lower()
        and "gaussian density" in evidence["alt_text"].lower()
    )
