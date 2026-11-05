"""Exercise parsed observation selection through generated scripts, SDK and CLI."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import runpy
import subprocess
import sys
from importlib.resources import files

import jsonschema
import pandas as pd
import pytest

from graphunslopify import Figure, SpecError
from graphunslopify.cli import main
from graphunslopify.observation_provenance import (
    ObservationLedger,
    _read_observation_selection,
)


def scatter(path):
    return (
        Figure.scatter(path)
        .x("x", "X")
        .y("y", "Y")
        .set(legend={"show": False})
        .output(formats=["png"])
    )


def evidence(report, directory, source):
    selection = report["observation_selection"]
    payload = (directory / selection["path"]).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == selection["sha256"]
    ledger = ObservationLedger.from_json(payload)
    graph = ledger.as_dict()
    assert graph["source"]["snapshot_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert graph["context"]["run_id"] == selection["run_id"]
    assert graph["context"]["program_sha256"] == report["script"]["sha256"]
    assert graph["context"]["spec_sha256"][:16] == report["spec_hash"]
    assert graph["context"]["runtime_source_sha256"] == report["script"]["runtime"]["source_sha256"]
    nodes = {node["id"]: node for node in graph["nodes"]}
    root = nodes[selection["node_id"]]
    assert root["operation"] == "reader_filter_selection"
    assert root["value"] == report["data"]["counts"]["after_filter"]
    retained = [nodes[ref]["record_ordinal"] for ref in root["inputs"]]
    exclusions = {
        (node["metadata"]["step"], node["reason"]): [
            nodes[ref]["record_ordinal"] for ref in node["inputs"]
        ]
        for node in (nodes[ref] for ref in root["excluded"])
    }
    return graph["source"]["reader"], retained, exclusions


def test_compressed_quoted_csv_selection_and_ordinary_render_match(tmp_path):
    source = tmp_path / "quoted.csv.gz"
    raw = b'x,y,group,note\n1,2,A,"secret\nline"\n2,3,A,same\n2,3,A,same\n3,1,A,low\n4,5,B,other\n'
    source.write_bytes(gzip.compress(raw))
    filters = [
        {"field": "group", "op": "eq", "value": "A"},
        {"field": "y", "op": "gt", "value": 1},
    ]
    figure = scatter(source).set(filter=filters)
    normal = figure.render(cwd=tmp_path / "normal")
    traced = figure.render(cwd=tmp_path / "traced", trace_observations=True)
    reader, retained, exclusions = evidence(traced["report"], traced["script"].parent, source)
    rows = list(csv.DictReader(io.StringIO(raw.decode())))
    expected = [i for i, row in enumerate(rows) if row["group"] == "A" and int(row["y"]) > 1]
    assert rows[1] == rows[2]
    assert retained == expected == [0, 1, 2]
    assert exclusions == {(0, "filter_predicate_false"): [4], (1, "filter_predicate_false"): [3]}
    assert reader["format"] == "csv" and reader["compression"] == "gzip"
    assert traced["report"]["data"] == normal["report"]["data"]
    assert traced["report"]["alt_text"] == normal["report"]["alt_text"]
    assert "observation_selection" not in normal["report"]
    assert not list(normal["script"].parent.glob("observations-*.json"))
    assert b"secret" not in traced["observation_path"].read_bytes()


def test_parquet_positions_follow_temporal_sort_and_nullable_duplicate_index(tmp_path, monkeypatch):
    pytest.importorskip("pyarrow")
    source = tmp_path / "points.parquet"
    frame = pd.DataFrame(
        {
            "x": pd.to_datetime(
                ["2026-11-05", "2026-11-02", "2026-11-06", "2026-11-04", "2026-11-01", "2026-11-03"]
            ),
            "y": pd.array([8, None, -3, 7, 5, 2], dtype="Int64"),
            "series": ["A", "A", "B", "B", "A", "A"],
            "__gu_ordinal": [80, 70, 60, 50, 40, 30],
        },
        index=[11, 11, 17, 9, 11, 9],
    )
    frame.to_parquet(source)
    figure = (
        scatter(source)
        .x("x", "Date", temporal=True)
        .set(
            filter=[
                {"field": "y", "op": "gt", "value": 0},
                {"field": "series", "op": "eq", "value": "A"},
            ]
        )
    )
    traced = figure.render(cwd=tmp_path / "trace", trace_observations=True)
    reader, retained, exclusions = evidence(traced["report"], traced["script"].parent, source)
    assert reader["format"] == "parquet" and reader["engine"] == "pyarrow"
    assert retained == [4, 5, 0]
    assert exclusions == {
        (0, "filter_predicate_missing"): [1],
        (0, "filter_predicate_false"): [2],
        (1, "filter_predicate_false"): [3],
    }
    pd.testing.assert_frame_equal(pd.read_parquet(source), frame)
    monkeypatch.chdir(traced["script"].parent)
    loaded, _ = runpy.run_path(str(traced["script"]))["load"]()
    pd.testing.assert_frame_equal(loaded, frame.sort_values("x"), check_exact=True)


@pytest.mark.parametrize("input_format", ["json", "excel"])
def test_cli_reports_actual_reader_and_keeps_standalone_evidence(tmp_path, capsys, input_format):
    frame = pd.DataFrame({"x": [1, 2, 2, 3], "y": [2, 3, 3, 0]})
    if input_format == "json":
        source = tmp_path / "points.json"
        frame.to_json(source, orient="records")
        figure = scatter(source)
    else:
        pytest.importorskip("python_calamine")
        pytest.importorskip("openpyxl")
        source = tmp_path / "points.xlsx"
        with pd.ExcelWriter(source, engine="openpyxl") as book:
            frame.iloc[:1].to_excel(book, sheet_name="Other", index=False)
            frame.to_excel(book, sheet_name="Measures", index=False)
        figure = scatter(source)
        figure.spec["data"]["sheet"] = "Measures"
    figure.set(filter=[{"field": "y", "op": "gt", "value": 0}])
    spec = tmp_path / "spec.json"
    spec.write_text(figure.to_json(), encoding="utf8")
    out = tmp_path / "output"
    assert main(["render", str(spec), "--out-dir", str(out), "--trace-observations", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    schema = files("graphunslopify").joinpath("schemas", "runtime-report.schema.json")
    jsonschema.Draft202012Validator(json.loads(schema.read_text(encoding="utf8"))).validate(report)
    reader, retained, exclusions = evidence(report, out, source)
    assert reader["format"] == input_format
    if input_format == "excel":
        assert reader["sheet"] == "Measures" and reader["engine"] == "calamine"
    assert retained == [0, 1, 2]
    assert exclusions == {(0, "filter_predicate_false"): [3]}

    script = out / f"{figure.spec['output'].get('stem', 'figure')}.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--json"], cwd=out, capture_output=True, check=True
    )
    rerun = json.loads(completed.stdout)
    assert evidence(rerun, out, source) == (reader, retained, exclusions)
    first, second = report["observation_selection"], rerun["observation_selection"]
    assert first["path"] != second["path"] and first["run_id"] != second["run_id"]
    with pytest.raises(ValueError, match="different run"):
        _read_observation_selection(
            out, report, run_id=second["run_id"], program_sha256=rerun["script"]["sha256"]
        )


def test_all_filtered_failure_still_reports_exact_exclusions(tmp_path):
    source = tmp_path / "points.csv"
    source.write_text("x,y\n1,2\n2,3\n", encoding="utf8")
    figure = scatter(source).set(filter=[{"field": "y", "op": "gt", "value": 10}])
    with pytest.raises(SpecError, match="every row was filtered out") as failed:
        figure.render(cwd=tmp_path, trace_observations=True)
    _, retained, exclusions = evidence(failed.value.report, tmp_path, source)
    assert retained == []
    assert exclusions == {(0, "filter_predicate_false"): [0, 1]}
    with pytest.raises(SpecError, match="requires the local translator"):
        figure.translate("https://example.invalid", trace_observations=True)


def test_trace_refuses_report_and_figure_aliases_without_changing_source(tmp_path):
    source = tmp_path / "figure.report.json"
    original = b'[{"x":1,"y":2},{"x":2,"y":3}]'
    source.write_bytes(original)
    figure = scatter(source).output(stem="figure")
    with pytest.raises(SpecError, match="would overwrite an observation input"):
        figure.render(cwd=tmp_path, trace_observations=True)
    assert source.read_bytes() == original
    assert not (tmp_path / "figure.py").exists()

    out = tmp_path / "output"
    out.mkdir()
    (out / "figure.png").hardlink_to(source)
    with pytest.raises(SpecError, match="would overwrite an observation input"):
        figure.render(cwd=out, trace_observations=True)
    assert source.read_bytes() == original
    assert not list(out.glob("observations-*.json"))

    (out / "figure.png").unlink()
    completed = subprocess.run(
        [sys.executable, str(out / "figure.py"), "--report", str(source)],
        cwd=out,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 1
    assert b"would overwrite an observation input" in completed.stderr
    assert source.read_bytes() == original


def test_demo_uses_the_default_render_without_observation_tracing(tmp_path, capsys):
    output = tmp_path / "demo with spaces"
    assert main(["demo", str(output), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "passed"
    assert "observation_selection" not in report
    assert not list(output.glob("observations-*.json"))
