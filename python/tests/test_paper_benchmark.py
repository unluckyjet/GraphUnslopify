"""Protect scientific benchmark accounting and actual drawn-point measurements."""

from __future__ import annotations

import runpy
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
PILOT = runpy.run_path(str(ROOT / "scripts/paper-benchmark.py"))


def test_paper_comparison_rejects_group_swaps_even_with_equal_numbers():
    with pytest.raises(AssertionError, match="identity"):
        PILOT["compare"](
            [{"x": "species", "group": "female", "mean": 5, "low": 4, "high": 6}],
            [{"x": "species", "group": "male", "mean": 5, "low": 4, "high": 6}],
        )


def test_paper_comparison_does_not_count_masked_offsets_as_drawn_points():
    figure, axes = plt.subplots()
    try:
        axes.scatter([1, 2, np.nan], [1, np.nan, 3], label="series")
        assert PILOT["REFERENCE"]["scatter_artists"](axes) == [
            {"x": 1.0, "y": 1.0, "group": "series"}
        ]
    finally:
        plt.close(figure)


def test_paper_comparison_rejects_missing_interval_endpoints():
    with pytest.raises(AssertionError, match="quantity"):
        PILOT["compare"](
            [{"x": "species", "group": "male", "mean": 5, "low": None, "high": None}],
            [{"x": "species", "group": "male", "mean": 5, "low": 4, "high": 6}],
        )


def test_scatter_oracle_is_independent_of_shared_artist_omissions(tmp_path):
    (tmp_path / "data.csv").write_text("x,y,series\n1,2,one\n3,4,one\n5,NA,one\n")
    spec = {
        "kind": "scatter",
        "data": {"path": "data.csv"},
        "x": {"field": "x"},
        "y": {"field": "y"},
        "group": "series",
    }
    expected = PILOT["expected_artists"](spec, tmp_path)
    assert expected == [{"x": 1.0, "y": 2.0, "group": "one"}, {"x": 3.0, "y": 4.0, "group": "one"}]
    # Even if both artist probes lose the same point, source-data truth retains it.
    for omitted in (expected[:1], expected[:1]):
        with pytest.raises(AssertionError, match="count differs"):
            PILOT["compare"](omitted, expected)
