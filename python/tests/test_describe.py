"""Profiling has to be right, because a spec is written from what it reports.

The failure that matters most is missing that x repeats per series, because the
resulting figure renders happily and draws a sawtooth.
"""

from __future__ import annotations

import json

import pytest

from graphunslopify.cli import main
from graphunslopify.describe import profile


@pytest.fixture
def training(tmp_path):
    path = tmp_path / "training.csv"
    rows = ["model,seed,epoch,accuracy,note"]
    for model in ("baseline", "ours"):
        for seed in range(3):
            for epoch in range(1, 11):
                score = 50 + epoch * 2.3 + seed * 0.7
                rows.append(f"{model},{seed},{epoch},{score:.3f},run-{model}-{seed}-{epoch}")
    path.write_text("\n".join(rows) + "\n", encoding="utf8")
    return path


def test_a_missing_file_is_reported_not_raised(tmp_path):
    report = profile(tmp_path / "nope.csv")
    assert report["ok"] is False
    assert "no such file" in report["error"]


def test_columns_are_given_a_role(training):
    roles = {c["name"]: c["role"] for c in profile(training)["columns"]}
    assert roles["model"] == "category"
    assert roles["epoch"] == "ordinal"
    assert roles["accuracy"] == "measure"
    assert roles["note"] == "identifier"


def test_small_category_sets_list_their_values(training):
    columns = {c["name"]: c for c in profile(training)["columns"]}
    assert set(columns["model"]["values"]) == {"baseline", "ours"}
    assert "values" not in columns["note"]


def test_numeric_columns_carry_their_range(training):
    accuracy = next(c for c in profile(training)["columns"] if c["name"] == "accuracy")
    assert accuracy["min"] == pytest.approx(52.3)
    assert accuracy["max"] == pytest.approx(74.4)


def test_repeated_x_per_series_is_reported(training):
    report = profile(training)
    pairs = {(r["x"], r["group"]) for r in report["repeats"]}
    assert ("epoch", "model") in pairs


def test_the_suggestion_picks_the_curve_axis_not_the_replicate(training):
    suggested = profile(training)["suggested"]
    assert suggested["x"] == "epoch"
    assert suggested["y"] == "accuracy"
    assert suggested["group"] == "model"


def test_the_suggestion_asks_for_aggregation_when_x_repeats(training):
    suggested = profile(training)["suggested"]
    assert suggested["aggregation"] == "mean"
    assert suggested["uncertainty"]["over"] == "seed"
    assert "repeat" in suggested["note"]


def test_no_aggregation_is_suggested_when_nothing_repeats(tmp_path):
    path = tmp_path / "clean.csv"
    rows = ["model,epoch,accuracy"]
    for model in ("a", "b"):
        for epoch in range(1, 6):
            rows.append(f"{model},{epoch},{epoch * 3.5:.2f}")
    path.write_text("\n".join(rows) + "\n", encoding="utf8")

    suggested = profile(path)["suggested"]
    assert "aggregation" not in suggested


def test_the_cli_prints_json(training, capsys):
    assert main(["describe", str(training)]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["ok"] is True
    assert "epoch" in parsed["column_names"]


def test_the_cli_reports_a_missing_file_without_crashing(tmp_path, capsys):
    assert main(["describe", str(tmp_path / "absent.csv")]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_profile_counts_missing_and_nonfinite_values_without_rewriting_data(tmp_path, capsys):
    path = tmp_path / "measurements.csv"
    content = "group,value\na,2\nb,inf\nc,-inf\nd,\ne,4\n"
    path.write_text(content)
    assert main(["describe", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    numeric = next(c for c in result["columns"] if c["name"] == "value")
    assert (
        numeric["missing"],
        numeric["non_missing"],
        numeric["finite"],
        numeric["nonfinite"],
    ) == (1, 4, 2, 2)
    assert (numeric["min"], numeric["max"], numeric["mean"]) == (2, 4, 3)
    assert numeric["numeric_summary_scope"] == "finite values only"
    assert "independent experimental" in result["inference_note"]
    assert path.read_text() == content
    json.dumps(result, allow_nan=False)


def test_a_nonfinite_only_column_is_not_suggested_as_a_usable_measure(tmp_path):
    path = tmp_path / "unavailable.csv"
    path.write_text("label,value\na,inf\nb,-inf\nc,\n")
    result = profile(path)
    column = next(c for c in result["columns"] if c["name"] == "value")
    assert column["finite"] == 0 and column["nonfinite"] == 2
    assert "mean" not in column and not result["suggested"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("value", [1e308, 1e-323])
def test_finite_means_preserve_extreme_magnitudes(tmp_path, value):
    path = tmp_path / "extreme.csv"
    path.write_text("value\n" + f"{value}\n" * 8)
    result = profile(path)
    assert result["columns"][0]["mean"] == pytest.approx(value, rel=1e-15, abs=0)
    json.dumps(result, allow_nan=False)


def test_datetime_categories_are_serializable_without_mutating_the_table(tmp_path):
    import pandas as pd

    path = tmp_path / "dates.parquet"
    pytest.importorskip("pyarrow")
    frame = pd.DataFrame(
        {"date": pd.to_datetime(["2026-01-01", "2026-01-02"]), "value": [3.0, 5.0]}
    )
    frame.to_parquet(path)
    raw = path.read_bytes()
    result = profile(path)
    assert result["columns"][0]["values"] == ["2026-01-01T00:00:00", "2026-01-02T00:00:00"]
    json.dumps(result, allow_nan=False)
    assert path.read_bytes() == raw


def test_wide_categorical_tables_disclose_bounded_repeat_probing(tmp_path):
    path = tmp_path / "wide.csv"
    path.write_text(
        ",".join(f"field{i}" for i in range(40))
        + "\n"
        + ",".join("a" for _ in range(40))
        + "\n"
        + ",".join("b" for _ in range(40))
        + "\n"
    )
    result = profile(path)
    assert result["repeat_scan"] == {
        "x_columns_checked": 16,
        "group_columns_checked": 16,
        "truncated": True,
    }
