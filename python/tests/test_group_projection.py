"""Declared comparisons cannot disappear or acquire an unrequested estimator."""

from __future__ import annotations

import importlib.util

import numpy as np
import pandas as pd
import pytest

from graphunslopify.transport import local_request

IGNORED_GROUP_KINDS = [
    "box",
    "violin",
    "raincloud",
    "ridgeline",
    "forest",
    "heatmap",
    "confusion_matrix",
    "waterfall",
]


def spec(kind="table", **extra):
    matrix = kind in {"heatmap", "confusion_matrix"}
    return {
        "kind": kind,
        "data": {"path": "data.csv"},
        "x": {"field": "category", "label": "Category"},
        "y": {"field": "row" if matrix else "value", "label": "Value"},
        "group": "method",
        **({"uncertainty": {"kind": "range"}} if kind == "forest" else {}),
        **({"value": "measurement", "value_label": "Measurement"} if kind == "heatmap" else {}),
        **({"value": "measurement", "normalize": "none"} if kind == "confusion_matrix" else {}),
        **({"start": 0, "category_order": ["A", "B"]} if kind == "waterfall" else {}),
        **extra,
    }


def generated(tmp_path, raw, *, allow_errors=False):
    r = local_request("convert", raw)
    assert r["ok"] or allow_errors, r
    p = tmp_path / "plot.py"
    p.write_text(r["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("projection_reference", p)
    m = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(m)
    return m


@pytest.mark.parametrize("kind", IGNORED_GROUP_KINDS)
@pytest.mark.parametrize("wide", [True, False])
def test_unused_comparison_groups_are_explicit_errors(kind, wide):
    raw = spec(kind)
    if wide:
        raw.pop("group")
        raw["series_from_columns"] = {
            "fields": ["first", "second"],
            "series_name": "method",
            "value_name": "measurement" if kind in {"heatmap", "confusion_matrix"} else "value",
        }
    r = local_request("convert", raw)
    assert not r["ok"]
    assert any(
        f["code"] == "unsupported_grouping" and f["severity"] == "error" for f in r["findings"]
    )


@pytest.mark.parametrize("kind", IGNORED_GROUP_KINDS)
def test_refused_generated_main_cannot_silently_run_the_projection(tmp_path, kind):
    m = generated(tmp_path, spec(kind), allow_errors=True)
    with pytest.raises(ValueError, match="Unsupported grouping"):
        m.main()


@pytest.mark.parametrize("kind", IGNORED_GROUP_KINDS)
def test_explicitly_unset_groups_keep_pooling_available(kind):
    raw = spec(kind)
    raw.pop("group")
    assert local_request("convert", raw)["ok"]


@pytest.mark.parametrize(
    "aggregation,expected", [("mean", 5), ("median", 5), ("sum", 10), ("count", 2), ("none", None)]
)
def test_grouped_table_cell_estimator_is_explicit(tmp_path, aggregation, expected):
    m = generated(tmp_path, spec(aggregation=aggregation))
    df = pd.DataFrame({"category": ["A", "A"], "value": [1, 9], "method": ["first", "first"]})
    original = df.copy(deep=True)
    if expected is None:
        with pytest.raises(ValueError, match="Duplicate table cell"):
            m.build_table(df)
    else:
        table, _, _ = m.build_table(df)
        assert table.loc["A", "first"] == expected
    pd.testing.assert_frame_equal(df, original)


def test_unique_grouped_raw_cells_preserve_exact_values(tmp_path):
    m = generated(tmp_path, spec(aggregation="none"))
    df = pd.DataFrame({"category": ["A", "A"], "value": [1, 9], "method": ["first", "second"]})
    table, _, _ = m.build_table(df)
    assert list(table.columns) == ["first", "second"]
    np.testing.assert_array_equal(table.values, [[1, 9]])


def test_ungrouped_raw_rows_do_not_acquire_an_implicit_estimator(tmp_path):
    raw = spec(aggregation="none")
    raw.pop("group")
    m = generated(tmp_path, raw)
    table, _, _ = m.build_table(pd.DataFrame({"category": ["A", "A"], "value": [1, 9]}))
    assert list(table.index) == ["A", "A"]
    np.testing.assert_array_equal(table.values, [[1], [9]])


@pytest.mark.parametrize(
    "kind",
    [
        "line",
        "scatter",
        "bar",
        "ecdf",
        "slope",
        "dumbbell",
        "calibration",
        "qq",
        "kaplan_meier",
        "scaling_fit",
        "sparkline_grid",
        "table",
    ],
)
def test_kinds_with_series_implementations_keep_group_declarations(kind):
    raw = spec(kind)
    if kind == "bar":
        raw["aggregation"] = "mean"
    if kind == "calibration":
        raw["outcome"] = "outcome"
    if kind == "kaplan_meier":
        raw["event"] = "event"
    if kind == "scaling_fit":
        raw["x"]["scale"] = "log"
        raw["y"]["scale"] = "log"
    assert local_request("convert", raw)["ok"]


@pytest.mark.parametrize(
    "aggregation,wording",
    [("none", "rows identified by category"), ("mean", "one row per category")],
)
def test_raw_row_descriptions_do_not_promise_unique_row_identifiers(tmp_path, aggregation, wording):
    raw = spec(aggregation=aggregation)
    raw.pop("group")
    m = generated(tmp_path, raw)
    assert wording in m.ENCODING_SENTENCE.lower()
