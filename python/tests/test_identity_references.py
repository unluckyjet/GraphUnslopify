"""Identity must survive actual file loading, filtering, grouping and displayed marks."""

from __future__ import annotations

import hashlib
import importlib.util
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
    "kind": "line",
    "x": {"field": "step", "label": "Step"},
    "y": {"field": "score", "label": "Score"},
    "group": "model",
    "legend": {"show": False},
    "output": {"stem": "identity", "formats": ["png", "svg"], "dpi": 100},
}
CSV = "step,score,model\n1,10,01\n2,12,01\n1,20,1\n2,22,1\n"


def generated(folder, csv=CSV, **extra):
    data = folder / "data.csv"
    data.write_text(csv, encoding="utf8")
    spec = {**BASE, "data": {"path": str(data)}, **extra}
    spec = {key: value for key, value in spec.items() if value is not None}
    result = local_request("convert", spec)
    assert result.get("ok"), result
    path = folder / "identity.py"
    path.write_text(result["code"], encoding="utf8")
    definition = importlib.util.spec_from_file_location("identity_reference", path)
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module, path


def prepared(module):
    return module.prepare(module.load())


def test_leading_zero_cohorts_have_distinct_actual_lines_and_values(tmp_path):
    module, _ = generated(tmp_path, series_order=["01", "1"])
    frame = prepared(module)
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, frame)
        assert [(line.get_label(), list(line.get_ydata())) for line in ax.lines] == [
            ("01", [10, 12]),
            ("1", [20, 22]),
        ]
        assert module.series_names(frame) == ["01", "1"]
    finally:
        plt.close(fig)


def test_numeric_names_align_order_emphasis_claims_and_annotation_coordinates(tmp_path):
    module, _ = generated(
        tmp_path,
        csv=CSV.replace(",01", ",2"),
        series_order=["2", "1"],
        emphasis={"series": "1"},
        claims=[{"kind": "beats_everywhere", "subject": "1", "reference": "2"}],
        annotate=[{"at": "last", "series": "1", "text": "Candidate endpoint"}],
    )
    frame = prepared(module)
    assert module.series_names(frame) == ["2", "1"]
    assert module.check_claim(frame, module.CLAIMS[0])[0] is True
    assert module.locate(frame, "last", "1") == (2, 22)
    assert module.series_style("1", 1, 2)["alpha"] == 1
    assert module.series_style("2", 0, 2)["alpha"] < 1


@pytest.mark.parametrize("categories", ["01,1", "1,2"])
def test_category_order_has_actual_ordered_bars(tmp_path, categories):
    first, second = categories.split(",")
    module, _ = generated(
        tmp_path,
        csv=f"step,score\n{first},10\n{second},20\n",
        kind="bar",
        group=None,
        category_order=[second, first],
    )
    frame = prepared(module)
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, frame)
        assert module.category_order(frame) == [second, first]
        np.testing.assert_allclose([bar.get_height() for bar in ax.patches], [20, 10])
    finally:
        plt.close(fig)


def test_heatmap_preserves_both_label_axes_and_actual_cells(tmp_path):
    module, _ = generated(
        tmp_path,
        csv="step,score,value\n01,01,1\n1,01,2\n01,1,3\n1,1,4\n",
        kind="heatmap",
        group=None,
        value="value",
        value_label="Value",
    )
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, prepared(module))
        np.testing.assert_array_equal(ax.images[0].get_array(), [[1, 2], [3, 4]])
        assert [label.get_text() for label in ax.get_xticklabels()] == ["01", "1"]
        assert [label.get_text() for label in ax.get_yticklabels()] == ["01", "1"]
    finally:
        plt.close(fig)


def test_confusion_preserves_class_identity_and_weighted_counts(tmp_path):
    module, _ = generated(
        tmp_path,
        csv="step,score,n\n01,01,2\n1,01,1\n1,1,3\n",
        kind="confusion_matrix",
        group=None,
        normalize="none",
        value="n",
    )
    matrix = module.confusion_counts(prepared(module))
    assert list(matrix.index) == list(matrix.columns) == ["01", "1"]
    np.testing.assert_array_equal(matrix, [[2, 1], [0, 3]])


def test_table_preserves_row_labels_series_names_and_ordered_cells(tmp_path):
    module, _ = generated(
        tmp_path,
        csv="step,score,model\n01,1,1\n01,2,2\n1,3,1\n1,4,2\n",
        kind="table",
        series_order=["2", "1"],
    )
    table, _, _ = module.build_table(prepared(module))
    assert list(table.index) == ["01", "1"] and list(table.columns) == ["2", "1"]
    np.testing.assert_array_equal(table, [[2, 1], [4, 3]])


def test_leading_zero_facet_names_own_distinct_panels(tmp_path):
    module, _ = generated(
        tmp_path,
        csv="step,score,site\n1,10,01\n2,12,01\n1,20,1\n2,22,1\n",
        group=None,
        facet={"by": "site", "columns": 2},
    )
    panels = module.panels(prepared(module))
    assert [(name, frame["score"].tolist()) for name, frame in panels] == [
        ("01", [10, 12]),
        ("1", [20, 22]),
    ]


def test_leading_zero_pair_ids_remain_two_independent_matched_units(tmp_path):
    module, _ = generated(
        tmp_path,
        csv="step,score,unit\n0,10,01\n1,14,01\n0,20,1\n1,26,1\n",
        kind="paired_difference",
        group=None,
        pair="unit",
        baseline="0",
    )
    fit = module.paired_estimates(prepared(module))[0]
    assert fit["n"] == 2 and fit["mean"] == 5
    np.testing.assert_array_equal(fit["values"], [4, 6])
    assert fit["technical_repeats"] == 0 and (fit["low"], fit["high"]) == (4, 6)


def test_repeat_ids_keep_equal_unit_weight_instead_of_merging(tmp_path):
    module, _ = generated(
        tmp_path,
        csv="step,score,model,unit\n1,0,A,01\n1,0,A,01\n1,10,A,1\n",
        aggregation="mean",
        uncertainty={"kind": "sem", "over": "unit"},
    )
    frame = prepared(module)
    row = module.summarise(frame).iloc[0]
    assert row["score"] == 5 and row["_low"] == 0 and row["_high"] == 10
    module.report_counts(frame)
    assert module.ROW_COUNTS["sample_sizes"] == [2]
    assert module.ROW_COUNTS["unit_observations"] == 2


@pytest.mark.parametrize(
    "op,value,expected",
    [
        ("eq", 1, [10, 12, 20, 22]),
        ("in", [1], [10, 12, 20, 22]),
        ("gt", 0, [10, 12, 20, 22]),
        ("not_in", [2], [10, 12, 20, 22]),
    ],
)
def test_raw_numeric_identifier_filters_precede_lexical_identity(tmp_path, op, value, expected):
    module, _ = generated(tmp_path, filter=[{"field": "model", "op": op, "value": value}])
    frame = prepared(module)
    assert frame["score"].tolist() == expected
    assert frame["model"].tolist() == ["01", "01", "1", "1"]


def test_raw_string_filter_retains_existing_typed_input_semantics(tmp_path):
    module, _ = generated(tmp_path, filter=[{"field": "model", "op": "eq", "value": "01"}])
    with pytest.raises(SystemExit, match="every row was filtered out"):
        prepared(module)


def test_numeric_measurement_filter_preserves_row_to_identity_alignment(tmp_path):
    module, _ = generated(tmp_path, filter=[{"field": "score", "op": "gt", "value": 11}])
    frame = prepared(module)
    assert list(zip(frame["model"], frame["score"], strict=True)) == [
        ("01", 12),
        ("1", 20),
        ("1", 22),
    ]
    assert pd.api.types.is_numeric_dtype(frame["step"])
    assert pd.api.types.is_numeric_dtype(frame["score"])


def test_numeric_baseline_transform_uses_named_identity_after_filtering(tmp_path):
    module, _ = generated(
        tmp_path,
        csv="step,score,model\n1,10,1\n2,20,1\n1,15,2\n2,30,2\n",
        transform={"kind": "delta_vs_baseline", "baseline": "1"},
    )
    frame = prepared(module)
    assert frame["model"].tolist() == ["2", "2"] and frame["score"].tolist() == [5, 10]


def test_wide_reshape_restores_ids_before_melt_and_normalizes_virtual_series(tmp_path):
    module, _ = generated(
        tmp_path,
        csv="step,site,01,1\n2,01,12,22\n1,1,10,20\n",
        group=None,
        series_from_columns={"fields": ["01", "1"]},
        y={"field": "value", "label": "Value"},
        facet={"by": "site"},
    )
    frame = prepared(module)
    assert list(zip(frame["site"], frame["metric"], frame["value"], strict=True)) == [
        ("01", "01", 12),
        ("1", "01", 10),
        ("01", "1", 22),
        ("1", "1", 20),
    ]


def test_temporal_sort_preserves_identity_and_numeric_measurements(tmp_path):
    module, _ = generated(
        tmp_path,
        csv="step,score,model\n2026-01-02,2,01\n2026-01-01,1,1\n",
        x={"field": "step", "label": "Date", "temporal": True},
    )
    frame = prepared(module)
    assert frame["model"].tolist() == ["1", "01"] and frame["score"].tolist() == [1, 2]
    assert pd.api.types.is_datetime64_any_dtype(frame["step"])


@pytest.mark.parametrize("fmt", ["json", "parquet"])
def test_typed_file_names_are_consistent_with_string_orders(tmp_path, fmt):
    rows = pd.DataFrame({"step": [1, 2, 1, 2], "score": [10, 12, 20, 22], "model": [1, 1, 2, 2]})
    data = tmp_path / ("data." + fmt)
    if fmt == "json":
        rows.to_json(data, orient="records")
    else:
        pytest.importorskip("pyarrow")
        rows.to_parquet(data)
    module, _ = generated(
        tmp_path, data={"path": str(data), "format": fmt}, series_order=["2", "1"]
    )
    frame = prepared(module)
    assert module.series_names(frame) == ["2", "1"]
    np.testing.assert_array_equal(frame["score"], [10, 12, 20, 22])


def test_json_string_spelling_is_preserved_before_dtype_inference(tmp_path):
    data = tmp_path / "data.json"
    data.write_text('[{"step":1,"score":10,"model":"01"},{"step":2,"score":20,"model":"1"}]')
    module, _ = generated(tmp_path, data={"path": str(data), "format": "json"})
    assert prepared(module)["model"].tolist() == ["01", "1"]


def test_direct_dataframe_names_are_normalized_without_mutating_input(tmp_path):
    module, _ = generated(tmp_path)
    rows = pd.DataFrame({"step": [1, 2], "score": [10, 20], "model": [1, 2]})
    frame = module.prepare(rows)
    assert frame["model"].tolist() == ["1", "2"] and rows["model"].tolist() == [1, 2]
    pd.testing.assert_frame_equal(module.prepare(frame), frame)


def test_missing_repeat_id_stays_missing_and_is_accounted(tmp_path):
    module, _ = generated(
        tmp_path,
        csv="step,score,model,unit\n1,0,A,01\n1,10,A,1\n1,100,A,\n",
        aggregation="mean",
        uncertainty={"kind": "sem", "over": "unit"},
    )
    frame = prepared(module)
    assert pd.isna(frame["unit"].iloc[-1])
    module.report_counts(frame)
    assert module.ROW_COUNTS["missing_unit_ids"] == 1
    assert module.summarise(frame)["score"].tolist() == [5]


@pytest.mark.parametrize("value", [None, "", " ", float("inf"), [1, 2]])
def test_missing_or_invalid_series_does_not_become_a_plausible_named_cohort(tmp_path, value):
    module, _ = generated(tmp_path)
    rows = pd.DataFrame({"step": [1, 2], "score": [10, 20], "model": ["good", value]})
    with pytest.raises(ValueError, match=r"[Ii]dentif"):
        module.prepare(rows)


@pytest.mark.parametrize("order", [["absent"], ["1"]])
def test_category_order_cannot_silently_hide_observed_categories(tmp_path, order):
    module, _ = generated(
        tmp_path, csv="step,score\n1,10\n2,20\n", kind="bar", group=None, category_order=order
    )
    with pytest.raises(ValueError, match="categor"):
        module.category_order(prepared(module))


def test_dual_identity_measurement_role_is_explicitly_refused(tmp_path):
    result = local_request("convert", {**BASE, "data": {"path": "data.csv"}, "group": "score"})
    assert not result["ok"]
    assert any(f["code"] == "unsupported_identity_roles" for f in result["findings"])


def test_one_byte_snapshot_owns_identity_values_measurements_and_data_hash(tmp_path, monkeypatch):
    module, _ = generated(tmp_path)
    original = pd.read_csv
    calls = []

    def read_and_change(*args, **kwargs):
        frame = original(*args, **kwargs)
        calls.append(1)
        (tmp_path / "data.csv").write_text("step,score,model\n9,999,99\n")
        return frame

    monkeypatch.setattr(pd, "read_csv", read_and_change)
    frame = prepared(module)
    assert frame["model"].tolist() == ["01", "01", "1", "1"]
    assert frame["score"].tolist() == [10, 12, 20, 22]
    assert hashlib.sha256(CSV.encode()).hexdigest()[:16] == module.DATA_HASH
    assert len(calls) == 2


def test_runtime_claim_and_exported_description_use_actual_lexical_cohorts(tmp_path):
    _, path = generated(
        tmp_path,
        series_order=["1", "01"],
        claims=[{"kind": "beats_everywhere", "subject": "1", "reference": "01"}],
    )
    process = subprocess.run(
        [sys.executable, str(path), "--strict", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report["status"] == "passed" and report["claims"][0]["verdict"] == "holds"
    assert "01" in report["alt_text"] and "22" in report["alt_text"]
    for suffix in ["png", "svg"]:
        evidence = read_provenance(tmp_path / ("identity." + suffix))
        assert evidence["alt_text"] == report["alt_text"]


@pytest.mark.parametrize("fmt", ["json", "parquet"])
def test_lexical_typed_files_keep_distinct_leading_zero_ids(tmp_path, fmt):
    rows = pd.DataFrame({"step": [1, 2], "score": [10, 20], "model": ["01", "1"]})
    data = tmp_path / ("lexical." + fmt)
    if fmt == "json":
        rows.to_json(data, orient="columns")
    else:
        pytest.importorskip("pyarrow")
        rows.to_parquet(data)
    module, _ = generated(tmp_path, data={"path": str(data), "format": fmt})
    assert prepared(module)["model"].tolist() == ["01", "1"]


def test_json_date_named_identifier_is_literal_text(tmp_path):
    data = tmp_path / "date.json"
    data.write_text(
        '[{"step":1,"score":10,"date":"2026-01-01"},{"step":2,"score":20,"date":"2026-01-02"}]'
    )
    module, _ = generated(tmp_path, group="date", data={"path": str(data), "format": "json"})
    assert prepared(module)["date"].tolist() == ["2026-01-01", "2026-01-02"]


def test_json_big_integer_units_do_not_round_or_merge(tmp_path):
    data = tmp_path / "big.json"
    data.write_text(
        '[{"step":1,"score":0,"unit":9007199254740992},{"step":1,"score":10,"unit":9007199254740993},{"step":1,"score":100,"unit":null}]'
    )
    module, _ = generated(
        tmp_path,
        group=None,
        data={"path": str(data), "format": "json"},
        aggregation="mean",
        uncertainty={"kind": "sem", "over": "unit"},
    )
    frame = prepared(module)
    assert frame["unit"].tolist() == ["9007199254740992", "9007199254740993", None]
    assert module.summarise(frame)["score"].tolist() == [5]


@pytest.mark.parametrize(
    "options",
    [
        {"series_order": ["1", "1"]},
        {"kind": "bar", "group": None, "category_order": ["1", "1"]},
    ],
)
def test_duplicate_orders_are_refused_before_rendering(options):
    spec = {**BASE, "data": {"path": "data.csv"}, **options}
    spec = {key: value for key, value in spec.items() if value is not None}
    result = local_request("convert", spec)
    assert result["status"] == "translated" and not result["ok"]
    assert any(f["code"] == "duplicate_identity_order" for f in result["findings"])


@pytest.mark.parametrize(
    "options",
    [
        {"group": "step"},
        {"facet": {"by": "score"}},
        {"kind": "calibration", "outcome": "flag", "group": "flag"},
        {"kind": "kaplan_meier", "event": "flag", "group": "flag"},
        {"kind": "heatmap", "value": "model", "value_label": "Value"},
        {"layers": [{"mark": "line", "y": "model", "label": "Reference"}]},
        {"repeat": {"fields": ["score", "model"]}},
    ],
)
def test_measurement_roles_are_not_silently_rewritten_as_text(options):
    result = local_request("convert", {**BASE, "data": {"path": "data.csv"}, **options})
    assert result["status"] == "translated" and not result["ok"], result
    assert any(f["code"] == "unsupported_identity_roles" for f in result["findings"])


def test_palette_lock_and_direct_labels_use_the_same_canonical_names(tmp_path):
    module, _ = generated(tmp_path, series_order=["1", "01"], legend={"style": "direct"})
    frame = prepared(module)
    module.LOCKED = {"1": {"colour": "#ff0000", "linestyle": ":"}}
    style = module.series_style("1", 0, 2)
    assert style["colour"] == "#ff0000" and style["linestyle"] == ":"
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, frame)
        module.add_legend(fig, ax, frame)
        assert [(text.get_text(), text.xy) for text in ax.texts] == [
            ("1", (2, 22)),
            ("01", (2, 12)),
        ]
    finally:
        plt.close(fig)


@pytest.mark.parametrize("fmt", ["dataframe", "json"])
def test_distinct_typed_ids_cannot_silently_collide_as_one_string(tmp_path, fmt):
    rows = pd.DataFrame({"step": [1, 2], "score": [10, 20], "model": [1, "1"]}, dtype=object)
    if fmt == "json":
        data = tmp_path / "collision.json"
        data.write_text('[{"step":1,"score":10,"model":1},{"step":2,"score":20,"model":"1"}]')
        module, _ = generated(tmp_path, data={"path": str(data), "format": "json"})
        rows = module.load()
    else:
        module, _ = generated(tmp_path)
    with pytest.raises(ValueError, match="collide"):
        module.prepare(rows)


def test_parquet_ordered_categorical_axis_retains_its_declared_level_order(tmp_path):
    pytest.importorskip("pyarrow")
    data = tmp_path / "ordered.parquet"
    pd.DataFrame(
        {
            "step": pd.Categorical(["B", "A"], categories=["B", "A"], ordered=True),
            "score": ["only", "only"],
            "value": [20, 10],
        }
    ).to_parquet(data)
    module, _ = generated(
        tmp_path,
        data={"path": str(data), "format": "parquet"},
        kind="heatmap",
        group=None,
        value="value",
        value_label="Value",
    )
    frame = prepared(module)
    assert isinstance(frame["step"].dtype, pd.CategoricalDtype) and frame["step"].cat.ordered
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, frame)
        assert [text.get_text() for text in ax.get_xticklabels()] == ["B", "A"]
        np.testing.assert_array_equal(ax.images[0].get_array(), [[20, 10]])
    finally:
        plt.close(fig)


@pytest.mark.parametrize(("fmt", "codec"), [("csv", "gzip"), ("json", "gzip"), ("csv", "zip")])
def test_compressed_inputs_keep_identity_and_hash_the_actual_input_bytes(tmp_path, fmt, codec):
    import gzip
    from zipfile import ZipFile

    payload = (
        CSV.encode()
        if fmt == "csv"
        else b'[{"step":1,"score":10,"model":"01"},{"step":2,"score":20,"model":"1"}]'
    )
    data = tmp_path / ("compressed." + fmt + (".gz" if codec == "gzip" else ".zip"))
    if codec == "gzip":
        data.write_bytes(gzip.compress(payload))
    else:
        with ZipFile(data, "w") as archive:
            archive.writestr("data.csv", payload)
    module, _ = generated(tmp_path, data={"path": str(data), "format": fmt})
    frame = prepared(module)
    assert frame["model"].tolist() == (["01", "01", "1", "1"] if fmt == "csv" else ["01", "1"])
    assert hashlib.sha256(data.read_bytes()).hexdigest()[:16] == module.DATA_HASH


def test_json_numeric_looking_measurement_column_names_do_not_collapse(tmp_path):
    data = tmp_path / "columns.json"
    data.write_text('{"01":[1,2],"1":[10,20]}')
    module, _ = generated(
        tmp_path,
        group=None,
        data={"path": str(data), "format": "json"},
        x={"field": "01", "label": "X"},
        y={"field": "1", "label": "Y"},
    )
    frame = prepared(module)
    assert list(frame.columns) == ["01", "1"]
    fig, ax = plt.subplots()
    try:
        module.draw_panel(ax, frame)
        np.testing.assert_array_equal(ax.lines[0].get_xdata(), [1, 2])
        np.testing.assert_array_equal(ax.lines[0].get_ydata(), [10, 20])
    finally:
        plt.close(fig)


def test_json_wide_numeric_column_names_become_distinct_virtual_series(tmp_path):
    data = tmp_path / "wide.json"
    data.write_text('{"step":[1,2],"01":[10,12],"1":[20,22]}')
    module, _ = generated(
        tmp_path,
        group=None,
        data={"path": str(data), "format": "json"},
        y={"field": "value", "label": "Value"},
        series_from_columns={"fields": ["01", "1"]},
    )
    frame = prepared(module)
    assert module.series_names(frame) == ["01", "1"]
    assert frame["value"].tolist() == [10, 12, 20, 22]


@pytest.mark.parametrize("encoded", [False, True])
def test_explicit_http_input_is_fetched_once_before_any_identity_conversion(tmp_path, encoded):
    import gzip
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    calls = []
    payload = gzip.compress(CSV.encode()) if encoded else CSV.encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            self.send_response(200)
            if encoded:
                self.send_header("Content-Encoding", "gzip")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        name = "data.csv.gz" if encoded else "data.csv"
        url = f"http://127.0.0.1:{server.server_port}/{name}"
        module, _ = generated(tmp_path, data={"path": url, "format": "csv"})
        frame = prepared(module)
        assert frame["model"].tolist() == ["01", "01", "1", "1"]
        assert frame["score"].tolist() == [10, 12, 20, 22]
        assert calls == ["/" + name]
        assert hashlib.sha256(CSV.encode()).hexdigest()[:16] == module.DATA_HASH
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


@pytest.mark.parametrize(
    ("names", "expected"), [([1.0, 2.0], ["1.0", "2.0"]), ([True, False], ["True", "False"])]
)
def test_typed_scalar_identity_spelling_is_explicit_and_does_not_change_measurements(
    tmp_path, names, expected
):
    module, _ = generated(tmp_path)
    rows = pd.DataFrame({"step": [1, 2], "score": [10, 20], "model": names})
    frame = module.prepare(rows)
    assert frame["model"].tolist() == expected
    np.testing.assert_array_equal(frame["step"], [1, 2])
    np.testing.assert_array_equal(frame["score"], [10, 20])


def test_nested_facet_row_and_column_identifiers_stay_distinct(tmp_path):
    module, _ = generated(
        tmp_path,
        csv="step,score,site,row\n1,10,01,001\n1,20,1,001\n1,30,01,1\n1,40,1,1\n",
        group=None,
        facet={"by": "site", "rows": "row", "columns": 2},
    )
    panels = module.panels(prepared(module))
    assert [(name, frame["score"].tolist()) for name, frame in panels] == [
        ("001 / 01", [10]),
        ("001 / 1", [20]),
        ("1 / 01", [30]),
        ("1 / 1", [40]),
    ]


def test_rendered_table_artists_show_exact_row_and_ordered_column_names(tmp_path, monkeypatch):
    module, _ = generated(
        tmp_path,
        csv="step,score,model\n01,1,1\n01,2,2\n1,3,1\n1,4,2\n",
        kind="table",
        series_order=["2", "1"],
    )
    captured = []
    close = plt.close
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(plt, "close", captured.append)
    try:
        module.main()
        figure = next(figure for figure in captured if hasattr(figure, "axes"))
        cells = figure.axes[0].tables[0].get_celld()
        assert [cells[(0, c)].get_text().get_text() for c in [0, 1]] == ["2", "1"]
        assert [cells[(r, -1)].get_text().get_text() for r in [1, 2]] == ["01", "1"]
        assert [[cells[(r, c)].get_text().get_text() for c in [0, 1]] for r in [1, 2]] == [
            ["2.00", "1.00"],
            ["4.00", "3.00"],
        ]
    finally:
        for figure in captured:
            close(figure)
